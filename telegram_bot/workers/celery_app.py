"""
Celery Application Configuration

Configures Celery with RabbitMQ for distributed task processing.
"""

import os
from celery import Celery
from decouple import config

# Get RabbitMQ URL from environment
RABBITMQ_URL = config('RABBITMQ_URL', default='amqp://guest:guest@localhost:5672//')

# Create Celery app
celery_app = Celery(
    'freefans_workers',
    broker=RABBITMQ_URL,
    backend='rpc://',  # Use RabbitMQ as result backend
    include=[
        'workers.celery_tasks'
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Result backend settings
    result_expires=300,  # Results expire after 5 minutes
    result_persistent=False,
    
    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,
    task_time_limit=120,  # Hard limit: 2 minutes
    task_soft_time_limit=110,  # Soft limit: 1 minute 50 seconds
    
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    
    # Retry settings
    task_default_retry_delay=5,  # Retry after 5 seconds
    task_max_retries=3,
)

# Task routes (optional - for advanced routing)
celery_app.conf.task_routes = {
    'workers.celery_tasks.search_creator': {'queue': 'search'},
    'workers.celery_tasks.search_simpcity': {'queue': 'search'},
    'workers.celery_tasks.get_random_creator': {'queue': 'search'},
    'workers.celery_tasks.load_content': {'queue': 'content'},
    'workers.celery_tasks.load_more_pages': {'queue': 'content'},
}
