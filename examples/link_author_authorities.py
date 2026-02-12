"""
Link item authors to local authority records (interactive).

Enhances an item that has dc.contributor.author in clear text by linking each
unlinked author to an authority already in this repository's SOLR authority core.
Uses the local vocabulary endpoint (e.g. CacheableAuthorAuthority) only — does
NOT search the public ORCID registry.

For each possible match the script pauses and asks for confirmation; only after
the user confirms is the update written to the REST API.

Run with the project venv (see README "Development")::
  source venv/bin/activate
  python examples/link_author_authorities.py [item-uuid]
  # or: ./venv/bin/python examples/link_author_authorities.py [item-uuid]
"""

import asyncio
import getpass
import sys
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


async def main() -> None:
    """Interactive flow: one item UUID, find unlinked authors, offer local authority match, confirm then PATCH."""
    # --- Input: item UUID ---
    item_uuid_input = (
        sys.argv[1].strip()
        if len(sys.argv) > 1
        else console.input("[bold cyan]Item UUID[/bold cyan]: ").strip()
    )
    if not item_uuid_input:
        console.print("[red]No item UUID provided.[/red]")
        return

    # --- Base URL and auth ---
    base_url = console.input(
        "[bold cyan]DSpace base URL[/bold cyan] [dim](press Enter for https://demo.dspace.org):[/dim] "
    ).strip()
    if not base_url:
        base_url = "https://demo.dspace.org"
        console.print("[dim]→ Using default: https://demo.dspace.org[/dim]")

    base_url_normalized = base_url.rstrip("/").lower()
    is_demo = "demo.dspace.org" in base_url_normalized
    if is_demo:
        console.print("[dim]Using demo credentials: dspacedemo+admin@gmail.com[/dim]")
        username = "dspacedemo+admin@gmail.com"
        password = "dspace"
    else:
        username = console.input("[bold cyan]Admin username:[/bold cyan] ").strip()
        password = getpass.getpass("Admin password: ")

    # --- Vocabulary name for local author authority ---
    vocab_input = console.input(
        f"[bold cyan]Author authority vocabulary[/bold cyan] [dim](press Enter for {DEFAULT_AUTHORITY_VOCABULARY}):[/dim] "
    ).strip()
    vocabulary_name = vocab_input or DEFAULT_AUTHORITY_VOCABULARY

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

    # --- Fetch item ---
    try:
        item = await client.get_item(item_uuid_input)
    except Exception as e:
        console.print(f"[red]Failed to get item: {e}[/red]")
        await auth.close()
        return

    metadata = item.get("metadata") or {}
    unlinked = get_unlinked_authors(metadata)
    if not unlinked:
        console.print("[green]No unlinked authors on this item; nothing to do.[/green]")
        await auth.close()
        return

    console.print(f"[cyan]Found {len(unlinked)} unlinked author(s).[/cyan]")
    linked_count = 0
    skipped_user = 0
    no_match_count = 0

    for idx, value_obj in unlinked:
        author_value = (value_obj.get("value") or "").strip()
        if not author_value:
            continue
        language = value_obj.get("language")
        normalized = normalize_name(author_value)

        # --- Search local authority only (vocabulary entries) ---
        try:
            resp = await client.get_vocabulary_entries(
                vocabulary_name,
                filter_term=author_value,
                exact=True,
                page=0,
                size=20,
            )
        except Exception as e:
            console.print(f"[red]Vocabulary lookup failed for '{author_value}': {e}[/red]")
            no_match_count += 1
            continue

        entries = (resp.get("_embedded") or {}).get("entries") or []
        # Exact match: entry display or value equals our author value (after normalizing)
        matching = [
            e
            for e in entries
            if isinstance(e, dict)
            and normalize_name((e.get("display") or e.get("value") or "")) == normalized
            and e.get("authority")
        ]
        if not matching:
            console.print(f"[yellow]No local authority match for: {author_value!r}[/yellow]")
            no_match_count += 1
            continue

        entry = matching[0]
        authority_uuid = entry.get("authority") or ""
        if not authority_uuid:
            no_match_count += 1
            continue

        # Optional: fetch detail for ORCID display
        detail = await fetch_entry_detail(client, vocabulary_name, authority_uuid)
        orcid_url = extract_orcid_from_entry(entry, detail)

        # --- Pause and ask for confirmation ---
        lines = [
            f"Author (item): [bold]{author_value}[/bold]",
            f"Authority UUID: [bold]{authority_uuid}[/bold]",
        ]
        if orcid_url:
            lines.append(f"ORCID: [link={orcid_url}]{orcid_url}[/link]")
        console.print(Panel("\n".join(lines), title="Link this author to the above authority?", border_style="cyan"))

        answer = console.input("[bold]Link? (y/n)[/bold]: ").strip().lower()
        if answer not in ("y", "yes"):
            console.print("[dim]Skipped by user.[/dim]")
            skipped_user += 1
            continue

        # --- PATCH: replace this metadata value with authority and confidence ---
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
            await client.patch_item(item_uuid_input, operations)
            console.print("[green]Linked.[/green]")
            linked_count += 1
        except Exception as e:
            console.print(f"[red]PATCH failed: {e}[/red]")

    # --- Summary ---
    console.print("\n[bold cyan]Summary[/bold cyan]")
    console.print(f"  Linked: {linked_count}")
    console.print(f"  Skipped (user said no): {skipped_user}")
    console.print(f"  No local match: {no_match_count}")
    await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
