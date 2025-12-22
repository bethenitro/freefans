"""
Performance Tracker - Tracks and reports performance metrics
"""

import logging
import threading
import time
from typing import List

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Tracks performance metrics and provides reporting."""
    
    def __init__(self):
        """Initialize performance tracking."""
        self._start_time = None
        self._creator_times = []
        self._lock = threading.Lock()
    
    def reset(self):
        """Reset performance tracking data."""
        with self._lock:
            self._start_time = time.time()
            self._creator_times = []
    
    def add_creator_time(self, elapsed_time: float):
        """Add timing data for a creator."""
        with self._lock:
            self._creator_times.append(elapsed_time)
            # Keep only recent times for rolling average
            if len(self._creator_times) > 100:
                self._creator_times = self._creator_times[-50:]
    
    def update_performance_stats(self, stats: dict):
        """Update performance statistics."""
        if not self._start_time:
            return
        
        elapsed_time = time.time() - self._start_time
        total_processed = stats['successful'] + stats['failed']
        
        if total_processed > 0 and elapsed_time > 0:
            stats['processing_rate'] = (total_processed / elapsed_time) * 60  # per minute
        
        if self._creator_times:
            stats['average_time_per_creator'] = sum(self._creator_times) / len(self._creator_times)
    
    def get_performance_stats(self) -> dict:
        """Get current performance statistics."""
        with self._lock:
            return {
                'processing_rate': 0.0,  # Will be updated by update_performance_stats
                'average_time_per_creator': sum(self._creator_times) / len(self._creator_times) if self._creator_times else 0.0,
                'active_workers': 0,  # Will be updated by batch processor
                'total_creator_times': len(self._creator_times)
            }
    
    def log_final_performance_report(self):
        """Log comprehensive performance report."""
        if not self._start_time:
            logger.info("No performance data to report")
            return
        
        total_time = time.time() - self._start_time
        
        logger.info("\n" + "="*60)
        logger.info("📊 FINAL PERFORMANCE REPORT")
        logger.info("="*60)
        logger.info(f"⏱️  Total time: {total_time/60:.1f} minutes")
        
        if self._creator_times:
            avg_time = sum(self._creator_times) / len(self._creator_times)
            logger.info(f"⏱️  Average time per creator: {avg_time:.1f}s")
            logger.info(f"📈 Total creators timed: {len(self._creator_times)}")
        
        logger.info("="*60)