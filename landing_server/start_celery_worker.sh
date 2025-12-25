#!/bin/bash
# Start Celery worker for landing server background tasks

cd "$(dirname "$0")/.."

# Activate virtual environment if exists
if [ -d "../env" ]; then
    source ../env/bin/activate
fi

# Start Celery worker with appropriate settings
celery -A landing_server.services.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --max-tasks-per-child=1000 \
    --time-limit=300 \
    --soft-time-limit=240
