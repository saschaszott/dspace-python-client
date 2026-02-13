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
import os
import sys
from datetime import datetime
from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel

from dspace_client import DSpaceAuthClient, DSpaceClient

# Compatible with DSpace 7.x, 8.x, 9.x (items PATCH and submission vocabularies)
TARGET_VERSIONS = ["7.0", "8.0", "9.0"]

# Default vocabulary for local author authority (SOLR cache); may be SolrAuthorAuthority on some instances
DEFAULT_AUTHORITY_VOCABULARY = "CacheableAuthorAuthority"

AUTHOR_FIELD = "dc.contributor.author"
CONFIDENCE_LINKED = 600

console = Console()


def normalize_name(s: str) -> str:
    """Normalize author name for exact match (strip, collapse spaces)."""
    if not s:
        return ""
    return " ".join(s.split())


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
    # Remove periods and collapse spaces, then rejoin with single space
    cleaned = " ".join(s.replace(".", " ").split()).upper()
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


async def discover_item_uuids_newest_first(client: DSpaceClient, page_size: int = 100) -> List[str]:
    """Discover all item UUIDs via discovery API, newest first. Paginates until no more results."""
    uuids: List[str] = []
    page = 0
    while True:
        results = await client.search_items(
            query="*",
            sort="dc.date.accessioned,desc",
            page=page,
            size=page_size,
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
    client: DSpaceClient,
    item_uuid: str,
    vocabulary_name: str,
    review_each_match: bool,
    use_fuzzy: bool,
    log_file: Optional[object],
) -> Tuple[int, int, int]:
    """
    Process one item: find unlinked authors, match to local authority, optionally prompt, PATCH.
    use_fuzzy: if True, allow abbreviated first names (e.g. "Smith, J." matches "Smith, John").
    Returns (linked_count, skipped_user, no_match_count).
    """
    try:
        item = await client.get_item(item_uuid)
    except Exception as e:
        console.print(f"[red]Failed to get item {item_uuid}: {e}[/red]")
        return (0, 0, 0)

    metadata = item.get("metadata") or {}
    unlinked = get_unlinked_authors(metadata)
    _log(log_file, f"ITEM {item_uuid} unlinked_count={len(unlinked)}")

    if not unlinked:
        return (0, 0, 0)

    console.print(f"[cyan]Item {item_uuid}: found {len(unlinked)} unlinked author(s).[/cyan]")

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
                        resp = await client.get_vocabulary_entries(
                            vocabulary_name,
                            filter_term=family,
                            exact=False,
                            page=page,
                            size=size,
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
                resp = await client.get_vocabulary_entries(
                    vocabulary_name,
                    filter_term=author_value,
                    exact=True,
                    page=0,
                    size=20,
                )
                entries = (resp.get("_embedded") or {}).get("entries") or []
                matching = [
                    e
                    for e in entries
                    if isinstance(e, dict)
                    and normalize_name((e.get("display") or e.get("value") or "")) == normalized
                    and e.get("authority")
                ]
        except Exception as e:
            console.print(f"[red]Vocabulary lookup failed for '{author_value}': {e}[/red]")
            no_match_count += 1
            _log(log_file, f"NO_MATCH item_uuid={item_uuid} author={author_value!r} reason=lookup_error")
            continue

        if not matching:
            console.print(f"[yellow]No local authority match for: {author_value!r}[/yellow]")
            no_match_count += 1
            _log(log_file, f"NO_MATCH item_uuid={item_uuid} author={author_value!r}")
            continue

        entry = matching[0]
        authority_uuid = entry.get("authority") or ""
        if not authority_uuid:
            no_match_count += 1
            continue

        detail = await fetch_entry_detail(client, vocabulary_name, authority_uuid)
        orcid_url = extract_orcid_from_entry(entry, detail)

        if review_each_match:
            lines = [
                f"Author (item): [bold]{author_value}[/bold]",
                f"Authority UUID: [bold]{authority_uuid}[/bold]",
            ]
            if orcid_url:
                lines.append(f"ORCID: [link={orcid_url}]{orcid_url}[/link]")
            console.print(
                Panel("\n".join(lines), title="Link this author to the above authority?", border_style="cyan")
            )
            answer = console.input("[bold]Link? (y/n)[/bold]: ").strip().lower()
            if answer not in ("y", "yes"):
                console.print("[dim]Skipped by user.[/dim]")
                skipped_user += 1
                _log(log_file, f"SKIP item_uuid={item_uuid} author={author_value!r} authority={authority_uuid}")
                continue

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
            await client.patch_item(item_uuid, operations)
            console.print("[green]Linked.[/green]")
            linked_count += 1
            _log(log_file, f"LINK item_uuid={item_uuid} author={author_value!r} authority={authority_uuid}")
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

    # --- 6. Review every ORCID match? ---
    review_ans = console.input(
        "[bold cyan]Do you want to review and approve every ORCID match?[/bold cyan] (y/n): "
    ).strip().lower()
    review_each_match = review_ans in ("y", "yes")

    # --- 7. Item UUID (optional; empty = all items, newest first) ---
    item_uuid_input = (
        sys.argv[1].strip()
        if len(sys.argv) > 1
        else console.input(
            "[bold cyan]Item UUID[/bold cyan] [dim](press Enter to process all items, newest first):[/dim] "
        ).strip()
    )

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

    total_linked = 0
    total_skipped = 0
    total_no_match = 0
    items_processed = 0

    try:
        if item_uuid_input:
            # Single item
            console.print(f"[cyan]Processing item {item_uuid_input}[/cyan]")
            linked, skipped, no_match = await process_item(
                client, item_uuid_input, vocabulary_name, review_each_match, use_fuzzy, log_file
            )
            total_linked += linked
            total_skipped += skipped
            total_no_match += no_match
            items_processed = 1
        else:
            # All items (newest first)
            console.print("[cyan]Discovering all items (newest first)...[/cyan]")
            uuids = await discover_item_uuids_newest_first(client)
            console.print(f"[cyan]Found {len(uuids)} item(s). Processing each.[/cyan]")
            for i, uuid in enumerate(uuids, 1):
                console.print(f"[dim]Item {i}/{len(uuids)}: {uuid}[/dim]")
                linked, skipped, no_match = await process_item(
                    client, uuid, vocabulary_name, review_each_match, use_fuzzy, log_file
                )
                total_linked += linked
                total_skipped += skipped
                total_no_match += no_match
                items_processed += 1

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
