"""
Core BackgroundScraper class - Main orchestrator for background scraping
"""

import asyncio
import logging
import threading
import time
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from managers.dual_cache_manager import DualCacheManager
from core.content_scraper import SimpleCityScraper
from scrapers.csv_handler import get_all_creators_from_csv
import random

from .batch_processor import BatchProcessor
from .retry_manager import RetryManager
from .performance_tracker import PerformanceTracker
from .cache_initializer import CacheInitializer

logger = logging.getLogger(__name__)


class BackgroundScraper:
    """Enhanced background scraper with modular components."""
    
    def __init__(
        self, 
        cache_manager: DualCacheManager,
        scraper: SimpleCityScraper,
        refresh_interval_hours: int = 12,
        max_pages_per_creator: int = None,
        batch_size: int = 3,
        max_workers: int = 4,
        concurrent_requests: int = 3
    ):
        """Initialize enhanced background scraper with modular components."""
        self.cache_manager = cache_manager
        self.scraper = scraper
        self.refresh_interval = timedelta(hours=refresh_interval_hours)
        self.max_pages = max_pages_per_creator
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.concurrent_requests = concurrent_requests
        
        self.is_running = False
        self.thread = None
        self.loop = None
        
        # Thread pool for parallel processing
        self._thread_pool = ThreadPoolExecutor(
            max_workers=max_workers, 
            thread_name_prefix="bg_scraper"
        )
        
        # Initialize modular components
        self.batch_processor = BatchProcessor(self)
        self.retry_manager = RetryManager(self)
        self.performance_tracker = PerformanceTracker()
        self.cache_initializer = CacheInitializer(self)
        
        # Enhanced statistics
        self.stats = {
            'total_scraped': 0,
            'successful': 0,
            'failed': 0,
            'retries': 0,
            'last_run': None,
            'next_run': None,
            'current_status': 'stopped',
            'current_batch': 0,
            'total_batches': 0,
            'processing_rate': 0.0,
            'average_time_per_creator': 0.0,
            'active_workers': 0
        }
        
        # Smart caching state
        self._initial_cache_complete = False
        self._background_cache_complete = False
        self._cached_creators = set()
    
    def start(self):
        """Start the enhanced background scraper."""
        if self.is_running:
            logger.warning("Background scraper is already running")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"✅ Enhanced background scraper started:")
        logger.info(f"   • Refresh interval: {self.refresh_interval.total_seconds()/3600}h")
        logger.info(f"   • Max workers: {self.max_workers}")
        logger.info(f"   • Batch size: {self.batch_size}")
        logger.info(f"   • Concurrent requests: {self.concurrent_requests}")
    
    def stop(self):
        """Stop the background scraper and cleanup resources."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Cleanup scraper resources if we have an event loop
        if self.loop and not self.loop.is_closed():
            try:
                # Schedule cleanup in the background loop
                future = asyncio.run_coroutine_threadsafe(self.scraper.close(), self.loop)
                future.result(timeout=5)  # Wait up to 5 seconds for cleanup
            except Exception as e:
                logger.warning(f"Error cleaning up scraper: {e}")
        
        # Shutdown thread pool
        logger.info("Shutting down thread pool...")
        self._thread_pool.shutdown(wait=True)
        
        if self.thread:
            self.thread.join(timeout=10)
        
        self.stats['current_status'] = 'stopped'
        logger.info("✅ Enhanced background scraper stopped")
    
    def _run_loop(self):
        """Run the scraper loop in a separate thread."""
        # Create new event loop for this thread
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Set up proper exception handling
            def exception_handler(loop, context):
                logger.error(f"Background scraper exception: {context}")
            
            self.loop.set_exception_handler(exception_handler)
            
            try:
                self.loop.run_until_complete(self._scraper_loop())
            except Exception as e:
                logger.error(f"Background scraper error: {e}", exc_info=True)
            finally:
                # Cleanup scraper resources first
                try:
                    self.loop.run_until_complete(self.scraper.close())
                except Exception as e:
                    logger.warning(f"Error cleaning up scraper in loop: {e}")
                
                # Properly cleanup the loop
                try:
                    # Cancel all pending tasks
                    pending = asyncio.all_tasks(self.loop)
                    if pending:
                        for task in pending:
                            task.cancel()
                        
                        # Wait for tasks to complete cancellation
                        self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                finally:
                    self.loop.close()
        except Exception as e:
            logger.error(f"Failed to create event loop for background scraper: {e}")
            self.stats['current_status'] = 'error'
    
    async def _scraper_loop(self):
        """Enhanced scraper loop with uncached-first caching strategy."""
        logger.info("Enhanced background scraper loop started")
        
        # Initial delay before first run (give bot time to start)
        await asyncio.sleep(60)
        
        # Cache all uncached creators first (in background, bot is already running)
        logger.info("🔄 Starting background caching of uncached creators...")
        try:
            await self.cache_initializer.cache_all_uncached_creators()
        except Exception as e:
            logger.error(f"Error caching uncached creators: {e}")
        
        while self.is_running:
            try:
                self.stats['current_status'] = 'running'
                self.stats['last_run'] = datetime.now().isoformat()
                
                logger.info("🔄 Starting periodic full refresh cycle (all creators)...")
                await self._scrape_all_creators()
                
                # Calculate next run time
                next_run = datetime.now() + self.refresh_interval
                self.stats['next_run'] = next_run.isoformat()
                self.stats['current_status'] = 'waiting'
                
                logger.info(f"✅ Periodic refresh complete. Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Wait until next refresh interval
                await asyncio.sleep(self.refresh_interval.total_seconds())
                
            except Exception as e:
                logger.error(f"Error in scraper loop: {e}", exc_info=True)
                self.stats['current_status'] = 'error'
                # Wait a bit before retrying on error
                await asyncio.sleep(300)  # 5 minutes
    
    async def _scrape_all_creators(self):
        """Enhanced scraping for periodic full refresh of ALL creators."""
        # Get ALL creators from CSV for complete refresh
        logger.info("🔄 Starting periodic full refresh (all creators)...")
        all_creators = get_all_creators_from_csv(max_results=None)
        
        if not all_creators:
            logger.warning("No creators found in CSV")
            return
        
        # Shuffle creators to distribute load and avoid patterns
        random.shuffle(all_creators)
        
        logger.info(f"📊 Periodic refresh: {len(all_creators)} total creators")
        
        # Reset tracking data
        self.retry_manager.reset()
        self.performance_tracker.reset()
        
        # Process all creators
        await self.batch_processor.process_creators_list(all_creators, "Periodic")
        
        # Enhanced retry logic
        await self.retry_manager.enhanced_retry_failed_creators()
        
        # Final performance report
        self.performance_tracker.log_final_performance_report()
    
    async def _scrape_stale_creators(self):
        """Enhanced scraping for periodic full refresh (deprecated - use _scrape_all_creators)."""
        await self._scrape_all_creators()
    
    async def scrape_single_creator(self, creator_name: str, url: str) -> bool:
        """Enhanced single creator scraping with timing and error handling."""
        start_time = time.time()
        
        try:
            logger.debug(f"📥 Scraping {creator_name}...")
            self.stats['total_scraped'] += 1
            
            # Scrape with enhanced error handling
            result = await self.scraper.scrape_creator_content(
                creator_name=creator_name,
                max_pages=self.max_pages,
                start_page=1,
                direct_url=url
            )
            
            if not result:
                logger.warning(f"No content returned for {creator_name}")
                return False
            
            # Process and cache results
            cache_data = self._prepare_cache_data(result)
            
            # Save to cache
            self.cache_manager.save_creator_cache(
                creator_name=result.get('creator_name', creator_name),
                url=url,
                content_data=cache_data
            )
            
            # Track timing
            elapsed_time = time.time() - start_time
            self.performance_tracker.add_creator_time(elapsed_time)
            
            pages_scraped = result.get('pages_scraped', 0)
            items_count = len(cache_data.get('items', []))
            
            logger.info(f"✅ {creator_name}: {items_count} items, {pages_scraped} pages ({elapsed_time:.1f}s)")
            return True
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ Error scraping {creator_name} after {elapsed_time:.1f}s: {e}")
            return False
    
    def _prepare_cache_data(self, result: dict) -> dict:
        """Prepare scraped data for caching with page numbers."""
        # Add page numbers to items for better organization
        items = result.get('content_items', [])
        for idx, item in enumerate(items):
            item['page_number'] = (idx // 20) + 1  # Assuming ~20 items per page
        
        preview_images = result.get('preview_images', [])
        for img in preview_images:
            img['page_number'] = 1  # Preview images typically on first page
        
        video_links = result.get('video_links', [])
        for video in video_links:
            video['page_number'] = 1  # Video links typically on first page
        
        return {
            'items': items,
            'preview_images': preview_images,
            'video_links': video_links,
            'total_pages': result.get('total_pages', result.get('pages_scraped', 0)),
            'social_links': result.get('social_links', {})
        }
    
    async def initialize_cache_from_csv(self, csv_path: str = 'onlyfans_models.csv', max_creators: int = None):
        """Smart cache initialization using the cache initializer component."""
        return await self.cache_initializer.initialize_cache_from_csv(csv_path, max_creators)
    
    async def scrape_specific_creators(self, creator_names: List[str]) -> dict:
        """Enhanced manual scraping for specific creators."""
        return await self.batch_processor.scrape_specific_creators(creator_names)
    
    def get_stats(self) -> dict:
        """Get enhanced scraper statistics."""
        cache_stats = self.cache_manager.get_cache_stats()
        
        # Calculate additional performance metrics
        total_processed = self.stats['successful'] + self.stats['failed']
        success_rate = (self.stats['successful'] / total_processed) if total_processed > 0 else 0
        
        return {
            **self.stats,
            'is_running': self.is_running,
            'cache_stats': cache_stats,
            'success_rate': success_rate,
            'total_processed': total_processed,
            'pending_retries': len(self.retry_manager.failed_creators),
            'performance': self.performance_tracker.get_performance_stats()
        }