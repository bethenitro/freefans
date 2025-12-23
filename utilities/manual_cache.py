#!/usr/bin/env python3
"""
Manual Cache Script - Independent caching mechanism for creator content
Run this script to manually cache creator content without starting the bot
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add telegram_bot to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'telegram_bot'))

from managers.cache_manager import CacheManager
from core.content_scraper import SimpleCityScraper
from scrapers.background_scraper import BackgroundScraper
from scrapers.csv_handler import get_all_creators_from_csv, preload_csv_cache
from decouple import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Reduce httpx logging noise
logging.getLogger('httpx').setLevel(logging.WARNING)


class ManualCacheManager:
    """Manual caching system that operates independently of the bot."""
    
    def __init__(self):
        """Initialize the manual cache manager."""
        print("🔧 Initializing Manual Cache Manager...")
        
        # Initialize cache manager
        self.cache_manager = CacheManager()
        
        # Initialize scraper
        self.scraper = SimpleCityScraper()
        
        # Get configuration from environment variables
        refresh_interval = int(config('CACHE_REFRESH_INTERVAL_HOURS', default=12))
        max_workers = int(config('SCRAPER_MAX_WORKERS', default=6))
        batch_size = int(config('SCRAPER_BATCH_SIZE', default=4))
        concurrent_requests = int(config('SCRAPER_CONCURRENT_REQUESTS', default=3))
        
        # Initialize background scraper (but don't start it)
        self.background_scraper = BackgroundScraper(
            cache_manager=self.cache_manager,
            scraper=self.scraper,
            refresh_interval_hours=refresh_interval,
            max_pages_per_creator=None,
            batch_size=batch_size,
            max_workers=max_workers,
            concurrent_requests=concurrent_requests
        )
        
        print(f"✅ Manual Cache Manager initialized")
        print(f"   • Max workers: {max_workers}")
        print(f"   • Batch size: {batch_size}")
        print(f"   • Concurrent requests: {concurrent_requests}")
    
    async def cache_all_creators(self, max_creators=None):
        """
        Cache all creators from CSV file.
        
        Args:
            max_creators: Maximum number of creators to cache (None for all)
        """
        print(f"\n🚀 Starting manual caching of all creators...")
        print(f"   • Max creators: {max_creators or 'unlimited'}")
        
        try:
            # Preload CSV cache
            print("📂 Preloading CSV cache...")
            count = preload_csv_cache()
            print(f"✅ Preloaded {count} models into CSV cache")
            
            # Set is_running flag to enable processing
            self.background_scraper.is_running = True
            
            # Initialize cache from CSV
            await self.background_scraper.initialize_cache_from_csv(max_creators=max_creators)
            
            # Stop running flag
            self.background_scraper.is_running = False
            
            # Get final stats
            stats = self.cache_manager.get_cache_stats()
            print(f"\n🎉 Manual caching complete!")
            print(f"   • Total cached creators: {stats['total_creators']}")
            print(f"   • Content items: {stats['total_content_items']}")
            print(f"   • Preview images: {stats['total_preview_images']}")
            print(f"   • Video links: {stats['total_video_links']}")
            print(f"   • Database size: {stats['database_size_mb']} MB")
            
        except Exception as e:
            logger.error(f"Error during manual caching: {e}", exc_info=True)
            print(f"❌ Manual caching failed: {e}")
    
    async def cache_uncached_creators_only(self, max_creators=None):
        """
        Cache only creators that are not already cached.
        
        Args:
            max_creators: Maximum number of creators to cache (None for all)
        """
        print(f"\n🎯 Starting manual caching of uncached creators only...")
        print(f"   • Max creators: {max_creators or 'unlimited'}")
        
        try:
            # Get all creators from CSV
            all_creators = get_all_creators_from_csv(max_results=max_creators)
            if not all_creators:
                print("❌ No creators found in CSV")
                return
            
            # Get already cached creators
            cached_creators = self.cache_manager.get_all_cached_creators()
            cached_names = {creator['name'].lower() for creator in cached_creators}
            
            # Filter to uncached creators only
            uncached_creators = [
                creator for creator in all_creators 
                if creator['name'].lower() not in cached_names
            ]
            
            print(f"📊 Cache analysis:")
            print(f"   • Total creators in CSV: {len(all_creators)}")
            print(f"   • Already cached: {len(cached_names)}")
            print(f"   • Uncached (to process): {len(uncached_creators)}")
            
            if not uncached_creators:
                print("✅ All creators are already cached!")
                return
            
            # Process uncached creators
            print(f"\n🔄 Processing {len(uncached_creators)} uncached creators...")
            
            # Set is_running flag to enable processing
            self.background_scraper.is_running = True
            
            # Use the batch processor to handle the uncached creators
            await self.background_scraper.batch_processor.process_creators_list(
                uncached_creators, "Manual-Uncached"
            )
            
            # Stop running flag
            self.background_scraper.is_running = False
            
            # Enhanced retry for failed creators
            if self.background_scraper.retry_manager.failed_creators:
                print(f"🔄 Retrying {len(self.background_scraper.retry_manager.failed_creators)} failed creators...")
                self.background_scraper.is_running = True
                await self.background_scraper.retry_manager.enhanced_retry_failed_creators(max_retries=2)
                self.background_scraper.is_running = False
            
            # Get final stats
            stats = self.cache_manager.get_cache_stats()
            print(f"\n🎉 Manual uncached-only caching complete!")
            print(f"   • Total cached creators: {stats['total_creators']}")
            print(f"   • Content items: {stats['total_content_items']}")
            print(f"   • Preview images: {stats['total_preview_images']}")
            print(f"   • Video links: {stats['total_video_links']}")
            print(f"   • Database size: {stats['database_size_mb']} MB")
            
        except Exception as e:
            logger.error(f"Error during uncached-only caching: {e}", exc_info=True)
            print(f"❌ Manual uncached-only caching failed: {e}")
    
    async def cache_specific_creators(self, creator_names):
        """
        Cache specific creators by name.
        
        Args:
            creator_names: List of creator names to cache
        """
        print(f"\n🎯 Starting manual caching of specific creators...")
        print(f"   • Creators: {', '.join(creator_names)}")
        
        try:
            # Use the background scraper's method for specific creators
            results = await self.background_scraper.scrape_specific_creators(creator_names)
            
            print(f"\n🎉 Manual specific creator caching complete!")
            print(f"   • Successful: {results['successful']}")
            print(f"   • Failed: {results['failed']}")
            print(f"   • Total processed: {results['total']}")
            
            if results['failed_creators']:
                print(f"   • Failed creators: {', '.join(results['failed_creators'])}")
            
        except Exception as e:
            logger.error(f"Error during specific creator caching: {e}", exc_info=True)
            print(f"❌ Manual specific creator caching failed: {e}")
    
    async def refresh_stale_creators(self, max_age_hours=24):
        """
        Refresh creators that haven't been updated recently.
        
        Args:
            max_age_hours: Consider creators stale if older than this many hours
        """
        print(f"\n🔄 Starting manual refresh of stale creators...")
        print(f"   • Max age: {max_age_hours} hours")
        
        try:
            # Get stale creators
            stale_creators = self.cache_manager.get_stale_creators(max_age_hours=max_age_hours)
            
            if not stale_creators:
                print("✅ No stale creators found!")
                return
            
            print(f"📊 Found {len(stale_creators)} stale creators to refresh")
            
            # Convert to the format expected by batch processor
            creators_to_refresh = [
                {'name': creator['name'], 'url': creator['url']}
                for creator in stale_creators
            ]
            
            # Set is_running flag to enable processing
            self.background_scraper.is_running = True
            
            # Process stale creators
            await self.background_scraper.batch_processor.process_creators_list(
                creators_to_refresh, "Manual-Stale"
            )
            
            # Stop running flag
            self.background_scraper.is_running = False
            
            # Enhanced retry for failed creators
            if self.background_scraper.retry_manager.failed_creators:
                print(f"🔄 Retrying {len(self.background_scraper.retry_manager.failed_creators)} failed creators...")
                self.background_scraper.is_running = True
                await self.background_scraper.retry_manager.enhanced_retry_failed_creators(max_retries=2)
                self.background_scraper.is_running = False
            
            # Get final stats
            stats = self.cache_manager.get_cache_stats()
            print(f"\n🎉 Manual stale creator refresh complete!")
            print(f"   • Total cached creators: {stats['total_creators']}")
            print(f"   • Content items: {stats['total_content_items']}")
            print(f"   • Database size: {stats['database_size_mb']} MB")
            
        except Exception as e:
            logger.error(f"Error during stale creator refresh: {e}", exc_info=True)
            print(f"❌ Manual stale creator refresh failed: {e}")
    
    def show_cache_stats(self):
        """Show current cache statistics."""
        print(f"\n📊 Current Cache Statistics:")
        
        try:
            stats = self.cache_manager.get_cache_stats()
            
            print(f"   • Cached creators: {stats['total_creators']}")
            print(f"   • Content items: {stats['total_content_items']}")
            print(f"   • Preview images: {stats['total_preview_images']}")
            print(f"   • Video links: {stats['total_video_links']}")
            print(f"   • OnlyFans users: {stats['total_onlyfans_users']}")
            print(f"   • OnlyFans posts: {stats['total_onlyfans_posts']}")
            print(f"   • Database size: {stats['database_size_mb']} MB")
            
            # Show some recent creators
            recent_creators = self.cache_manager.get_all_cached_creators()[:10]
            if recent_creators:
                print(f"\n📋 Recent cached creators:")
                for creator in recent_creators:
                    last_scraped = creator['last_scraped'][:19] if creator['last_scraped'] else 'Never'
                    print(f"   • {creator['name']} - {last_scraped} ({creator['item_count']} items)")
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            print(f"❌ Failed to get cache statistics: {e}")


async def smart_cache_all():
    """
    Smart caching: First cache uncached creators, then refresh already cached ones.
    This prioritizes adding new content before refreshing existing content.
    """
    print("="*80)
    print("🚀 SMART CACHE - Two-Phase Caching Strategy")
    print("="*80)
    print("Phase 1: Cache uncached creators (new content)")
    print("Phase 2: Refresh already cached creators (updates)")
    print("="*80)
    
    # Initialize manual cache manager
    manager = ManualCacheManager()
    
    try:
        # PHASE 1: Cache uncached creators first
        print("\n" + "="*80)
        print("📍 PHASE 1: Caching Uncached Creators")
        print("="*80)
        
        await manager.cache_uncached_creators_only(max_creators=None)
        
        # PHASE 2: Refresh already cached creators
        print("\n" + "="*80)
        print("📍 PHASE 2: Refreshing Already Cached Creators")
        print("="*80)
        
        await manager.refresh_stale_creators(max_age_hours=24)
        
        # Final summary
        print("\n" + "="*80)
        print("✅ SMART CACHE COMPLETE!")
        print("="*80)
        manager.show_cache_stats()
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n⏹️  Smart caching interrupted by user")
    except Exception as e:
        logger.error(f"Error in smart cache: {e}", exc_info=True)
        print(f"❌ Smart caching failed: {e}")


async def main():
    """Main function - runs smart caching automatically."""
    await smart_cache_all()


if __name__ == "__main__":
    asyncio.run(main())