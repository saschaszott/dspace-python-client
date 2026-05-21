"""Tests for adaptive concurrency control."""

import asyncio
import time

import pytest

from dspace_client.concurrency import (
    AdaptiveDelayController,
    AdaptiveSemaphore,
    ConcurrencyConfig,
    PerformanceMonitor,
)


@pytest.mark.asyncio
async def test_adaptive_semaphore_ramp_up_increases_available_permits():
    config = ConcurrencyConfig(initial=2, min_concurrency=1, max_concurrency=8)
    semaphore = AdaptiveSemaphore(config)

    acquired = []
    for _ in range(2):
        await semaphore.acquire()
        acquired.append(True)

    await semaphore.adjust_limit(4)

    async def try_acquire():
        await semaphore.acquire()
        return True

    results = await asyncio.gather(try_acquire(), try_acquire())
    assert all(results)

    for _ in acquired:
        semaphore.release()
    for _ in results:
        semaphore.release()


@pytest.mark.asyncio
async def test_adaptive_semaphore_context_manager():
    config = ConcurrencyConfig(initial=1, max_concurrency=4)
    semaphore = AdaptiveSemaphore(config)

    async with semaphore:
        assert semaphore.current_limit == 1


@pytest.mark.asyncio
async def test_throughput_uses_timestamps_not_durations():
    """Throughput must not be computed from latency deltas (which can be negative)."""
    config = ConcurrencyConfig(window_size=10)
    monitor = PerformanceMonitor(config)

    base_time = time.time()
    for idx in range(10):
        # Decreasing durations would produce a negative denominator with the old bug.
        await monitor.record_operation(0.5 - idx * 0.04, success=True)
        monitor.operation_timestamps[-1] = base_time + idx

    metrics = await monitor.get_metrics(current_concurrency=4)
    assert metrics.throughput > 0


def test_adaptive_delay_controller_has_no_context_manager():
    controller = AdaptiveDelayController()
    assert not hasattr(controller, "acquire")
    assert not hasattr(controller, "release")
