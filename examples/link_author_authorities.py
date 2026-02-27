"""
Link item authors to local authority records (interactive).

Enhances an item that has dc.contributor.author in clear text by linking each
unlinked author to an authority already in this repository's SOLR authority core.
Uses the local vocabulary endpoint (e.g. CacheableAuthorAuthority) only — does
NOT search the public ORCID registry.

You can choose Exact or Fuzzy author matching (Fuzzy allows "Smith, J." to match "Smith, John");
and whether to review every ORCID match or auto-link. Item UUID is optional: leave empty to
process all items (newest first). Each run writes a timestamped log file.

Run with the project venv (see README "Development")::
  source venv/bin/activate
  python examples/link_author_authorities.py [item-uuid]
  # or: ./venv/bin/python examples/link_author_authorities.py [item-uuid]
  # Leave item UUID empty to process all items (newest first). Run can take a long time; Ctrl+C is safe, log is still written.
"""

import asyncio
import getpass
import json
import os
import sys
from datetime import datetime
import time
from typing import Awaitable, Callable, List, Optional, Tuple
import unicodedata

from rich.console import Console
from rich.panel import Panel

from dspace_client import AuthenticationError, DSpaceAPIError, DSpaceAuthClient, DSpaceClient
from dspace_client.throttle import ThrottleConfig, ThrottleController

# Compatible with DSpace 7.x, 8.x, 9.x (items PATCH and submission vocabularies)
TARGET_VERSIONS = ["7.0", "8.0", "9.0"]

# Default vocabulary for local author authority (SOLR cache); may be SolrAuthorAuthority on some instances
DEFAULT_AUTHORITY_VOCABULARY = "CacheableAuthorAuthority"

AUTHOR_FIELD = "dc.contributor.author"
CONFIDENCE_LINKED = 600

console = Console()


async def _ensure_fresh_session(
    auth: DSpaceAuthClient,
    client: DSpaceClient,
    username: str,
    password: str,
) -> None:
    """
    Proactively refresh the session if it is near or past its configured max age.
    
    Updates the DSpaceClient's JWT/CSRF tokens if a refresh occurs.
    """
    jwt = await auth.ensure_session(username, password)
    # Keep client in sync with latest auth tokens
    client.jwt_token = auth.jwt_token or jwt
    if auth.csrf_token:
        client.csrf_token = auth.csrf_token


async def _call_with_reauth(
    auth: DSpaceAuthClient,
    client: DSpaceClient,
    username: str,
    password: str,
    func: Callable[[], Awaitable],
) -> object:
    """
    Wrap a DSpaceClient operation so that:
    - It uses proactive session refresh via _ensure_fresh_session.
    - On first 401 DSpaceAPIError, it forces re-auth and retries once.
    """
    await _ensure_fresh_session(auth, client, username, password)
    retry_on_401 = os.environ.get("DSPACE_RETRY_ON_401", "1").lower() not in ("0", "false", "no")

    try:
        return await func()
    except DSpaceAPIError as e:
        status = getattr(e, "status_code", None)
        if not retry_on_401 or status != 401:
            raise

        console.print("[yellow]Received 401 from DSpace API; refreshing session and retrying once...[/yellow]")
        # Force re-auth and sync client tokens, then retry once
        jwt = await auth.ensure_session(username, password, force=True)
        client.jwt_token = auth.jwt_token or jwt
        if auth.csrf_token:
            client.csrf_token = auth.csrf_token

        return await func()


async def _throttled_call(
    auth: DSpaceAuthClient,
    client: DSpaceClient,
    username: str,
    password: str,
    throttle: ThrottleController,
    func: Callable[[], Awaitable],
) -> object:
    """
    Wrap a DSpaceClient operation with adaptive, single-threaded throttling.
    
    This keeps execution linear:
    - Sleep for the current delay
    - Delegate to _call_with_reauth (which handles session refresh/401 retry)
    - Record duration and any HTTP status code for feedback
    """
    await throttle.before_call()
    start = time.time()
    try:
        result = await _call_with_reauth(auth, client, username, password, func)
        duration = time.time() - start
        await throttle.after_call(duration, success=True, status_code=None)
        return result
    except DSpaceAPIError as e:
        duration = time.time() - start
        status = getattr(e, "status_code", None)
        await throttle.after_call(duration, success=False, status_code=status)
        raise
    except Exception:
        duration = time.time() - start
        await throttle.after_call(duration, success=False, status_code=None)
        raise


def _strip_accents(s: str) -> str:
    """Remove diacritics from a string while preserving base characters."""
    if not s:
        return ""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )


def normalize_name(s: str) -> str:
    """Normalize author name for exact match (strip spaces, ignore accents, lowercase)."""
    if not s:
        return ""
    # Collapse whitespace, then strip accents and lowercase for accent-insensitive matching
    collapsed = " ".join(s.split())
    no_accents = _strip_accents(collapsed)
    return no_accents.lower()


def _parse_family_first(name: str) -> Tuple[str, str]:
    """Split 'Family, First' into (family, first). If no comma, return (normalized, '')."""
    n = normalize_name(name)
    if not n:
        return ("", "")
    if "," in n:
        parts = n.split(",", 1)
        return (normalize_name(parts[0]), normalize_name(parts[1]))
    return (n, "")


def _initials(s: str) -> str:
    """Get initials from a name part, e.g. 'Jane Marie' -> 'J M', 'John' -> 'J'."""
    if not s:
        return ""
    return " ".join((w[0] for w in s.split() if w)).upper()


def _normalize_initials(s: str) -> str:
    """Normalize an initials string for comparison: 'J. M.' -> 'J M', 'J.M.' -> 'J M'."""
    if not s:
        return ""
    # Strip accents, remove periods and collapse spaces, then rejoin with single space
    base = _strip_accents(s)
    cleaned = " ".join(base.replace(".", " ").split()).upper()
    return cleaned


def fuzzy_match_author(item_author: str, authority_name: str) -> bool:
    """
    Return True if item_author matches authority_name allowing abbreviated first names.

    E.g. "Smith, J." matches "Smith, John"; "Doe, J. M." matches "Doe, Jane Marie".
    Both must be in "Family, First" form (comma-separated). Family name must match exactly
    (after normalize); first name matches if item's first is initials and matches
    authority's first name initials.
    """
    item_family, item_first = _parse_family_first(item_author)
    auth_family, auth_first = _parse_family_first(authority_name)
    if not item_family or not auth_family:
        return False
    if item_family.lower() != auth_family.lower():
        return False
    if not item_first and not auth_first:
        return True
    if not item_first:
        return True  # item has no first name, family match only
    if not auth_first:
        return False
    # Exact first name match (e.g. "Smith, John" vs "Smith, John")
    if normalize_name(item_first).lower() == normalize_name(auth_first).lower():
        return True
    # Item first is initials and matches authority first initials (e.g. "Smith, J." vs "Smith, John")
    item_initials = _normalize_initials(item_first)
    auth_initials = _initials(auth_first)
    return item_initials == auth_initials


def get_unlinked_authors(metadata: dict) -> List[Tuple[int, dict]]:
    """Return list of (index, value_obj) for dc.contributor.author where authority is null."""
    entries = metadata.get(AUTHOR_FIELD) or []
    result = []
    for i, obj in enumerate(entries):
        if not isinstance(obj, dict):
            continue
        authority = obj.get("authority") if obj else None
        if authority is None or (isinstance(authority, str) and authority.strip() == ""):
            result.append((i, obj))
    return result


async def fetch_entry_detail(client: DSpaceClient, vocabulary_name: str, authority_uuid: str) -> Optional[dict]:
    """Optionally fetch vocabulary entry detail for ORCID/display. Returns None on any error."""
    return await client.get_vocabulary_entry_detail(vocabulary_name, authority_uuid)


def extract_orcid_from_entry(entry: dict, detail: Optional[dict]) -> Optional[str]:
    """Get ORCID URL from vocabulary entry or its detail if available."""
    # From entry metadata (some authorities store dc.identifier.orcid)
    meta = entry.get("metadata") or {}
    for key in ("dc.identifier.orcid", "orcid"):
        for lst in (meta.get(key) or []):
            if isinstance(lst, dict) and lst.get("value"):
                v = lst["value"].strip()
                if v and not v.startswith("http"):
                    return f"https://orcid.org/{v}"
                return v or None
    # From detail otherInformation
    if detail and isinstance(detail.get("otherInformation"), dict):
        oi = detail["otherInformation"]
        for key in ("orcid", "dc.identifier.orcid"):
            if oi.get(key):
                v = str(oi[key]).strip()
                if v and not v.startswith("http"):
                    return f"https://orcid.org/{v}"
                return v or None
    return None


def _log(log_file: Optional[object], line: str) -> None:
    """Write a line to the log file and flush."""
    if log_file is not None:
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        log_file.write(f"{ts} {line}\n")
        log_file.flush()


def _first_metadata_value(metadata: dict, key: str) -> str:
    """Get first metadata value for a key, or empty string."""
    vals = metadata.get(key) or []
    if not isinstance(vals, list) or not vals:
        return ""
    first = vals[0]
    if isinstance(first, dict):
        return str(first.get("value") or "").strip()
    return str(first).strip()


def _all_metadata_values(metadata: dict, key: str) -> List[str]:
    """Get all metadata values for a key as strings."""
    vals = metadata.get(key) or []
    result: List[str] = []
    if not isinstance(vals, list):
        return result
    for v in vals:
        if isinstance(v, dict):
            s = str(v.get("value") or "").strip()
        else:
            s = str(v).strip()
        if s:
            result.append(s)
    return result


STATE_ENV_VAR = "LINK_AUTHOR_STATE_FILE"
DEFAULT_STATE_FILENAME = "link_author_authorities_state.jsonl"


def _get_state_path(log_dir: str) -> str:
    """Compute path for the incremental state file."""
    override = os.environ.get(STATE_ENV_VAR)
    if override:
        return override
    return os.path.join(log_dir, DEFAULT_STATE_FILENAME)


def _load_attempt_state(path: str) -> dict[str, datetime]:
    """Load last-attempt timestamps per item UUID from a JSONL state file."""
    state: dict[str, datetime] = {}
    if not os.path.exists(path):
        return state
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                uuid = rec.get("uuid")
                ts = rec.get("last_attempt")
                if not uuid or not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    continue
                state[uuid] = dt
    except OSError:
        return state
    return state


def _append_attempt_state(path: str, item_uuid: str, when: datetime) -> None:
    """Append a single attempt record to the state file."""
    rec = {"uuid": item_uuid, "last_attempt": when.isoformat()}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        # Best-effort only; do not fail the whole run if we can't write state
        return


def _should_process_uuid(
    item_uuid: str,
    mode: str,
    state: dict[str, datetime],
    now: datetime,
    min_age_days: Optional[int],
) -> bool:
    """
    Decide whether to process a given item UUID based on incremental state.
    
    Modes:
    - "new": only items never seen before.
    - "since": items never seen OR last attempt at least `min_age_days` ago.
    - "force": always process.
    """
    if mode == "force":
        return True
    last = state.get(item_uuid)
    if last is None:
        return True  # new in both "new" and "since" modes
    if mode == "new":
        return False
    if mode == "since" and min_age_days is not None:
        delta = now - last
        return delta.days >= min_age_days
    return True


async def discover_item_uuids_newest_first(
    auth: DSpaceAuthClient,
    client: DSpaceClient,
    username: str,
    password: str,
    throttle: ThrottleController,
    page_size: int = 100,
) -> List[str]:
    """Discover all item UUIDs via discovery API, newest first. Paginates until no more results."""
    uuids: List[str] = []
    page = 0
    while True:
        results = await _throttled_call(
            auth,
            client,
            username,
            password,
            throttle,
            lambda: client.search_items(
                query="*",
                sort="dc.date.accessioned,desc",
                page=page,
                size=page_size,
            ),
        )
        objects = (
            results.get("_embedded") or {}
        ).get("searchResult", {}).get("_embedded", {}).get("objects", [])
        if not objects:
            break
        for obj in objects:
            indexable = (obj.get("_embedded") or {}).get("indexableObject", {})
            uuid_val = indexable.get("uuid")
            if uuid_val:
                uuids.append(uuid_val)
        if len(objects) < page_size:
            break
        page += 1
    return uuids


async def process_item(
    auth: DSpaceAuthClient,
    client: DSpaceClient,
    username: str,
    password: str,
    throttle: ThrottleController,
    item_uuid: str,
    vocabulary_name: str,
    auto_link_single: bool,
    use_fuzzy: bool,
    log_file: Optional[object],
) -> Tuple[int, int, int]:
    """
    Process one item: find unlinked authors, match to local authority, optionally prompt, PATCH.
    use_fuzzy: if True, allow abbreviated first names (e.g. "Smith, J." matches "Smith, John").
    Returns (linked_count, skipped_user, no_match_count).
    """
    try:
        item = await _throttled_call(
            auth,
            client,
            username,
            password,
            throttle,
            lambda: client.get_item(item_uuid),
        )
    except AuthenticationError as e:
        console.print(f"[red]Authentication error while getting item {item_uuid}: {e}[/red]")
        # Fatal: bubble up so the main loop can abort the run
        raise
    except Exception as e:
        console.print(f"[red]Failed to get item {item_uuid}: {e}[/red]")
        return (0, 0, 0)

    metadata = item.get("metadata") or {}
    title = _first_metadata_value(metadata, "dc.title")
    uris = _all_metadata_values(metadata, "dc.identifier.uri")
    uris_str = ",".join(uris) if uris else ""
    unlinked = get_unlinked_authors(metadata)
    _log(
        log_file,
        f"ITEM uuid={item_uuid} title={title!r} uris={uris_str!r} unlinked_count={len(unlinked)}",
    )

    if not unlinked:
        return (0, 0, 0)

    console.print(
        f"[cyan]Item {item_uuid}: '{title}' ({uris_str or 'no dc.identifier.uri'}) – "
        f"found {len(unlinked)} unlinked author(s).[/cyan]"
    )

    linked_count = 0
    skipped_user = 0
    no_match_count = 0

    for idx, value_obj in unlinked:
        author_value = (value_obj.get("value") or "").strip()
        if not author_value:
            continue
        language = value_obj.get("language")
        normalized = normalize_name(author_value)

        try:
            if use_fuzzy:
                # Fuzzy: paginate by family name to find "Smith, John" when item has "Smith, J."
                family, _ = _parse_family_first(author_value)
                if not family:
                    matching = []
                else:
                    matching = []
                    page = 0
                    size = 100
                    while True:
                        resp = await _throttled_call(
                            auth,
                            client,
                            username,
                            password,
                            throttle,
                            lambda: client.get_vocabulary_entries(
                                vocabulary_name,
                                filter_term=family,
                                exact=False,
                                page=page,
                                size=size,
                            ),
                        )
                        entries = (resp.get("_embedded") or {}).get("entries") or []
                        for e in entries:
                            if not isinstance(e, dict) or not e.get("authority"):
                                continue
                            auth_name = e.get("display") or e.get("value") or ""
                            if fuzzy_match_author(author_value, auth_name):
                                matching.append(e)
                        if matching or len(entries) < size:
                            break
                        page += 1
            else:
                resp = await _throttled_call(
                    auth,
                    client,
                    username,
                    password,
                    throttle,
                    lambda: client.get_vocabulary_entries(
                        vocabulary_name,
                        filter_term=author_value,
                        exact=True,
                        page=0,
                        size=20,
                    ),
                )
                entries = (resp.get("_embedded") or {}).get("entries") or []
                matching = [
                    e
                    for e in entries
                    if isinstance(e, dict)
                    and normalize_name((e.get("display") or e.get("value") or "")) == normalized
                    and e.get("authority")
                ]
        except AuthenticationError as e:
            console.print(
                f"[red]Authentication error during vocabulary lookup for '{author_value}': {e}[/red]"
            )
            # Fatal: bubble up so the main loop can abort the run
            raise
        except Exception as e:
            console.print(f"[red]Vocabulary lookup failed for '{author_value}': {e}[/red]")
            no_match_count += 1
            _log(
                log_file,
                f"NO_MATCH item_uuid={item_uuid} title={title!r} uris={uris_str!r} "
                f"author={author_value!r} reason=lookup_error",
            )
            continue

        if not matching:
            console.print(f"[yellow]No local authority match for: {author_value!r}[/yellow]")
            no_match_count += 1
            _log(
                log_file,
                f"NO_MATCH item_uuid={item_uuid} title={title!r} uris={uris_str!r} "
                f"author={author_value!r}",
            )
            continue

        # Decide which authority entry to use.
        selected_entry: Optional[dict] = None

        if len(matching) > 1:
            # Multiple possible matches: always require explicit user choice.
            lines = [
                f"Multiple local authority matches found for [bold]{author_value}[/bold]:",
            ]
            for opt_idx, cand in enumerate(matching, 1):
                cand_name = cand.get("display") or cand.get("value") or ""
                cand_auth = cand.get("authority") or ""
                lines.append(f"{opt_idx}. {cand_name} (authority={cand_auth})")
            console.print(
                Panel(
                    "\n".join(lines),
                    title="Select authority to link",
                    border_style="cyan",
                )
            )

            while True:
                choice_raw = console.input(
                    "[bold]Enter number to link, or 0 to skip[/bold]: "
                ).strip()
                try:
                    choice = int(choice_raw)
                except ValueError:
                    console.print("[red]Please enter a valid number.[/red]")
                    continue

                if choice == 0:
                    console.print("[dim]Skipped by user (multiple matches).[/dim]")
                    skipped_user += 1
                    _log(
                        log_file,
                        f"SKIP item_uuid={item_uuid} title={title!r} uris={uris_str!r} "
                        f"author={author_value!r} reason=multiple_matches",
                    )
                    selected_entry = None
                    break

                if 1 <= choice <= len(matching):
                    selected_entry = matching[choice - 1]
                    break

                console.print("[red]Choice out of range.[/red]")

            if selected_entry is None:
                continue
        else:
            # Exactly one match; respect auto_link_single flag.
            selected_entry = matching[0]
            authority_uuid_preview = selected_entry.get("authority") or ""
            if not authority_uuid_preview:
                no_match_count += 1
                continue

            if not auto_link_single:
                # Require per-match confirmation for even single matches.
                detail_preview = await fetch_entry_detail(
                    client, vocabulary_name, authority_uuid_preview
                )
                orcid_preview = extract_orcid_from_entry(
                    selected_entry, detail_preview
                )
                lines = [
                    f"Author (item): [bold]{author_value}[/bold]",
                    f"Authority UUID: [bold]{authority_uuid_preview}[/bold]",
                ]
                if orcid_preview:
                    lines.append(
                        f"ORCID: [link={orcid_preview}]{orcid_preview}[/link]"
                    )
                console.print(
                    Panel(
                        "\n".join(lines),
                        title="Link this author to the above authority?",
                        border_style="cyan",
                    )
                )
                answer = console.input("[bold]Link? (y/n)[/bold]: ").strip().lower()
                if answer not in ("y", "yes"):
                    console.print("[dim]Skipped by user.[/dim]")
                    skipped_user += 1
                    _log(
                        log_file,
                        f"SKIP item_uuid={item_uuid} title={title!r} uris={uris_str!r} "
                        f"author={author_value!r} authority={authority_uuid_preview}",
                    )
                    continue

        authority_uuid = selected_entry.get("authority") or ""
        if not authority_uuid:
            no_match_count += 1
            continue

        detail = await fetch_entry_detail(client, vocabulary_name, authority_uuid)
        orcid_url = extract_orcid_from_entry(selected_entry, detail)

        # PATCH
        patch_value = {
            "value": author_value,
            "language": language,
            "authority": authority_uuid,
            "confidence": CONFIDENCE_LINKED,
        }
        operations = [
            {"op": "replace", "path": f"/metadata/{AUTHOR_FIELD}/{idx}", "value": patch_value}
        ]
        try:
            await _throttled_call(
                auth,
                client,
                username,
                password,
                throttle,
                lambda: client.patch_item(item_uuid, operations),
            )
            orcid_display = orcid_url or ""
            console.print(f"[green]Linked:[/green] {author_value!r}")
            linked_count += 1
            _log(
                log_file,
                f"LINK item_uuid={item_uuid} title={title!r} uris={uris_str!r} "
                f"author={author_value!r} authority={authority_uuid} orcid={orcid_display!r}",
            )
        except AuthenticationError as e:
            console.print(
                f"[red]Authentication error during PATCH for item {item_uuid}: {e}[/red]"
            )
            # Fatal: bubble up so the main loop can abort the run
            raise
        except Exception as e:
            console.print(f"[red]PATCH failed: {e}[/red]")

    return (linked_count, skipped_user, no_match_count)


async def main() -> None:
    """Interactive flow: URL and credentials first, then optional review-each, then item UUID or all items."""
    # --- 1. Base URL ---
    base_url = console.input(
        "[bold cyan]DSpace base URL[/bold cyan] [dim](press Enter for https://demo.dspace.org):[/dim] "
    ).strip()
    if not base_url:
        base_url = "https://demo.dspace.org"
        console.print("[dim]→ Using default: https://demo.dspace.org[/dim]")

    # --- 2. Credentials ---
    base_url_normalized = base_url.rstrip("/").lower()
    is_demo = "demo.dspace.org" in base_url_normalized
    if is_demo:
        console.print("[dim]Using demo credentials: dspacedemo+admin@gmail.com[/dim]")
        username = "dspacedemo+admin@gmail.com"
        password = "dspace"
    else:
        username = console.input("[bold cyan]Admin username:[/bold cyan] ").strip()
        password = getpass.getpass("Admin password: ")

    # --- 3. Vocabulary name ---
    vocab_input = console.input(
        f"[bold cyan]Author authority vocabulary[/bold cyan] [dim](press Enter for {DEFAULT_AUTHORITY_VOCABULARY}):[/dim] "
    ).strip()
    vocabulary_name = vocab_input or DEFAULT_AUTHORITY_VOCABULARY

    # --- 4. Throttle ---
    throttle_input = console.input(
        "[bold cyan]Throttle delay (seconds)[/bold cyan] [dim](press Enter for 1.0):[/dim] "
    ).strip()
    try:
        courtesy_delay = float(throttle_input) if throttle_input else 1.0
    except ValueError:
        courtesy_delay = 1.0

    # --- Authenticate and create client ---
    auth = DSpaceAuthClient(base_url)
    jwt, status = await auth.authenticate(username, password)
    if not jwt:
        console.print("[red]Authentication failed.[/red]")
        await auth.close()
        return

    client = DSpaceClient(
        base_url=base_url,
        jwt_token=jwt,
        csrf_token=auth.csrf_token,
        http_client=auth.client,
        target_versions=TARGET_VERSIONS,
        courtesy_delay=courtesy_delay,
    )

    # --- Adaptive throttle (single-threaded, delay-based) ---
    throttle_config = ThrottleConfig(initial_delay=courtesy_delay)
    throttle = ThrottleController(throttle_config)

    # --- 5. Exact or Fuzzy matching ---
    while True:
        match_mode = console.input(
            "[bold cyan]Match author names by: Exact or Fuzzy?[/bold cyan] (type [bold]Exact[/bold] or [bold]Fuzzy[/bold]): "
        ).strip()
        if match_mode.lower() == "exact":
            use_fuzzy = False
            break
        if match_mode.lower() == "fuzzy":
            console.print(
                "[yellow]Fuzzy matching may link publications to the wrong ORCID author.[/yellow]"
            )
            confirm = console.input(
                "[bold cyan]Continue with fuzzy matching?[/bold cyan] (Yes/No): "
            ).strip().lower()
            if confirm in ("yes", "y"):
                use_fuzzy = True
                break
            console.print("[dim]Please choose Exact or Fuzzy.[/dim]")
            continue
        console.print("[red]Please type exactly [bold]Exact[/bold] or [bold]Fuzzy[/bold].[/red]")

    # --- 6. Auto-link single unambiguous matches? ---
    review_ans = console.input(
        "[bold cyan]Allow automatic linking when there is exactly one local authority match?[/bold cyan] (y/n): "
    ).strip().lower()
    auto_link_single = review_ans in ("y", "yes")

    # --- 7. Item UUID (optional; empty = all items, newest first) ---
    item_uuid_input = (
        sys.argv[1].strip()
        if len(sys.argv) > 1
        else console.input(
            "[bold cyan]Item UUID[/bold cyan] [dim](press Enter to process all items, newest first):[/dim] "
        ).strip()
    )

    # --- 8. Incremental run mode (only for repository-wide runs) ---
    run_mode = "force"
    min_age_days: Optional[int] = None
    if not item_uuid_input:
        mode_input = console.input(
            "[bold cyan]Run mode[/bold cyan] "
            "[dim]([N]ew only, [S]ince days, [F]orce all; press Enter for New only):[/dim] "
        ).strip().lower()
        if mode_input in ("s", "since"):
            run_mode = "since"
            days_str = console.input(
                "[bold cyan]Re-run items not updated for at least how many days?[/bold cyan]: "
            ).strip()
            try:
                min_age_days = int(days_str)
            except ValueError:
                min_age_days = 0
        elif mode_input in ("f", "force"):
            run_mode = "force"
            min_age_days = None
        else:
            run_mode = "new"
            min_age_days = None

    # --- Log file ---
    log_dir = os.environ.get("LINK_AUTHOR_LOG_DIR", ".")
    log_filename = datetime.now().strftime("link_author_authorities_%Y-%m-%d_%H-%M-%S.log")
    log_path = os.path.join(log_dir, log_filename)
    try:
        log_file = open(log_path, "w", encoding="utf-8")
    except OSError as e:
        console.print(f"[yellow]Could not open log file {log_path}: {e}[/yellow]")
        log_file = None
    else:
        console.print(f"[dim]Log file: {log_path}[/dim]")

    # --- Incremental state (per item UUID) ---
    state_path = _get_state_path(log_dir)
    attempt_state = _load_attempt_state(state_path)
    now = datetime.now()

    total_linked = 0
    total_skipped = 0
    total_no_match = 0
    items_processed = 0

    try:
        if item_uuid_input:
            # Single item – no incremental mode questions, always attempt
            console.print(f"[cyan]Processing item {item_uuid_input}[/cyan]")
            linked, skipped, no_match = await process_item(
                auth,
                client,
                username,
                password,
                throttle,
                item_uuid_input,
                vocabulary_name,
                auto_link_single,
                use_fuzzy,
                log_file,
            )
            total_linked += linked
            total_skipped += skipped
            total_no_match += no_match
            items_processed = 1
        else:
            # All items (newest first)
            console.print("[cyan]Discovering all items (newest first)...[/cyan]")
            uuids = await discover_item_uuids_newest_first(
                auth, client, username, password, throttle
            )
            console.print(f"[cyan]Found {len(uuids)} item(s). Processing each.[/cyan]")
            for i, uuid in enumerate(uuids, 1):
                if not _should_process_uuid(uuid, run_mode, attempt_state, now, min_age_days):
                    console.print(
                        f"[dim]Item {i}/{len(uuids)}: {uuid} – skipped by incremental run mode.[/dim]"
                    )
                    continue

                console.print(f"[dim]Item {i}/{len(uuids)}: {uuid}[/dim]")
                linked, skipped, no_match = await process_item(
                    auth,
                    client,
                    username,
                    password,
                    throttle,
                    uuid,
                    vocabulary_name,
                    auto_link_single,
                    use_fuzzy,
                    log_file,
                )
                total_linked += linked
                total_skipped += skipped
                total_no_match += no_match
                items_processed += 1
                attempt_state[uuid] = now
                _append_attempt_state(state_path, uuid, now)
    except AuthenticationError as e:
        console.print(
            "[red]Fatal authentication error (e.g. CSRF/login refresh failed). "
            "Aborting run.[/red]"
        )
        console.print(f"[dim]{e}[/dim]")

        # --- Summary ---
        console.print("\n[bold cyan]Summary[/bold cyan]")
        console.print(f"  Items processed: {items_processed}")
        console.print(f"  Linked: {total_linked}")
        console.print(f"  Skipped (user said no): {total_skipped}")
        console.print(f"  No local match: {total_no_match}")

        if log_file is not None:
            _log(
                log_file,
                f"SUMMARY items_processed={items_processed} linked={total_linked} skipped={total_skipped} no_match={total_no_match}",
            )
    finally:
        if log_file is not None:
            log_file.close()
        await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
