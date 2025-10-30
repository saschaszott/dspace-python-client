"""Bulk import example with batch operations and concurrency control."""

import asyncio
import getpass
from rich.console import Console
from dspace_client import DSpaceAuthClient, DSpaceClient, BatchItemCreator, ConcurrencyConfig

console = Console()


async def main():
    """Demonstrate bulk import with adaptive concurrency."""
    
    # Interactive prompt for base URL
    base_url = console.input(
        "[bold cyan]DSpace base URL[/bold cyan] [dim](press Enter for https://demo.dspace.org):[/dim] "
    ).strip()
    
    if not base_url:
        base_url = "https://demo.dspace.org"
        console.print("[dim]→ Using default: https://demo.dspace.org[/dim]")
    
    # Auto-detect demo.dspace.org credentials
    base_url_normalized = base_url.rstrip("/").lower()
    is_demo = "demo.dspace.org" in base_url_normalized
    
    if is_demo:
        console.print("[dim]ℹ️  Using demo credentials: dspacedemo+admin@gmail.com[/dim]")
        username = "dspacedemo+admin@gmail.com"
        password = "dspace"
    else:
        username = console.input("[bold cyan]Admin username:[/bold cyan] ").strip()
        password = getpass.getpass("Admin password: ")
    
    # Authenticate
    auth = DSpaceAuthClient(base_url)
    jwt, status = await auth.authenticate(username, password)
    
    # Create client with version specification
    client = DSpaceClient(
        base_url=base_url,
        jwt_token=jwt,
        csrf_token=auth.csrf_token,
        http_client=auth.client,
        target_versions=["7.6", "8.0", "9.0"],  # Multi-version compatibility
    )
    
    # Create a community and collection for bulk import
    community = await client.create_community("Bulk Import Community")
    collection = await client.create_collection(
        name="Bulk Import Collection",
        parent_community_uuid=community["uuid"]
    )
    
    print(f"Created collection: {collection['uuid']}")
    
    # Configure concurrency for optimal performance
    config = ConcurrencyConfig(
        initial=8,  # Start with 8 concurrent operations
        max_concurrency=32,  # Allow up to 32 concurrent operations
        min_concurrency=2,   # Never go below 2
    )
    
    # Create batch item creator
    batch_creator = BatchItemCreator(client, config)
    
    # Generate sample item data
    item_data = []
    for i in range(100):  # Create 100 items
        item_data.append({
            "title": f"Bulk Item {i+1}",
            "metadata": {
                "dc.title": [{"value": f"Bulk Item {i+1}", "language": None, "authority": None, "confidence": -1}],
                "dc.description": [{"value": f"Description for bulk item {i+1}", "language": None, "authority": None, "confidence": -1}],
                "dc.subject": [{"value": f"Subject {i+1}", "language": None, "authority": None, "confidence": -1}]
            },
            "content": f"Sample content for item {i+1}".encode(),
            "filename": f"item_{i+1}.txt"
        })
    
    # Create items in batches with adaptive concurrency
    print(f"Creating {len(item_data)} items with adaptive concurrency...")
    
    items, bundles, bitstreams = await batch_creator.create_items_batch(
        collection_uuids=[collection["uuid"]],
        item_data=item_data
    )
    
    # Show final metrics
    metrics = await batch_creator.get_final_metrics()
    counts = batch_creator.get_created_counts()
    
    print(f"\nBulk import complete!")
    print(f"Items created: {counts['items']}")
    print(f"Bundles created: {counts['bundles']}")
    print(f"Bitstreams created: {counts['bitstreams']}")
    print(f"Final concurrency: {metrics.current_concurrency}")
    print(f"Average throughput: {metrics.throughput:.2f} items/second")
    print(f"P95 latency: {metrics.p95_latency:.3f} seconds")
    
    await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
