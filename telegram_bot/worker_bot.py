"""
Worker Bot - Celery worker that processes tasks from RabbitMQ.

This bot:
- Runs Celery worker
- Pulls tasks from RabbitMQ
- Executes business logic
- Returns results via RabbitMQ
- Can be scaled horizontally (multiple instances)
"""

import logging
import sys
from decouple import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Start the Celery worker."""
    print("=" * 60)
    print("CELERY WORKER BOT - Task Processor")
    print("=" * 60)
    print()
    
    # Get RabbitMQ URL
    try:
        rabbitmq_url = config('RABBITMQ_URL', default='amqp://guest:guest@localhost:5672//')
    except:
        rabbitmq_url = 'amqp://guest:guest@localhost:5672//'
        logger.warning("RABBITMQ_URL not found in .env, using default")
    
    print(f"📡 RabbitMQ URL: {rabbitmq_url}")
    print()
    print("✅ Starting Celery worker...")
    print("✅ Workers will process tasks from RabbitMQ")
    print()
    print("⚡ Waiting for tasks from Coordinator Bot...")
    print("🔄 Worker will process tasks continuously...")
    print()
    print("💡 To stop: Press Ctrl+C")
    print()
    
    # Import Celery app
    from workers.celery_app import celery_app
    
    # Start Celery worker
    # This is equivalent to: celery -A workers.celery_app worker --loglevel=info
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=4',  # 4 concurrent tasks
        '--max-tasks-per-child=1000',  # Restart after 1000 tasks
        '--queues=search,content',  # Listen to both queues
    ])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Worker stopped")
        sys.exit(0)
