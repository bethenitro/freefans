"""
Background Scraper - Periodically scrapes and updates cache for popular creators
Enhanced with multithreading, intelligent batching, and advanced rate limiting
"""

import asyncio
import logging
import threading
import time
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from cache_manager import CacheManager
from content_scraper import SimpleCityScraper
from scrapers.csv_handler import get_all_creators_from_csv
import random

logger = logging.getLogger(__name__)


class BackgroundScraper:
    """Enhanced background scraper with multithreading and intelligent rate limiting."""
    
    def __init__(
        self, 
        cache_manager: CacheManager,
        scraper: SimpleCityScraper,
        refresh_interval_hours: int = 12,
        max_pages_per_creator: int = None,
        batch_size: int = 3,
        max_workers: int = 4,
        concurrent_requests: int = 3
    ):
        """
        Initialize enhanced background scraper.
        
        Args:
            cache_manager: CacheManager instance
            scraper: SimpleCityScraper instance
            refresh_interval_hours: Hours between refresh cycles (default 12)
            max_pages_per_creator: Maximum pages to scrape per creator (None = all pages)
            batch_size: Number of creators to scrape in each batch (default 3)
            max_workers: Maximum number of worker threads (default 4)
            concurrent_requests: Maximum concurrent HTTP requests per worker (default 3)
        """
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
       
        # Track failed creators for retry with exponential backoff
        self.failed_creators = []
        self.retry_delays = {}  # Track retry delays per creator
        
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
            'processing_rate': 0.0,  # creators per minute
            'average_time_per_creator': 0.0,
            'active_workers': 0
        }
        
        # Performance tracking
        self._start_time = None
        self._creator_times = []
        self._lock = threading.Lock()
        
        # Smart caching state
        self._initial_cache_complete = False
        self._background_cache_complete = False
        self._cached_creators = set()  # Track which creators are already cached
    
    def _get_cached_creators_set(self) -> set:
        """Get set of already cached creator names."""
        try:
            cached_creators = self.cache_manager.get_all_cached_creators()
            return {creator['name'].lower() for creator in cached_creators}
        except Exception as e:
            logger.error(f"Error getting cached creators: {e}")
            return set()
    
    def _split_creators_by_cache_status(self, all_creators: List[dict]) -> Tuple[List[dict], List[dict]]:
        """
        Split creators into uncached (priority) and cached (background) lists.
        
        Returns:
            Tuple of (uncached_creators, cached_creators)
        """
        self._cached_creators = self._get_cached_creators_set()
        
        uncached_creators = []
        cached_creators = []
        
        for creator in all_creators:
            creator_name_lower = creator['name'].lower()
            if creator_name_lower in self._cached_creators:
                cached_creators.append(creator)
            else:
                uncached_creators.append(creator)
        
        logger.info(f"📊 Creator cache analysis:")
        logger.info(f"   • Uncached (priority): {len(uncached_creators)} creators")
        logger.info(f"   • Already cached: {len(cached_creators)} creators")
        
        return uncached_creators, cached_creators 
   
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
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._scraper_loop())
        except Exception as e:
            logger.error(f"Background scraper error: {e}", exc_info=True)
        finally:
            self.loop.close()
    
    async def _scraper_loop(self):
        """Enhanced scraper loop with smart background caching."""
        logger.info("Enhanced background scraper loop started")
        
        # Initial delay before first run (give bot time to start)
        await asyncio.sleep(60)
        
        # If we have background creators to process, do that first
        if hasattr(self, '_cached_creators_for_background') and not self._background_cache_complete:
            logger.info("🔄 Starting background caching for previously cached creators...")
            await self.continue_background_caching()
        
        while self.is_running:
            try:
                self.stats['current_status'] = 'running'
                self.stats['last_run'] = datetime.now().isoformat()
                
                logger.info("🔄 Starting periodic full refresh cycle...")
                await self._scrape_stale_creators()
                
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
  
    async def _scrape_stale_creators(self):
        """Enhanced scraping for periodic full refresh."""
        # Get ALL creators from CSV for complete refresh
        logger.info("🔄 Starting periodic full refresh...")
        all_creators = get_all_creators_from_csv(max_results=None)
        
        if not all_creators:
            logger.warning("No creators found in CSV")
            return
        
        # Shuffle creators to distribute load and avoid patterns
        random.shuffle(all_creators)
        
        logger.info(f"📊 Periodic refresh: {len(all_creators)} creators")
        
        # Clear tracking data
        self.failed_creators = []
        self.retry_delays = {}
        self._creator_times = []
        self._start_time = time.time()
        
        # Process all creators
        await self._process_creators_list(all_creators, "Periodic")
        
        # Enhanced retry logic
        await self._enhanced_retry_failed_creators()
        
        # Final performance report
        self._log_final_performance_report()
    
    async def _process_creators_list(self, creators: List[dict], phase_name: str):
        """Process a list of creators with the current settings."""
        total_creators = len(creators)
        total_batches = (total_creators + self.batch_size - 1) // self.batch_size
        
        logger.info(f"📊 {phase_name} processing: {total_creators} creators in {total_batches} batches")
        
        # Update stats
        self.stats['total_batches'] = total_batches
        self.stats['current_batch'] = 0
        
        # Process creators in batches
        for batch_idx in range(0, total_creators, self.batch_size):
            if not self.is_running:
                break
            
            batch = creators[batch_idx:batch_idx + self.batch_size]
            batch_num = (batch_idx // self.batch_size) + 1
            
            self.stats['current_batch'] = batch_num
            logger.info(f"📦 {phase_name} batch {batch_num}/{total_batches} ({len(batch)} creators)")
            
            # Process batch with multithreading
            await self._process_batch_multithreaded(batch, batch_num, total_batches)
            
            # Update performance stats
            self._update_performance_stats()
            
            # Adaptive delay between batches
            if batch_idx + self.batch_size < total_creators:
                delay = self._calculate_adaptive_delay()
                # Longer delays for background processing to not impact bot
                if phase_name == "Background":
                    delay *= 1.5
                logger.debug(f"⏱️  {phase_name} batch delay: {delay:.1f}s")
                await asyncio.sleep(delay)  
  
    async def _process_batch_multithreaded(self, creators: List[dict], batch_num: int, total_batches: int):
        """Process a batch of creators using multithreading."""
        batch_start_time = time.time()
        
        # Create tasks for thread pool
        futures = []
        for creator in creators:
            future = self._thread_pool.submit(
                self._scrape_creator_sync_wrapper,
                creator['name'],
                creator['url']
            )
            futures.append((future, creator))
        
        # Update active workers count
        with self._lock:
            self.stats['active_workers'] = len(futures)
        
        # Process completed tasks as they finish
        completed = 0
        for future, creator in futures:
            if not self.is_running:
                break
            
            try:
                # Wait for completion with timeout
                success = future.result(timeout=120)  # 2 minute timeout per creator
                completed += 1
                
                if success:
                    self.stats['successful'] += 1
                    logger.debug(f"✅ {creator['name']} completed successfully ({completed}/{len(futures)})")
                else:
                    self.stats['failed'] += 1
                    self._add_failed_creator(creator, "Scraping failed")
                    logger.warning(f"❌ {creator['name']} failed ({completed}/{len(futures)})")
                
            except Exception as e:
                completed += 1
                self.stats['failed'] += 1
                self._add_failed_creator(creator, str(e))
                logger.error(f"💥 {creator['name']} error: {e} ({completed}/{len(futures)})")
        
        # Update stats
        with self._lock:
            self.stats['active_workers'] = 0
        
        batch_time = time.time() - batch_start_time
        logger.info(f"📦 Batch {batch_num}/{total_batches} completed in {batch_time:.1f}s")
    
    def _scrape_creator_sync_wrapper(self, creator_name: str, url: str) -> bool:
        """Synchronous wrapper for async scraping (for thread pool)."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(self._scrape_single_creator(creator_name, url))
                return result
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Error in sync wrapper for {creator_name}: {e}")
            return False
    
    def _add_failed_creator(self, creator: dict, error: str):
        """Add creator to failed list with retry tracking."""
        creator_key = creator['name']
        
        # Initialize retry delay if not exists
        if creator_key not in self.retry_delays:
            self.retry_delays[creator_key] = 1.0  # Start with 1 second
        else:
            # Exponential backoff (max 60 seconds)
            self.retry_delays[creator_key] = min(60.0, self.retry_delays[creator_key] * 2)
        
        self.failed_creators.append({
            'name': creator['name'],
            'url': creator['url'],
            'error': error,
            'retry_delay': self.retry_delays[creator_key],
            'attempts': self.retry_delays[creator_key] // 2  # Rough attempt count
        })
    
    def _update_performance_stats(self):
        """Update performance statistics."""
        if not self._start_time:
            return
        
        elapsed_time = time.time() - self._start_time
        total_processed = self.stats['successful'] + self.stats['failed']
        
        if total_processed > 0 and elapsed_time > 0:
            self.stats['processing_rate'] = (total_processed / elapsed_time) * 60  # per minute
        
        if self._creator_times:
            self.stats['average_time_per_creator'] = sum(self._creator_times) / len(self._creator_times)
    
    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay based on success rate and performance."""
        total_requests = self.stats['successful'] + self.stats['failed']
        if total_requests == 0:
            return 5.0  # Default delay
        
        success_rate = self.stats['successful'] / total_requests
        
        # Adjust delay based on success rate
        if success_rate > 0.9:  # Very good success rate
            return random.uniform(3.0, 5.0)
        elif success_rate > 0.7:  # Good success rate
            return random.uniform(5.0, 8.0)
        elif success_rate > 0.5:  # Moderate success rate
            return random.uniform(8.0, 12.0)
        else:  # Poor success rate - slow down significantly
            return random.uniform(15.0, 20.0)
    
    def _log_final_performance_report(self):
        """Log comprehensive performance report."""
        total_time = time.time() - self._start_time if self._start_time else 0
        total_processed = self.stats['successful'] + self.stats['failed']
        
        logger.info("\n" + "="*60)
        logger.info("📊 FINAL PERFORMANCE REPORT")
        logger.info("="*60)
        logger.info(f"⏱️  Total time: {total_time/60:.1f} minutes")
        logger.info(f"📈 Total processed: {total_processed} creators")
        logger.info(f"✅ Successful: {self.stats['successful']} ({self.stats['successful']/total_processed*100:.1f}%)")
        logger.info(f"❌ Failed: {self.stats['failed']} ({self.stats['failed']/total_processed*100:.1f}%)")
        logger.info(f"🔄 Retries performed: {self.stats['retries']}")
        logger.info(f"⚡ Processing rate: {self.stats['processing_rate']:.1f} creators/minute")
        logger.info(f"⏱️  Average time per creator: {self.stats['average_time_per_creator']:.1f}s")
        logger.info("="*60)    

    async def _enhanced_retry_failed_creators(self, max_retries: int = 3):
        """Enhanced retry logic with exponential backoff and intelligent scheduling."""
        if not self.failed_creators:
            logger.info("✅ No failed creators to retry!")
            return
        
        logger.info(f"\n🔄 Starting enhanced retry for {len(self.failed_creators)} failed creators...")
        
        for retry_round in range(max_retries):
            if not self.failed_creators or not self.is_running:
                break
            
            logger.info(f"\n📥 Retry round {retry_round + 1}/{max_retries}")
            
            # Sort by retry delay (shortest first) for intelligent scheduling
            self.failed_creators.sort(key=lambda x: x.get('retry_delay', 1.0))
            
            # Copy and clear failed list for this retry
            to_retry = self.failed_creators.copy()
            self.failed_creators = []
            
            # Group retries by delay for batch processing
            retry_groups = {}
            for creator in to_retry:
                delay = creator.get('retry_delay', 1.0)
                if delay not in retry_groups:
                    retry_groups[delay] = []
                retry_groups[delay].append(creator)
            
            # Process each delay group
            for delay, group in sorted(retry_groups.items()):
                if not self.is_running:
                    break
                
                logger.info(f"⏱️  Processing {len(group)} creators with {delay:.1f}s delay...")
                
                # Apply the delay before processing this group
                if delay > 1.0:
                    await asyncio.sleep(delay)
                
                # Process group in smaller batches
                retry_batch_size = max(1, self.batch_size // 2)  # Smaller batches for retries
                
                for i in range(0, len(group), retry_batch_size):
                    if not self.is_running:
                        break
                    
                    batch = group[i:i + retry_batch_size]
                    logger.info(f"🔄 Retry batch: {len(batch)} creators")
                    
                    # Process retry batch
                    await self._process_retry_batch(batch)
                    self.stats['retries'] += len(batch)
                    
                    # Short delay between retry batches
                    if i + retry_batch_size < len(group):
                        await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Log retry round results
            remaining_failures = len(self.failed_creators)
            if remaining_failures == 0:
                logger.info(f"✅ All retries successful after round {retry_round + 1}!")
                break
            else:
                logger.info(f"⚠️  {remaining_failures} creators still failing after round {retry_round + 1}")
        
        # Final failure report
        if self.failed_creators:
            logger.warning(f"\n⚠️  {len(self.failed_creators)} creators failed after {max_retries} retry rounds:")
            for i, failed in enumerate(self.failed_creators[:10]):  # Show first 10
                logger.warning(f"  {i+1}. {failed['name']}: {failed['error']} (attempts: {failed.get('attempts', 'unknown')})")
            if len(self.failed_creators) > 10:
                logger.warning(f"  ... and {len(self.failed_creators) - 10} more")
        else:
            logger.info("\n✅ All creators processed successfully after retries!") 
   
    async def _process_retry_batch(self, creators: List[dict]):
        """Process a batch of retry creators."""
        tasks = []
        for creator in creators:
            task = self._scrape_single_creator(creator['name'], creator['url'])
            tasks.append((task, creator))
        
        # Execute with limited concurrency for retries
        semaphore = asyncio.Semaphore(2)  # More conservative for retries
        
        async def retry_with_semaphore(task, creator):
            async with semaphore:
                return await task, creator
        
        retry_tasks = [retry_with_semaphore(task, creator) for task, creator in tasks]
        results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Retry task exception: {result}")
                continue
            
            (success, creator) = result
            if isinstance(success, Exception):
                self.stats['failed'] += 1
                self._add_failed_creator(creator, str(success))
                logger.warning(f"Retry failed for {creator['name']}: {success}")
            elif success:
                self.stats['successful'] += 1
                logger.debug(f"✅ Retry successful for {creator['name']}")
            else:
                self.stats['failed'] += 1
                self._add_failed_creator(creator, "Retry scraping failed")
                logger.warning(f"❌ Retry failed for {creator['name']}")
    
    async def _scrape_single_creator(self, creator_name: str, url: str) -> bool:
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
            with self._lock:
                self._creator_times.append(elapsed_time)
                # Keep only recent times for rolling average
                if len(self._creator_times) > 100:
                    self._creator_times = self._creator_times[-50:]
            
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
        """
        Smart cache initialization: prioritize uncached creators first, then continue in background.
        
        Args:
            csv_path: Path to CSV file
            max_creators: Maximum number of creators to initially cache (None = all)
        """
        logger.info(f"🚀 Starting smart cache initialization...")
        logger.info(f"   • Max creators: {max_creators or 'unlimited'}")
        logger.info(f"   • Workers: {self.max_workers}")
        logger.info(f"   • Batch size: {self.batch_size}")
        
        try:
            # Get creators from CSV
            all_creators = get_all_creators_from_csv(csv_path, max_results=max_creators)
            
            if not all_creators:
                logger.warning("No creators found in CSV")
                return
            
            # Split creators by cache status
            uncached_creators, cached_creators = self._split_creators_by_cache_status(all_creators)
            
            # Shuffle for better load distribution
            random.shuffle(uncached_creators)
            random.shuffle(cached_creators)
            
            # Initialize tracking
            self.failed_creators = []
            self.retry_delays = {}
            self._creator_times = []
            self._start_time = time.time()
            
            # Phase 1: Process uncached creators first (PRIORITY - blocks bot startup)
            if uncached_creators:
                logger.info(f"\n🎯 PHASE 1: Processing {len(uncached_creators)} uncached creators (PRIORITY)")
                logger.info("⏸️  Bot startup will wait for this phase to complete")
                
                await self._process_creators_list(uncached_creators, "Priority")
                
                # Enhanced retry for priority creators
                if self.failed_creators:
                    logger.info(f"🔄 Retrying {len(self.failed_creators)} failed priority creators...")
                    await self._enhanced_retry_failed_creators(max_retries=2)
                
                self._initial_cache_complete = True
                logger.info(f"✅ PHASE 1 COMPLETE: Priority caching finished!")
            else:
                logger.info("✅ All creators already cached - skipping priority phase")
                self._initial_cache_complete = True
            
            # Store cached creators for background processing
            self._cached_creators_for_background = cached_creators
            
            # Final stats for priority phase
            priority_stats = self.cache_manager.get_cache_stats()
            total_time = time.time() - self._start_time
            
            logger.info(f"\n🎉 Smart cache initialization (Priority Phase) complete!")
            logger.info(f"   • Priority time: {total_time/60:.1f} minutes")
            logger.info(f"   • Total cached creators: {priority_stats['total_creators']}")
            logger.info(f"   • Content items: {priority_stats['total_content_items']}")
            if self.stats['successful'] + self.stats['failed'] > 0:
                logger.info(f"   • Success rate: {self.stats['successful']/(self.stats['successful']+self.stats['failed'])*100:.1f}%")
            logger.info(f"   • Background creators pending: {len(cached_creators)}")
            
        except Exception as e:
            logger.error(f"Error in smart cache initialization: {e}", exc_info=True) 
   
    async def continue_background_caching(self):
        """
        Continue caching for already-cached creators in the background after bot starts.
        This runs after the bot is operational.
        """
        if not hasattr(self, '_cached_creators_for_background'):
            logger.info("No background caching needed - all creators processed in priority phase")
            return
        
        cached_creators = self._cached_creators_for_background
        
        if not cached_creators:
            logger.info("No cached creators to refresh in background")
            self._background_cache_complete = True
            return
        
        logger.info(f"\n🔄 PHASE 2: Starting background refresh for {len(cached_creators)} cached creators")
        logger.info("✅ Bot is now operational - this runs in background")
        
        # Reset stats for background phase
        bg_start_time = time.time()
        bg_stats = {'successful': 0, 'failed': 0, 'total': len(cached_creators)}
        
        try:
            # Process cached creators with more conservative settings
            original_batch_size = self.batch_size
            original_max_workers = self.max_workers
            
            # Use smaller batches for background processing to not impact bot performance
            self.batch_size = max(1, self.batch_size // 2)
            self.max_workers = max(2, self.max_workers // 2)
            
            logger.info(f"🔧 Background settings: batch_size={self.batch_size}, workers={self.max_workers}")
            
            # Clear failed list for background processing
            self.failed_creators = []
            
            await self._process_creators_list(cached_creators, "Background")
            
            # Light retry for background creators (don't block too much)
            if self.failed_creators:
                logger.info(f"🔄 Light retry for {len(self.failed_creators)} failed background creators...")
                await self._enhanced_retry_failed_creators(max_retries=1)
            
            # Restore original settings
            self.batch_size = original_batch_size
            self.max_workers = original_max_workers
            
            self._background_cache_complete = True
            
            # Background phase stats
            bg_time = time.time() - bg_start_time
            bg_stats['successful'] = self.stats['successful']
            bg_stats['failed'] = self.stats['failed']
            
            logger.info(f"\n🎉 PHASE 2 COMPLETE: Background caching finished!")
            logger.info(f"   • Background time: {bg_time/60:.1f} minutes")
            logger.info(f"   • Refreshed: {bg_stats['successful']}/{bg_stats['total']} creators")
            if bg_stats['total'] > 0:
                logger.info(f"   • Background success rate: {bg_stats['successful']/bg_stats['total']*100:.1f}%")
            
        except Exception as e:
            logger.error(f"Error in background caching: {e}", exc_info=True)
            # Restore settings even on error
            self.batch_size = original_batch_size
            self.max_workers = original_max_workers 
   
    async def scrape_specific_creators(self, creator_names: List[str]) -> dict:
        """
        Enhanced manual scraping for specific creators.
        
        Args:
            creator_names: List of creator names to scrape
            
        Returns:
            Dict with detailed results
        """
        logger.info(f"🎯 Manual scraping requested for {len(creator_names)} creators")
        
        results = {
            'total': len(creator_names),
            'successful': 0,
            'failed': 0,
            'details': [],
            'start_time': datetime.now().isoformat(),
            'processing_time': 0.0
        }
        
        start_time = time.time()
        
        # Look up creators in CSV and prepare for scraping
        creators_to_scrape = []
        for name in creator_names:
            try:
                csv_result = self.scraper.search_model_in_csv(name)
                if csv_result:
                    creators_to_scrape.append({
                        'name': name,
                        'url': csv_result['url'],
                        'similarity': csv_result['similarity']
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'name': name, 
                        'status': 'not_found_in_csv',
                        'error': 'Creator not found in CSV database'
                    })
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'name': name, 
                    'status': 'csv_lookup_error',
                    'error': str(e)
                })
        
        if not creators_to_scrape:
            results['processing_time'] = time.time() - start_time
            return results
        
        logger.info(f"📋 Found {len(creators_to_scrape)} creators in CSV, starting scraping...")
        
        # Process creators using thread pool for better performance
        futures = []
        for creator in creators_to_scrape:
            future = self._thread_pool.submit(
                self._scrape_creator_sync_wrapper,
                creator['name'],
                creator['url']
            )
            futures.append((future, creator))
        
        # Collect results
        for future, creator in futures:
            try:
                success = future.result(timeout=120)  # 2 minute timeout
                
                if success:
                    results['successful'] += 1
                    results['details'].append({
                        'name': creator['name'],
                        'status': 'success',
                        'similarity': creator.get('similarity', 1.0)
                    })
                    logger.info(f"✅ Manual scrape successful: {creator['name']}")
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'name': creator['name'],
                        'status': 'scraping_failed',
                        'error': 'Content scraping returned no results'
                    })
                    logger.warning(f"❌ Manual scrape failed: {creator['name']}")
                    
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'name': creator['name'],
                    'status': 'error',
                    'error': str(e)
                })
                logger.error(f"💥 Manual scrape error for {creator['name']}: {e}")
        
        results['processing_time'] = time.time() - start_time
        
        logger.info(f"🎯 Manual scraping complete: {results['successful']}/{results['total']} successful")
        return results
    
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
            'pending_retries': len(self.failed_creators),
            'performance': {
                'processing_rate': self.stats['processing_rate'],
                'average_time_per_creator': self.stats['average_time_per_creator'],
                'active_workers': self.stats['active_workers']
            }
        }