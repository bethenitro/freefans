"""
Retry Manager - Handles failed creator retries with exponential backoff
"""

import asyncio
import logging
import random
from typing import List, Dict

logger = logging.getLogger(__name__)


class RetryManager:
    """Manages retry logic for failed creators with exponential backoff."""
    
    def __init__(self, scraper_instance):
        """Initialize with reference to main scraper instance."""
        self.scraper = scraper_instance
        self.failed_creators = []
        self.retry_delays = {}  # Track retry delays per creator
    
    def reset(self):
        """Reset retry tracking data."""
        self.failed_creators = []
        self.retry_delays = {}
    
    def add_failed_creator(self, creator: dict, error: str):
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
    
    async def enhanced_retry_failed_creators(self, max_retries: int = 3):
        """Enhanced retry logic with exponential backoff and intelligent scheduling."""
        if not self.failed_creators:
            logger.info("✅ No failed creators to retry!")
            return
        
        logger.info(f"\n🔄 Starting enhanced retry for {len(self.failed_creators)} failed creators...")
        
        for retry_round in range(max_retries):
            if not self.failed_creators or not self.scraper.is_running:
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
                if not self.scraper.is_running:
                    break
                
                logger.info(f"⏱️  Processing {len(group)} creators with {delay:.1f}s delay...")
                
                # Apply the delay before processing this group
                if delay > 1.0:
                    await asyncio.sleep(delay)
                
                # Process group in smaller batches
                retry_batch_size = max(1, self.scraper.batch_size // 2)  # Smaller batches for retries
                
                for i in range(0, len(group), retry_batch_size):
                    if not self.scraper.is_running:
                        break
                    
                    batch = group[i:i + retry_batch_size]
                    logger.info(f"🔄 Retry batch: {len(batch)} creators")
                    
                    # Process retry batch
                    await self._process_retry_batch(batch)
                    self.scraper.stats['retries'] += len(batch)
                    
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
            task = self.scraper.scrape_single_creator(creator['name'], creator['url'])
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
                self.scraper.stats['failed'] += 1
                self.add_failed_creator(creator, str(success))
                logger.warning(f"Retry failed for {creator['name']}: {success}")
            elif success:
                self.scraper.stats['successful'] += 1
                logger.debug(f"✅ Retry successful for {creator['name']}")
            else:
                self.scraper.stats['failed'] += 1
                self.add_failed_creator(creator, "Retry scraping failed")
                logger.warning(f"❌ Retry failed for {creator['name']}")