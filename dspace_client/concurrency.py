"""Adaptive concurrency control for DSpace operations."""

import asyncio
import time
import statistics
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import deque


@dataclass
class ConcurrencyConfig:
    """Configuration for adaptive concurrency control."""
    initial: int = 4  # Balanced start
    min_concurrency: int = 1
    max_concurrency: int = 128
    ramp_up_threshold: float = 0.1  # 10% improvement
    ramp_down_threshold: float = 0.2  # 20% degradation
    window_size: int = 20  # Operations to track for metrics
    ramp_up_interval: int = 10  # Operations between ramp-up checks
    ramp_up_amount: int = 1  # Conservative ramp-up (1 at a time)
    ramp_down_amount: int = 1  # Conservative ramp-down (1 at a time)


@dataclass
class PerformanceMetrics:
    """Performance metrics for concurrency control."""
    throughput: float  # Operations per second
    p95_latency: float  # 95th percentile latency in seconds
    p50_latency: float  # 50th percentile latency in seconds
    current_concurrency: int
    total_operations: int
    successful_operations: int
    failed_operations: int


class AdaptiveSemaphore:
    """Dynamic semaphore that adjusts concurrency limit based on performance."""
    
    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.initial)
        self._current_limit = config.initial
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire the semaphore."""
        await self._semaphore.acquire()
    
    def release(self):
        """Release the semaphore."""
        self._semaphore.release()
    
    async def adjust_limit(self, new_limit: int):
        """Adjust the semaphore limit."""
        async with self._lock:
            new_limit = max(self.config.min_concurrency, 
                          min(self.config.max_concurrency, new_limit))
            
            if new_limit == self._current_limit:
                return
            
            # Calculate difference
            diff = new_limit - self._current_limit
            
            if diff > 0:
                # Increase limit - release more permits
                for _ in range(diff):
                    self._semaphore.release()
            else:
                # Decrease limit - acquire permits to reduce available
                for _ in range(-diff):
                    await self._semaphore.acquire()
            
            self._current_limit = new_limit
    
    @property
    def current_limit(self) -> int:
        """Get current concurrency limit."""
        return self._current_limit
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


class PerformanceMonitor:
    """Tracks performance metrics for adaptive concurrency control."""
    
    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        self.operation_times: deque = deque(maxlen=config.window_size)
        self.operation_timestamps: deque = deque(maxlen=config.window_size)
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self._lock = asyncio.Lock()
    
    async def record_operation(self, duration: float, success: bool = True):
        """Record an operation's timing and success status."""
        async with self._lock:
            current_time = time.time()
            self.operation_times.append(duration)
            self.operation_timestamps.append(current_time)
            self.total_operations += 1
            
            if success:
                self.successful_operations += 1
            else:
                self.failed_operations += 1
    
    async def get_metrics(self, current_concurrency: int) -> PerformanceMetrics:
        """Calculate current performance metrics."""
        async with self._lock:
            if not self.operation_times:
                return PerformanceMetrics(
                    throughput=0.0,
                    p95_latency=0.0,
                    p50_latency=0.0,
                    current_concurrency=current_concurrency,
                    total_operations=self.total_operations,
                    successful_operations=self.successful_operations,
                    failed_operations=self.failed_operations,
                )
            
            # Calculate throughput (operations per second)
            if len(self.operation_timestamps) >= 2:
                time_span = self.operation_timestamps[-1] - self.operation_timestamps[0]
                throughput = len(self.operation_times) / time_span if time_span > 0 else 0.0
            else:
                throughput = 0.0
            
            # Calculate latency percentiles
            sorted_times = sorted(self.operation_times)
            p50_latency = statistics.median(sorted_times)
            p95_latency = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0.0
            
            return PerformanceMetrics(
                throughput=throughput,
                p95_latency=p95_latency,
                p50_latency=p50_latency,
                current_concurrency=current_concurrency,
                total_operations=self.total_operations,
                successful_operations=self.successful_operations,
                failed_operations=self.failed_operations,
            )
    
    async def should_ramp_up(self) -> bool:
        """Check if we should ramp up concurrency."""
        if len(self.operation_times) < self.config.window_size:
            return False
        
        # Get recent metrics
        recent_times = list(self.operation_times)[-self.config.ramp_up_interval:]
        if len(recent_times) < self.config.ramp_up_interval:
            return False
        
        # Check if recent performance is good
        recent_p95 = statistics.quantiles(recent_times, n=20)[18]  # 95th percentile
        
        # More conservative: ramp up only if p95 latency is very reasonable (< 1.5 seconds)
        # and we have enough data points
        return recent_p95 < 1.5 and len(recent_times) >= 5
    
    async def should_ramp_down(self, current_metrics: PerformanceMetrics) -> bool:
        """Check if we should ramp down concurrency."""
        if len(self.operation_times) < self.config.window_size:
            return False
        
        # Get baseline metrics (first half of window)
        baseline_size = self.config.window_size // 2
        if len(self.operation_times) < baseline_size * 2:
            return False
        
        baseline_times = list(self.operation_times)[:baseline_size]
        recent_times = list(self.operation_times)[-baseline_size:]
        
        # Calculate baseline metrics
        baseline_p95 = statistics.quantiles(baseline_times, n=20)[18] if len(baseline_times) > 1 else 0
        baseline_throughput = len(baseline_times) / (baseline_times[-1] - baseline_times[0]) if len(baseline_times) > 1 else 0
        
        # Calculate recent metrics
        recent_p95 = statistics.quantiles(recent_times, n=20)[18] if len(recent_times) > 1 else 0
        recent_throughput = len(recent_times) / (recent_times[-1] - recent_times[0]) if len(recent_times) > 1 else 0
        
        # Check for degradation
        latency_degradation = (recent_p95 - baseline_p95) / baseline_p95 if baseline_p95 > 0 else 0
        throughput_degradation = (baseline_throughput - recent_throughput) / baseline_throughput if baseline_throughput > 0 else 0
        
        # More conservative: ramp down only if BOTH metrics show significant degradation
        # OR if latency is extremely high (> 3 seconds)
        return ((latency_degradation > self.config.ramp_down_threshold and 
                throughput_degradation > self.config.ramp_down_threshold) or
                recent_p95 > 3.0)


class ConcurrencyController:
    """Main controller for adaptive concurrency management."""
    
    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        self.config = config or ConcurrencyConfig()
        self.semaphore = AdaptiveSemaphore(self.config)
        self.monitor = PerformanceMonitor(self.config)
        self.operations_since_adjustment = 0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire concurrency slot."""
        await self.semaphore.acquire()
    
    def release(self):
        """Release concurrency slot."""
        self.semaphore.release()
    
    async def record_operation(self, duration: float, success: bool = True):
        """Record an operation and potentially adjust concurrency."""
        await self.monitor.record_operation(duration, success)
        
        async with self._lock:
            self.operations_since_adjustment += 1
            
            # Check if we should adjust concurrency
            should_adjust = (
                self.operations_since_adjustment >= self.config.ramp_up_interval or
                await self.monitor.should_ramp_down(await self.monitor.get_metrics(self.semaphore.current_limit))
            )
            
            if should_adjust:
                await self._adjust_concurrency()
                self.operations_since_adjustment = 0
    
    async def _adjust_concurrency(self):
        """Adjust concurrency based on current performance."""
        current_limit = self.semaphore.current_limit
        metrics = await self.monitor.get_metrics(current_limit)
        
        # Check if we should ramp down
        if await self.monitor.should_ramp_down(metrics):
            new_limit = max(
                self.config.min_concurrency,
                current_limit - self.config.ramp_down_amount
            )
            await self.semaphore.adjust_limit(new_limit)
            return
        
        # Check if we should ramp up
        if (self.operations_since_adjustment >= self.config.ramp_up_interval and
            await self.monitor.should_ramp_up()):
            new_limit = min(
                self.config.max_concurrency,
                current_limit + self.config.ramp_up_amount
            )
            await self.semaphore.adjust_limit(new_limit)
    
    async def get_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        return await self.monitor.get_metrics(self.semaphore.current_limit)
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
