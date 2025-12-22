#!/usr/bin/env python3
"""
Cache Management Script - Utility for managing the content cache
"""

import asyncio
import argparse
import sys
from cache_manager import CacheManager
from background_scraper import BackgroundScraper
from content_scraper import SimpleCityScraper

def print_cache_stats(cache_manager):
    """Print cache statistics."""
    stats = cache_manager.get_cache_stats()
    
    print("\n📊 Cache Statistics:")
    print(f"  • Cached Creators: {stats['total_creators']}")
    print(f"  • Content Items: {stats['total_content_items']}")
    print(f"  • Preview Images: {stats['total_preview_images']}")
    print(f"  • Video Links: {stats['total_video_links']}")
    print(f"  • Database Size: {stats['database_size_mb']} MB")
    print()

def list_creators(cache_manager):
    """List all cached creators."""
    creators = cache_manager.get_all_cached_creators()
    
    if not creators:
        print("No creators in cache.")
        return
    
    print(f"\n📋 Cached Creators ({len(creators)}):")
    print("-" * 80)
    for i, creator in enumerate(creators, 1):
        last_scraped = creator['last_scraped'][:19] if creator['last_scraped'] else 'Never'
        print(f"{i:3}. {creator['name']:<30} | Items: {creator['item_count']:4} | "
              f"Pages: {creator['total_pages']:2} | Last: {last_scraped}")
    print()

def list_stale_creators(cache_manager, max_age_hours=24):
    """List creators that need refreshing."""
    stale = cache_manager.get_stale_creators(max_age_hours)
    
    if not stale:
        print(f"✅ No stale creators found (max age: {max_age_hours}h)")
        return
    
    print(f"\n⚠️  Stale Creators ({len(stale)}) - need refresh:")
    print("-" * 80)
    for i, creator in enumerate(stale, 1):
        last_scraped = creator['last_scraped'][:19] if creator['last_scraped'] else 'Never'
        print(f"{i:3}. {creator['name']:<30} | Last: {last_scraped}")
    print()

async def initialize_cache(cache_manager, max_creators=None):
    """Initialize cache with creators from CSV."""
    if max_creators:
        print(f"\n🔄 Initializing cache with up to {max_creators} creators...")
    else:
        print(f"\n🔄 Initializing cache with ALL creators from CSV...")
    
    scraper = SimpleCityScraper()
    background_scraper = BackgroundScraper(
        cache_manager=cache_manager,
        scraper=scraper,
        max_pages_per_creator=None,  # Scrape ALL pages (unlimited)
        batch_size=3  # Reduced for rate limiting
    )
    
    await background_scraper.initialize_cache_from_csv(max_creators=max_creators)
    
    print("✅ Cache initialization complete!")
    print_cache_stats(cache_manager)

async def refresh_stale(cache_manager, max_age_hours=24):
    """Refresh ALL creators (complete scrape)."""
    print(f"\n🔄 Starting COMPLETE refresh of ALL creators from CSV...")
    
    scraper = SimpleCityScraper()
    background_scraper = BackgroundScraper(
        cache_manager=cache_manager,
        scraper=scraper,
        max_pages_per_creator=None,  # Scrape ALL pages (unlimited)
        batch_size=3  # Reduced for rate limiting
    )
    
    # Get all creators for complete refresh
    from scrapers.csv_handler import get_all_creators_from_csv
    all_creators = get_all_creators_from_csv()
    
    if not all_creators:
        print("✅ No creators to refresh!")
        return
    
    print(f"Found {len(all_creators)} creators to refresh...")
    
    # Prepare creators for batch scraping
    creators_to_scrape = [
        {'name': c['name'], 'url': c['url']}
        for c in all_creators
    ]
    
    # Scrape in batches
    batch_size = 5
    for i in range(0, len(creators_to_scrape), batch_size):
        batch = creators_to_scrape[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(creators_to_scrape)-1)//batch_size + 1}...")
        await background_scraper._scrape_batch(batch)
        
        if i + batch_size < len(creators_to_scrape):
            await asyncio.sleep(5)
    
    print("✅ Complete refresh finished!")
    print_cache_stats(cache_manager)

async def scrape_specific(cache_manager, creator_names):
    """Scrape specific creators."""
    print(f"\n🔄 Scraping {len(creator_names)} specific creator(s)...")
    
    scraper = SimpleCityScraper()
    background_scraper = BackgroundScraper(
        cache_manager=cache_manager,
        scraper=scraper,
        max_pages_per_creator=3,
        batch_size=5
    )
    
    results = await background_scraper.scrape_specific_creators(creator_names)
    
    print("\n📊 Results:")
    print(f"  • Total: {results['total']}")
    print(f"  • Successful: {results['successful']}")
    print(f"  • Failed: {results['failed']}")
    
    if results['details']:
        print("\nDetails:")
        for detail in results['details']:
            status_emoji = {'success': '✅', 'failed': '❌', 'not_found': '❓', 'error': '⚠️'}
            emoji = status_emoji.get(detail['status'], '?')
            print(f"  {emoji} {detail['name']}: {detail['status']}")
    
    print()

def clear_cache(cache_manager, max_age_days=None):
    """Clear old cache entries."""
    if max_age_days:
        print(f"\n🧹 Clearing cache entries older than {max_age_days} days...")
        deleted = cache_manager.clear_old_cache(max_age_days)
        print(f"✅ Deleted {deleted} old entries")
    else:
        # Ask for confirmation to clear all
        response = input("\n⚠️  Are you sure you want to clear ALL cache? (yes/no): ")
        if response.lower() == 'yes':
            # Clear by setting max_age to 0 days
            deleted = cache_manager.clear_old_cache(0)
            print(f"✅ Cleared all cache ({deleted} entries deleted)")
        else:
            print("❌ Cancelled")
    
    print_cache_stats(cache_manager)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Manage FreeFans content cache')
    parser.add_argument('command', choices=[
        'stats', 'list', 'stale', 'init', 'refresh', 'scrape', 'clear'
    ], help='Command to execute')
    parser.add_argument('--max-creators', type=int, default=None,
                       help='Maximum creators for init (default: None = all)')
    parser.add_argument('--max-age', type=int, default=24,
                       help='Maximum age in hours for stale/refresh (default: 24, NOTE: refresh now does complete scrape)')
    parser.add_argument('--names', nargs='+',
                       help='Creator names for scrape command')
    parser.add_argument('--days', type=int,
                       help='Days for clear command (omit to clear all)')
    
    args = parser.parse_args()
    
    # Initialize cache manager
    cache_manager = CacheManager()
    
    # Execute command
    if args.command == 'stats':
        print_cache_stats(cache_manager)
    
    elif args.command == 'list':
        list_creators(cache_manager)
    
    elif args.command == 'stale':
        list_stale_creators(cache_manager, args.max_age)
    
    elif args.command == 'init':
        asyncio.run(initialize_cache(cache_manager, args.max_creators))
    
    elif args.command == 'refresh':
        print("⚠️  Note: Refresh now does a COMPLETE scrape of ALL creators")
        asyncio.run(refresh_stale(cache_manager, args.max_age))
    
    elif args.command == 'scrape':
        if not args.names:
            print("❌ Error: --names required for scrape command")
            sys.exit(1)
        asyncio.run(scrape_specific(cache_manager, args.names))
    
    elif args.command == 'clear':
        clear_cache(cache_manager, args.days)

if __name__ == '__main__':
    main()
