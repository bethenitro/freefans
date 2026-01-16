# Distributed Deployment Guide (Celery + RabbitMQ)

## Architecture Overview

The bot uses **Celery + RabbitMQ** for distributed task processing:

```
┌─────────────────┐         ┌─────────────┐         ┌─────────────────┐
│  Coordinator    │────────▶│  RabbitMQ   │◀────────│  Worker(s)      │
│  Bot            │         │   Broker    │         │  (Celery)       │
│                 │         │             │         │                 │
│ - Telegram API  │         │ - Task Queue│         │ - Search        │
│ - User Sessions │         │ - Results   │         │ - Content Load  │
│ - Task Submit   │         └─────────────┘         │ - Business Logic│
└─────────────────┘                                 └─────────────────┘
```

## Prerequisites

1. **RabbitMQ Server** - Required for task queue
2. **Python 3.11+**
3. **Environment Variables** (`.env` file)

## Environment Variables

Create a `.env` file with:

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# RabbitMQ Connection
RABBITMQ_URL=amqp://guest:guest@localhost:5672//

# Supabase (if using)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Admin Setup Password
ADMIN_SETUP_PASSWORD=your_secure_password
```

## Deployment Options

### Option 1: Local Development

1. **Start RabbitMQ:**
   ```bash
   docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3-management
   ```
   
   Management UI: http://localhost:15672 (guest/guest)

2. **Start Coordinator Bot:**
   ```bash
   cd telegram_bot
   python coordinator_bot.py
   ```

3. **Start Worker Bot(s):**
   ```bash
   cd telegram_bot
   python worker_bot.py
   ```
   
   Or use Celery directly:
   ```bash
   celery -A workers.celery_app worker --loglevel=info --concurrency=4
   ```

### Option 2: Docker Deployment

1. **Build Images:**
   ```bash
   # Coordinator
   docker build -f Dockerfile.coordinator -t freefans-coordinator .
   
   # Worker
   docker build -f Dockerfile.worker -t freefans-worker .
   ```

2. **Run RabbitMQ:**
   ```bash
   docker run -d \
     --name freefans-rabbitmq \
     -p 5672:5672 \
     -p 15672:15672 \
     rabbitmq:3-management
   ```

3. **Run Coordinator:**
   ```bash
   docker run -d \
     --name freefans-coordinator \
     --env-file .env \
     -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672// \
     freefans-coordinator
   ```

4. **Run Worker(s):**
   ```bash
   # Worker 1
   docker run -d \
     --name freefans-worker-1 \
     --env-file .env \
     -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672// \
     freefans-worker
   
   # Worker 2 (optional - for scaling)
   docker run -d \
     --name freefans-worker-2 \
     --env-file .env \
     -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672// \
     freefans-worker
   ```

### Option 3: Separate Servers

**Server 1 (Coordinator + RabbitMQ):**
```bash
# Start RabbitMQ
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Start Coordinator
docker run -d \
  --name coordinator \
  --env-file .env \
  -e RABBITMQ_URL=amqp://guest:guest@localhost:5672// \
  freefans-coordinator
```

**Server 2+ (Workers):**
```bash
# Start Worker (point to Server 1's RabbitMQ)
docker run -d \
  --name worker \
  --env-file .env \
  -e RABBITMQ_URL=amqp://guest:guest@server1-ip:5672// \
  freefans-worker
```

## Scaling Workers

You can run multiple worker instances to handle more load:

```bash
# Start 3 workers
for i in {1..3}; do
  docker run -d \
    --name freefans-worker-$i \
    --env-file .env \
    -e RABBITMQ_URL=amqp://guest:guest@rabbitmq-server:5672// \
    freefans-worker
done
```

All workers will pull tasks from the same RabbitMQ queues automatically.

### Advanced: Different Worker Types

You can run specialized workers for different task types:

```bash
# Search-only worker
celery -A workers.celery_app worker --loglevel=info --queues=search

# Content-only worker
celery -A workers.celery_app worker --loglevel=info --queues=content

# All tasks worker
celery -A workers.celery_app worker --loglevel=info --queues=search,content
```

## Monitoring

### RabbitMQ Management UI
Access at http://localhost:15672 (guest/guest)
- View queues and message rates
- Monitor worker connections
- See task throughput

### Celery Monitoring

**Check active workers:**
```bash
celery -A workers.celery_app inspect active
```

**Check registered tasks:**
```bash
celery -A workers.celery_app inspect registered
```

**Check worker stats:**
```bash
celery -A workers.celery_app inspect stats
```

**Monitor in real-time with Flower:**
```bash
pip install flower
celery -A workers.celery_app flower
```
Access at http://localhost:5555

### View Logs
```bash
# Coordinator
docker logs -f freefans-coordinator

# Worker
docker logs -f freefans-worker-1
```

## Production Recommendations

1. **RabbitMQ Clustering**: Use RabbitMQ cluster for high availability
2. **Multiple Workers**: Run at least 2-3 workers for redundancy
3. **Task Queues**: Separate queues for different task types (search, content)
4. **Monitoring**: Use Flower or Prometheus for monitoring
5. **Resource Limits**: Set memory/CPU limits in production
6. **Persistent Messages**: Configure RabbitMQ for message persistence
7. **Dead Letter Queue**: Configure DLQ for failed tasks

## Celery Configuration

The Celery app is configured in `workers/celery_app.py`:

- **Task timeout**: 2 minutes (hard limit)
- **Result expiry**: 5 minutes
- **Retry policy**: 3 retries with 5-second delay
- **Acknowledgment**: Late acknowledgment (after task completes)
- **Prefetch**: 1 task per worker at a time

## Task Queues

Tasks are routed to specific queues:

- **search** queue: `search_creator`, `search_simpcity`, `get_random_creator`
- **content** queue: `load_content`, `load_more_pages`

## Troubleshooting

### Workers not processing tasks
- Check RabbitMQ is running: `docker ps | grep rabbitmq`
- Verify RABBITMQ_URL environment variable
- Check worker logs for connection errors
- Verify queues exist in RabbitMQ management UI

### Tasks timing out
- Increase worker count
- Check worker resource usage (CPU/memory)
- Increase task timeout in `celery_app.py`

### Coordinator not responding
- Check Telegram API connectivity
- Verify bot token is correct
- Check RabbitMQ connection

### RabbitMQ connection refused
- Ensure RabbitMQ is running on correct port (5672)
- Check firewall rules
- Verify credentials (default: guest/guest)

## Architecture Benefits

✅ **Industry Standard**: Celery is battle-tested and widely used
✅ **Guaranteed Delivery**: Tasks persist in RabbitMQ
✅ **Acknowledgments**: Tasks aren't lost if worker crashes
✅ **Dead Letter Queues**: Failed tasks can be retried
✅ **Horizontal Scaling**: Add workers without touching coordinator
✅ **Task Routing**: Route different tasks to different workers
✅ **Monitoring**: Built-in monitoring with Flower
✅ **Retries**: Automatic retry on failure
