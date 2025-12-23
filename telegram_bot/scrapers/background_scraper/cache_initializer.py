"""
Cache Initializer - Handles smart cache initialization and background caching
"""

import logging
import time
from typing import List, Tuple, Set
from scrapers.csv_handler import get_all_creators_from_csv
import random

logger = logging.getLogger(__name__)


class CacheInitializer:
    """Handles smart cache initialization with priority and background phases."""
    
    def __init__(self, scraper_instance):
        """Initialize with reference to main scraper instance."""
        self.scraper = scraper_instance
    
    def _get_cached_creators_set(self) -> Set[str]:
        """Get set of already cached creator names."""
        try:
            cached_creators = self.scraper.cache_manager.get_all_cached_creators()
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
        self.scraper._cached_creators = self._get_cached_creators_set()
        
        uncached_creators = []
        cached_creators = []
        
        for creator in all_creators:
            creator_name_lower = creator['name'].lower()
            if creator_name_lower in self.scraper._cached_creators:
                cached_creators.append(creator)
            else:
                uncached_creators.append(creator)
        
        logger.info(f"📊 Creator cache analysis:")
        logger.info(f"   • Uncached (priority): {len(uncached_creators)} creators")
        logger.info(f"   • Already cached: {len(cached_creators)} creators")
        
        return uncached_creators, cached_creators
    
    async def cache_uncached_creators_only(self, csv_path: str = 'onlyfans_models.csv', max_creators: int = None):
        """
        Cache only uncached creators - used for intelligent bot startup.
        
        Args:
            csv_path: Path to CSV file
            max_creators: Maximum number of creators to process (None = all)
        """
        logger.info(f"🧠 Starting intelligent caching (uncached creators only)...")
        logger.info(f"   • Max creators: {max_creators or 'unlimited'}")
        logger.info(f"   • Workers: {self.scraper.max_workers}")
        logger.info(f"   • Batch size: {self.scraper.batch_size}")
        
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
            
            # Initialize tracking
            self.scraper.retry_manager.reset()
            self.scraper.performance_tracker.reset()
            
            # Process only uncached creators
            if uncached_creators:
                logger.info(f"\n🎯 Processing {len(uncached_creators)} uncached creators (intelligent startup)")
                
                await self.scraper.batch_processor.process_creators_list(uncached_creators, "Intelligent")
                
                # Enhanced retry for uncached creators
                if self.scraper.retry_manager.failed_creators:
                    logger.info(f"🔄 Retrying {len(self.scraper.retry_manager.failed_creators)} failed creators...")
                    await self.scraper.retry_manager.enhanced_retry_failed_creators(max_retries=2)
                
                self.scraper._initial_cache_complete = True
                logger.info(f"✅ Intelligent caching complete!")
            else:
                logger.info("✅ All creators already cached - no startup caching needed")
                self.scraper._initial_cache_complete = True
            
            # Store cached creators for background processing (if any)
            self.scraper._cached_creators_for_background = cached_creators
            self.scraper._background_cache_complete = len(cached_creators) == 0
            
            # Final stats
            stats = self.scraper.cache_manager.get_cache_stats()
            total_time = time.time() - self.scraper.performance_tracker._start_time
            
            logger.info(f"\n🎉 Intelligent caching complete!")
            logger.info(f"   • Processing time: {total_time/60:.1f} minutes")
            logger.info(f"   • Total cached creators: {stats['total_creators']}")
            logger.info(f"   • Content items: {stats['total_content_items']}")
            if self.scraper.stats['successful'] + self.scraper.stats['failed'] > 0:
                logger.info(f"   • Success rate: {self.scraper.stats['successful']/(self.scraper.stats['successful']+self.scraper.stats['failed'])*100:.1f}%")
            logger.info(f"   • Background creators pending: {len(cached_creators)}")
            
        except Exception as e:
            logger.error(f"Error in intelligent caching: {e}", exc_info=True)

    async def initialize_cache_from_csv(self, csv_path: str = 'onlyfans_models.csv', max_creators: int = None):
        """
        Smart cache initialization: prioritize uncached creators first, then continue in background.
        
        Args:
            csv_path: Path to CSV file
            max_creators: Maximum number of creators to initially cache (None = all)
        """
        logger.info(f"🚀 Starting smart cache initialization...")
        logger.info(f"   • Max creators: {max_creators or 'unlimited'}")
        logger.info(f"   • Workers: {self.scraper.max_workers}")
        logger.info(f"   • Batch size: {self.scraper.batch_size}")
        
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
            self.scraper.retry_manager.reset()
            self.scraper.performance_tracker.reset()
            
            # Phase 1: Process uncached creators first (PRIORITY - blocks bot startup)
            if uncached_creators:
                logger.info(f"\n🎯 PHASE 1: Processing {len(uncached_creators)} uncached creators (PRIORITY)")
                logger.info("⏸️  Bot startup will wait for this phase to complete")
                
                await self.scraper.batch_processor.process_creators_list(uncached_creators, "Priority")
                
                # Enhanced retry for priority creators
                if self.scraper.retry_manager.failed_creators:
                    logger.info(f"🔄 Retrying {len(self.scraper.retry_manager.failed_creators)} failed priority creators...")
                    await self.scraper.retry_manager.enhanced_retry_failed_creators(max_retries=2)
                
                self.scraper._initial_cache_complete = True
                logger.info(f"✅ PHASE 1 COMPLETE: Priority caching finished!")
            else:
                logger.info("✅ All creators already cached - skipping priority phase")
                self.scraper._initial_cache_complete = True
            
            # Store cached creators for background processing
            self.scraper._cached_creators_for_background = cached_creators
            
            # Final stats for priority phase
            priority_stats = self.scraper.cache_manager.get_cache_stats()
            total_time = time.time() - self.scraper.performance_tracker._start_time
            
            logger.info(f"\n🎉 Smart cache initialization (Priority Phase) complete!")
            logger.info(f"   • Priority time: {total_time/60:.1f} minutes")
            logger.info(f"   • Total cached creators: {priority_stats['total_creators']}")
            logger.info(f"   • Content items: {priority_stats['total_content_items']}")
            if self.scraper.stats['successful'] + self.scraper.stats['failed'] > 0:
                logger.info(f"   • Success rate: {self.scraper.stats['successful']/(self.scraper.stats['successful']+self.scraper.stats['failed'])*100:.1f}%")
            logger.info(f"   • Background creators pending: {len(cached_creators)}")
            
        except Exception as e:
            logger.error(f"Error in smart cache initialization: {e}", exc_info=True)
    
    async def continue_background_caching(self):
        """
        Continue caching for already-cached creators in the background after bot starts.
        This runs after the bot is operational.
        """
        if not hasattr(self.scraper, '_cached_creators_for_background'):
            logger.info("No background caching needed - all creators processed in priority phase")
            return
        
        cached_creators = self.scraper._cached_creators_for_background
        
        if not cached_creators:
            logger.info("No cached creators to refresh in background")
            self.scraper._background_cache_complete = True
            return
        
        logger.info(f"\n🔄 PHASE 2: Starting background refresh for {len(cached_creators)} cached creators")
        logger.info("✅ Bot is now operational - this runs in background")
        
        # Reset stats for background phase
        bg_start_time = time.time()
        bg_stats = {'successful': 0, 'failed': 0, 'total': len(cached_creators)}
        
        try:
            # Process cached creators with more conservative settings
            original_batch_size = self.scraper.batch_size
            original_max_workers = self.scraper.max_workers
            
            # Use smaller batches for background processing to not impact bot performance
            self.scraper.batch_size = max(1, self.scraper.batch_size // 2)
            self.scraper.max_workers = max(2, self.scraper.max_workers // 2)
            
            logger.info(f"🔧 Background settings: batch_size={self.scraper.batch_size}, workers={self.scraper.max_workers}")
            
            # Clear failed list for background processing
            self.scraper.retry_manager.reset()
            
            await self.scraper.batch_processor.process_creators_list(cached_creators, "Background")
            
            # Light retry for background creators (don't block too much)
            if self.scraper.retry_manager.failed_creators:
                logger.info(f"🔄 Light retry for {len(self.scraper.retry_manager.failed_creators)} failed background creators...")
                await self.scraper.retry_manager.enhanced_retry_failed_creators(max_retries=1)
            
            # Restore original settings
            self.scraper.batch_size = original_batch_size
            self.scraper.max_workers = original_max_workers
            
            self.scraper._background_cache_complete = True
            
            # Background phase stats
            bg_time = time.time() - bg_start_time
            bg_stats['successful'] = self.scraper.stats['successful']
            bg_stats['failed'] = self.scraper.stats['failed']
            
            logger.info(f"\n🎉 PHASE 2 COMPLETE: Background caching finished!")
            logger.info(f"   • Background time: {bg_time/60:.1f} minutes")
            logger.info(f"   • Refreshed: {bg_stats['successful']}/{bg_stats['total']} creators")
            if bg_stats['total'] > 0:
                logger.info(f"   • Background success rate: {bg_stats['successful']/bg_stats['total']*100:.1f}%")
            
        except Exception as e:
            logger.error(f"Error in background caching: {e}", exc_info=True)
            # Restore settings even on error
            self.scraper.batch_size = original_batch_size
            self.scraper.max_workers = original_max_workers
    
    async def cache_all_uncached_creators(self, csv_path: str = 'onlyfans_models.csv'):
        """
        Cache ALL uncached creators in the background (after bot has started).
        This is the new primary caching strategy.
        
        Args:
            csv_path: Path to CSV file
        """
        logger.info(f"🚀 Starting background caching of all uncached creators...")
        
        try:
            # Get all creators from CSV
            all_creators = get_all_creators_from_csv(csv_path, max_results=None)
            
            if not all_creators:
                logger.warning("No creators found in CSV")
                return
            
            # Get uncached creators only
            self.scraper._cached_creators = self._get_cached_creators_set()
            uncached_creators = []
            
            for creator in all_creators:
                creator_name_lower = creator['name'].lower()
                if creator_name_lower not in self.scraper._cached_creators:
                    uncached_creators.append(creator)
            
            if not uncached_creators:
                logger.info("✅ All creators are already cached - nothing to do")
                return
            
            logger.info(f"📊 Found {len(uncached_creators)} uncached creators out of {len(all_creators)} total")
            
            # Shuffle for better load distribution
            random.shuffle(uncached_creators)
            
            # Reset tracking
            self.scraper.retry_manager.reset()
            self.scraper.performance_tracker.reset()
            start_time = time.time()
            
            # Process uncached creators
            logger.info(f"🎯 Processing {len(uncached_creators)} uncached creators in background...")
            await self.scraper.batch_processor.process_creators_list(uncached_creators, "Background Uncached")
            
            # Retry failed creators
            if self.scraper.retry_manager.failed_creators:
                logger.info(f"🔄 Retrying {len(self.scraper.retry_manager.failed_creators)} failed creators...")
                await self.scraper.retry_manager.enhanced_retry_failed_creators(max_retries=2)
            
            # Final stats
            total_time = time.time() - start_time
            stats = self.scraper.cache_manager.get_cache_stats()
            
            logger.info(f"\n🎉 Background caching of uncached creators complete!")
            logger.info(f"   • Processing time: {total_time/60:.1f} minutes")
            logger.info(f"   • Total cached creators now: {stats['total_creators']}")
            logger.info(f"   • Total content items: {stats['total_content_items']}")
            logger.info(f"   • Successfully cached: {self.scraper.stats['successful']} creators")
            logger.info(f"   • Failed: {self.scraper.stats['failed']} creators")
            if self.scraper.stats['successful'] + self.scraper.stats['failed'] > 0:
                success_rate = self.scraper.stats['successful']/(self.scraper.stats['successful']+self.scraper.stats['failed'])*100
                logger.info(f"   • Success rate: {success_rate:.1f}%")
            
        except Exception as e:
            logger.error(f"Error in background caching of uncached creators: {e}", exc_info=True)