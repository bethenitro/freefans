"""
Worker Bot - Processes tasks from distributed queue.

This bot:
- Pulls tasks from Redis queue
- Executes business logic
- Stores results back to Redis
- Can be scaled horizontally (multiple instances)
"""

import logging
import os
import sys
import asyncio
import signal
from decouple import config

# Import distributed registry
from workers.distributed_registry import get_distributed_registry

# Import workers
from workers.search_worker import SearchWorker
from workers.content_worker import ContentWorker

# Import business logic components
from core.content_manager import ContentManager
from managers.cache_factory import get_cache_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)


class DistributedWorkerBot:
    """Worker bot that processes tasks from Redis queue."""
    
    def __init__(self, redis_url: str):
        """
        Initialize distributed worker bot.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.registry = get_distributed_registry(redis_url)
        self.cache_manager = get_cache_manager()
        self.content_manager = ContentManager(self.cache_manager)
        self.running = False
        
        # Register all workers
        self._register_workers()
        
        logger.info("✅ Distributed Worker Bot initialized")
    
    def _register_workers(self):
        """Register all functional workers."""
        # Search Worker
        search_worker = SearchWorker(self.content_manager)
        self.registry.register_worker(search_worker)
        
        # Content Worker
        content_worker = ContentWorker(self.content_manager)
        self.registry.register_worker(content_worker)
        
        logger.info(f"✅ Registered {self.registry.get_worker_count()} workers")
        
        # Log registered workers
        for worker_info in self.registry.list_workers():
            logger.info(f"   - {worker_info['name']}: {worker_info['supported_tasks']}")
    
    async def start(self):
        """Start processing tasks from queue."""
        self.running = True
        logger.info("🚀 Worker Bot started - processing tasks from queue")
        
        try:
            # Start processing tasks (this blocks)
            await self.registry.process_tasks()
        except asyncio.CancelledError:
            logger.info("Worker Bot received cancellation signal")
        finally:
            self.running = False
    
    def stop(self):
        """Stop the worker bot."""
        logger.info("⏹️  Stopping Worker Bot...")
        self.running = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


async def main():
    """Main entry point for worker bot."""
    print("=" * 60)
    print("DISTRIBUTED WORKER BOT - Task Processor")
    print("=" * 60)
    print()
    
    # Get Redis URL
    try:
        redis_url = config('REDIS_URL', default='redis://localhost:6379')
    except:
        redis_url = 'redis://localhost:6379'
        logger.warning("REDIS_URL not found in .env, using default: redis://localhost:6379")
    
    print(f"📡 Redis URL: {redis_url}")
    print()
    
    # Initialize worker bot
    print("💾 Initializing cache manager...")
    worker_bot = DistributedWorkerBot(redis_url)
    
    print()
    print("✅ Worker Bot ready!")
    print("✅ All workers registered and operational")
    print()
    print("📊 Worker Status:")
    print(f"   - Total Workers: {worker_bot.registry.get_worker_count()}")
    print(f"   - Redis Connected: {redis_url}")
    print()
    print("⚡ Waiting for tasks from Coordinator Bot...")
    print("🔄 Worker Bot will process tasks continuously...")
    print()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker_bot.start()
    except KeyboardInterrupt:
        print("\n⏹️  Stopping Worker Bot...")
        worker_bot.stop()
        print("👋 Worker Bot shutdown complete")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Worker Bot stopped")
