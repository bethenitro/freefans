# Distributed Deployment Guide

## Architecture Overview

The bot is now split into two components that communicate via Redis:

```
┌─────────────────┐         ┌─────────┐         ┌─────────────────┐
│  Coordinator    │────────▶│  Redis  │◀────────│  Worker(s)      │
│  Bot            │         │  Queue  │         │  Bot            │
│                 │         │         │         │                 │
│ - Telegram API  │         │ - Tasks │         │ - Search        │
│ - User Sessions │         │ - Results│        │ - Content Load  │
│ - Routing       │         └─────────┘         │ - Business Logic│
└─────────────────┘                             └─────────────────┘
```

## Prerequisites

1. **Redis Server** - Required for task queue
2. **Python 3.11+**
3. **Environment Variables** (`.env` file)

## Environment Variables

Create a `.env` file with:

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Redis Connection
REDIS_URL=redis://localhost:6379

# Supabase (if using)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Admin Setup Password
ADMIN_SETUP_PASSWORD=your_secure_password
```

## Deployment Options

### Option 1: Local Development

1. **Start Redis:**
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   ```

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

### Option 2: Docker Deployment

1. **Build Images:**
   ```bash
   # Coordinator
   docker build -f Dockerfile.coordinator -t freefans-coordinator .
   
   # Worker
   docker build -f Dockerfile.worker -t freefans-worker .
   ```

2. **Run Redis:**
   ```bash
   docker run -d \
     --name freefans-redis \
     -p 6379:6379 \
     redis:7-alpine
   ```

3. **Run Coordinator:**
   ```bash
   docker run -d \
     --name freefans-coordinator \
     --env-file .env \
     -e REDIS_URL=redis://host.docker.internal:6379 \
     freefans-coordinator
   ```

4. **Run Worker(s):**
   ```bash
   # Worker 1
   docker run -d \
     --name freefans-worker-1 \
     --env-file .env \
     -e REDIS_URL=redis://host.docker.internal:6379 \
     freefans-worker
   
   # Worker 2 (optional - for scaling)
   docker run -d \
     --name freefans-worker-2 \
     --env-file .env \
     -e REDIS_URL=redis://host.docker.internal:6379 \
     freefans-worker
   ```

### Option 3: Separate Servers

**Server 1 (Coordinator + Redis):**
```bash
# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Start Coordinator
docker run -d \
  --name coordinator \
  --env-file .env \
  -e REDIS_URL=redis://localhost:6379 \
  freefans-coordinator
```

**Server 2+ (Workers):**
```bash
# Start Worker (point to Server 1's Redis)
docker run -d \
  --name worker \
  --env-file .env \
  -e REDIS_URL=redis://server1-ip:6379 \
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
    -e REDIS_URL=redis://redis-server:6379 \
    freefans-worker
done
```

All workers will pull tasks from the same Redis queue automatically.

## Monitoring

### Check Queue Size
```bash
redis-cli LLEN freefans:tasks:queue
```

### Check Task Status
```bash
redis-cli GET freefans:tasks:status:<task_id>
```

### View Logs
```bash
# Coordinator
docker logs -f freefans-coordinator

# Worker
docker logs -f freefans-worker-1
```

## Production Recommendations

1. **Redis Persistence**: Use Redis with AOF or RDB persistence
2. **Multiple Workers**: Run at least 2-3 workers for redundancy
3. **Health Checks**: Monitor both coordinator and workers
4. **Resource Limits**: Set memory/CPU limits in production
5. **Separate Networks**: Use Docker networks or VPCs for security

## Troubleshooting

### Workers not processing tasks
- Check Redis connection: `redis-cli ping`
- Verify REDIS_URL environment variable
- Check worker logs for errors

### Tasks timing out
- Increase worker count
- Check worker resource usage
- Verify network connectivity to Redis

### Coordinator not responding
- Check Telegram API connectivity
- Verify bot token is correct
- Check Redis connection

## Architecture Benefits

✅ **Horizontal Scaling**: Add more workers as needed
✅ **Fault Tolerance**: Workers can restart without losing tasks
✅ **Separation**: Coordinator and workers on different servers
✅ **Load Distribution**: Tasks automatically distributed across workers
✅ **Independent Deployment**: Update coordinator or workers separately
