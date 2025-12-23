"""
Batch Processor - Handles batch processing of creators with multithreading
"""

import asyncio
import logging
import time
from typing import List, Dict
from datetime import datetime
from concurrent.futures import as_completed
import random

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batch processing of creators with multithreading support."""
    
    def __init__(self, scraper_instance):
        """Initialize with reference to main scraper instance."""
        self.scraper = scraper_instance
    
    async def process_creators_list(self, creators: List[dict], phase_name: str):
        """Process a list of creators with the current settings."""
        total_creators = len(creators)
        total_batches = (total_creators + self.scraper.batch_size - 1) // self.scraper.batch_size
        
        logger.info(f"📊 {phase_name} processing: {total_creators} creators in {total_batches} batches")
        
        # Update stats
        self.scraper.stats['total_batches'] = total_batches
        self.scraper.stats['current_batch'] = 0
        
        # Process creators in batches
        for batch_idx in range(0, total_creators, self.scraper.batch_size):
            if not self.scraper.is_running:
                break
            
            batch = creators[batch_idx:batch_idx + self.scraper.batch_size]
            batch_num = (batch_idx // self.scraper.batch_size) + 1
            
            self.scraper.stats['current_batch'] = batch_num
            logger.info(f"📦 {phase_name} batch {batch_num}/{total_batches} ({len(batch)} creators)")
            
            # Process batch with multithreading
            await self._process_batch_multithreaded(batch, batch_num, total_batches)
            
            # Update performance stats
            self.scraper.performance_tracker.update_performance_stats(self.scraper.stats)
            
            # Adaptive delay between batches
            if batch_idx + self.scraper.batch_size < total_creators:
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
            future = self.scraper._thread_pool.submit(
                self._scrape_creator_sync_wrapper,
                creator['name'],
                creator['url']
            )
            futures.append((future, creator))
        
        # Update active workers count
        self.scraper.stats['active_workers'] = len(futures)
        
        # Process completed tasks as they finish
        completed = 0
        for future, creator in futures:
            if not self.scraper.is_running:
                break
            
            try:
                # Wait for completion with timeout
                success = future.result(timeout=120)  # 2 minute timeout per creator
                completed += 1
                
                if success:
                    self.scraper.stats['successful'] += 1
                    logger.debug(f"✅ {creator['name']} completed successfully ({completed}/{len(futures)})")
                else:
                    self.scraper.stats['failed'] += 1
                    self.scraper.retry_manager.add_failed_creator(creator, "Scraping failed")
                    logger.warning(f"❌ {creator['name']} failed ({completed}/{len(futures)})")
                
            except Exception as e:
                completed += 1
                self.scraper.stats['failed'] += 1
                self.scraper.retry_manager.add_failed_creator(creator, str(e))
                logger.error(f"💥 {creator['name']} error: {e} ({completed}/{len(futures)})")
        
        # Update stats
        self.scraper.stats['active_workers'] = 0
        
        batch_time = time.time() - batch_start_time
        logger.info(f"📦 Batch {batch_num}/{total_batches} completed in {batch_time:.1f}s")
    
    def _scrape_creator_sync_wrapper(self, creator_name: str, url: str) -> bool:
        """Synchronous wrapper for async scraping (for thread pool)."""
        loop = None
        try:
            # Check if we're in the main thread with an existing loop
            try:
                current_loop = asyncio.get_running_loop()
                # If we have a running loop, we need to run in a new thread
                if current_loop and current_loop.is_running():
                    # Use asyncio.run_coroutine_threadsafe to run in the main loop
                    future = asyncio.run_coroutine_threadsafe(
                        self.scraper.scrape_single_creator(creator_name, url),
                        current_loop
                    )
                    return future.result(timeout=120)
            except RuntimeError:
                # No running loop, we can create our own
                pass
            
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(self.scraper.scrape_single_creator(creator_name, url))
                return result
            finally:
                # Properly close the loop - make sure all tasks are done
                try:
                    # Give pending tasks a moment to complete
                    loop.run_until_complete(asyncio.sleep(0.1))
                    
                    # Cancel all pending tasks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    
                    # Wait for tasks to complete cancellation
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as cleanup_err:
                    logger.debug(f"Error during loop cleanup for {creator_name}: {cleanup_err}")
                finally:
                    # Close the loop
                    try:
                        loop.close()
                    except Exception as close_err:
                        logger.debug(f"Error closing loop for {creator_name}: {close_err}")
                
        except Exception as e:
            logger.error(f"Error in sync wrapper for {creator_name}: {e}")
            return False
        finally:
            # Ensure loop is closed even if exception occurs
            if loop and not loop.is_closed():
                try:
                    loop.close()
                except:
                    pass
    
    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay based on success rate and performance."""
        total_requests = self.scraper.stats['successful'] + self.scraper.stats['failed']
        if total_requests == 0:
            return 5.0  # Default delay
        
        success_rate = self.scraper.stats['successful'] / total_requests
        
        # Adjust delay based on success rate
        if success_rate > 0.9:  # Very good success rate
            return random.uniform(3.0, 5.0)
        elif success_rate > 0.7:  # Good success rate
            return random.uniform(5.0, 8.0)
        elif success_rate > 0.5:  # Moderate success rate
            return random.uniform(8.0, 12.0)
        else:  # Poor success rate - slow down significantly
            return random.uniform(15.0, 20.0)
    
    async def scrape_specific_creators(self, creator_names: List[str]) -> dict:
        """Enhanced manual scraping for specific creators."""
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
                csv_result = self.scraper.scraper.search_model_in_csv(name)
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
            future = self.scraper._thread_pool.submit(
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