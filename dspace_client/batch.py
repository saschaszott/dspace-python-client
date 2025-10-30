"""Batch item creation with adaptive concurrency control."""

import asyncio
import time
from typing import List, Dict, Optional, Tuple, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from .core import DSpaceClient, DSpaceAPIError
from .concurrency import ConcurrencyController, ConcurrencyConfig, PerformanceMetrics

console = Console()


class BatchItemCreator:
    """Creates items in batches with adaptive concurrency control."""
    
    def __init__(
        self,
        client: DSpaceClient,
        config: Optional[ConcurrencyConfig] = None,
    ):
        """
        Initialize batch item creator.
        
        Args:
            client: DSpace API client
            config: Concurrency configuration
        """
        self.client = client
        self.config = config or ConcurrencyConfig()
        self.controller = ConcurrencyController(self.config)
        
        # Track created items for progress
        self.created_items: List[Dict] = []
        self.created_bundles: List[Dict] = []
        self.created_bitstreams: List[Dict] = []
    
    async def create_items_batch(
        self,
        collection_uuids: List[str],
        item_data: List[Dict[str, Any]],
        progress: Optional[Progress] = None,
        task_id: Optional[int] = None,
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Create items in batches with adaptive concurrency.
        
        Args:
            collection_uuids: List of collection UUIDs to create items in
            item_data: List of item data dictionaries with keys:
                - title: Item title
                - metadata: Optional metadata dictionary
                - content: Optional binary content for bitstream
                - filename: Optional filename for bitstream
            progress: Rich progress bar (optional)
            task_id: Progress task ID (optional)
        
        Returns:
            Tuple of (created_items, created_bundles, created_bitstreams)
        """
        total_items = len(item_data)
        batch_size = 20  # Process in chunks of 20 for concurrency adjustment
        
        console.print(f"\n[cyan]Starting batch creation of {total_items} items with adaptive concurrency[/cyan]")
        console.print(f"[dim]Initial concurrency: {self.config.initial}, range: {self.config.min_concurrency}-{self.config.max_concurrency} (balanced ramp-up)[/dim]")
        
        # Clear previous results
        self.created_items.clear()
        self.created_bundles.clear()
        self.created_bitstreams.clear()
        
        # Create tasks for all items
        tasks = []
        for idx, item_info in enumerate(item_data):
            # Determine collection UUID (cycle through if needed)
            collection_uuid = collection_uuids[idx % len(collection_uuids)]
            
            # Create task for this item
            task = self._create_single_item_with_bitstream(
                item_info=item_info,
                collection_uuid=collection_uuid,
            )
            tasks.append(task)
        
        # Process tasks in batches
        completed = 0
        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i:i + batch_size]
            
            # Execute batch with concurrency control
            batch_results = await self._execute_batch_with_concurrency(batch_tasks)
            
            # Process results
            for result in batch_results:
                if result["success"]:
                    self.created_items.append(result["item"])
                    self.created_bundles.append(result["bundle"])
                    if result.get("bitstream"):
                        self.created_bitstreams.append(result["bitstream"])
                else:
                    console.print(f"[red]Failed to create item: {result['error']}[/red]")
            
            completed += len(batch_tasks)
            
            # Update progress
            if progress and task_id is not None:
                progress.update(task_id, advance=len(batch_tasks))
            
            # Show current metrics
            if completed % 50 == 0 or completed == total_items:
                await self._show_current_metrics(completed, total_items)
        
        console.print(f"[green]✓[/green] Batch creation complete: {len(self.created_items)} items created")
        return self.created_items, self.created_bundles, self.created_bitstreams
    
    async def _execute_batch_with_concurrency(self, tasks: List) -> List[Dict]:
        """Execute a batch of tasks with concurrency control."""
        semaphore = asyncio.Semaphore(self.controller.semaphore.current_limit)
        
        async def execute_with_semaphore(task):
            async with semaphore:
                start_time = time.time()
                try:
                    result = await task
                    duration = time.time() - start_time
                    await self.controller.record_operation(duration, success=True)
                    return {"success": True, **result}
                except Exception as e:
                    duration = time.time() - start_time
                    await self.controller.record_operation(duration, success=False)
                    return {"success": False, "error": str(e)}
        
        # Execute all tasks concurrently
        return await asyncio.gather(*[execute_with_semaphore(task) for task in tasks])
    
    async def _create_single_item_with_bitstream(
        self,
        item_info: Dict[str, Any],
        collection_uuid: str,
    ) -> Dict:
        """
        Create a single item with bundle and optional bitstream (atomic operation).
        
        This is the core operation that gets executed concurrently.
        """
        title = item_info["title"]
        metadata = item_info.get("metadata", {})
        content = item_info.get("content")
        filename = item_info.get("filename", "document.pdf")
        
        # Create item
        item = await self.client.create_item(
            name=title,
            owning_collection_uuid=collection_uuid,
            metadata=metadata,
        )
        
        # Create bundle
        bundle = await self.client.create_bundle(item["uuid"], "ORIGINAL")
        
        result = {
            "item": item,
            "bundle": bundle,
        }
        
        # Upload bitstream if content provided
        if content:
            bitstream = await self.client.upload_bitstream(
                bundle_uuid=bundle["uuid"],
                filename=filename,
                content=content,
            )
            result["bitstream"] = bitstream
        
        return result
    
    async def _show_current_metrics(self, completed: int, total: int):
        """Show current performance metrics."""
        metrics = await self.controller.get_metrics()
        
        # Format metrics
        throughput = f"{metrics.throughput:.1f}" if metrics.throughput > 0 else "0.0"
        p95_latency = f"{metrics.p95_latency * 1000:.0f}ms" if metrics.p95_latency > 0 else "0ms"
        concurrency = metrics.current_concurrency
        
        # Calculate progress percentage
        progress_pct = (completed / total) * 100 if total > 0 else 0
        
        console.print(
            f"\n[dim]Progress: {completed}/{total} ({progress_pct:.1f}%) | "
            f"Concurrency: {concurrency} | "
            f"Throughput: {throughput} items/s | "
            f"p95 Latency: {p95_latency}[/dim]"
        )
    
    async def get_final_metrics(self) -> PerformanceMetrics:
        """Get final performance metrics after batch creation."""
        return await self.controller.get_metrics()
    
    def get_created_counts(self) -> Dict[str, int]:
        """Get counts of created objects."""
        return {
            "items": len(self.created_items),
            "bundles": len(self.created_bundles),
            "bitstreams": len(self.created_bitstreams),
        }
