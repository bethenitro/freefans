"""
Celery application for background tasks
"""
from celery import Celery
from decouple import config

# RabbitMQ broker URL
RABBITMQ_URL = config('RABBITMQ_URL', default='amqp://guest:guest@localhost:5672//')

# No result backend needed (we don't track task results)
# Redis result backend (optional, for task result storage)
# REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'landing_server',
    broker=RABBITMQ_URL,
    backend=None,  # No result backend (fire-and-forget tasks)
    include=['landing_server.services.celery_tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=4,  # How many tasks a worker grabs at once
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (prevent memory leaks)
    task_acks_late=True,  # Acknowledge task after completion (ensures retry on failure)
    task_reject_on_worker_lost=True,  # Requeue if worker crashes
)
