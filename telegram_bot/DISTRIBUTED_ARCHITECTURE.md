# Distributed Architecture

## Overview

The bot has been refactored from in-process workers to a **distributed task queue architecture** using Redis. This enables:

- **Horizontal scaling** of workers
- **Separate deployment** of coordinator and workers
- **Load distribution** across multiple worker instances
- **Fault tolerance** and resilience

## Components

### 1. Coordinator Bot (`coordinator_bot.py`)
**Responsibilities:**
- Handles ALL Telegram communication
- Manages user sessions
- Submits tasks to Redis queue
- Waits for and returns results to users

**Does NOT:**
- Execute business logic
- Perform searches or content loading
- Process heavy computations

### 2. Worker Bot(s) (`worker_bot.py`)
**Responsibilities:**
- Pulls tasks from Redis queue
- Executes business logic (search, content loading, etc.)
- Stores results back to Redis

**Does NOT:**
- Communicate with Telegram
- Manage user sessions
- Handle user interactions

### 3. Redis Queue
**Responsibilities:**
- Task queue storage
- Result storage (with TTL)
- Task status tracking

**Keys Used:**
- `freefans:tasks:queue` - Pending tasks
- `freefans:tasks:result:<task_id>` - Task results (5 min TTL)
- `freefans:tasks:status:<task_id>` - Task status (5 min TTL)

## Task Flow

```
1. User sends message to Telegram
   ↓
2. Coordinator receives update
   ↓
3. Coordinator creates Task and submits to Redis queue
   ↓
4. Worker pulls Task from Redis queue
   ↓
5. Worker executes business logic
   ↓
6. Worker stores TaskResult in Redis
   ↓
7. Coordinator retrieves TaskResult from Redis
   ↓
8. Coordinator sends response to user via Telegram
```

## Key Classes

### TaskQueue (`workers/task_queue.py`)
Handles Redis operations:
- `submit_task(task)` - Add task to queue
- `get_task(timeout)` - Pull task from queue (blocking)
- `store_result(task_id, result)` - Store task result
- `get_result(task_id, timeout)` - Retrieve result (with polling)

### DistributedWorkerRegistry (`workers/distributed_registry.py`)
Manages distributed task execution:
- **Coordinator side**: `execute_task()` - Submit and wait for result
- **Worker side**: `process_tasks()` - Continuous task processing loop

### Task & TaskResult (`workers/base_worker.py`)
Data structures for task communication:
```python
Task(
    task_id: str,
    user_id: int,
    task_type: str,
    params: dict
)

TaskResult(
    success: bool,
    data: dict,
    error: str,
    metadata: dict
)
```

## Supported Task Types

### SearchWorker
- `search_creator` - CSV search
- `search_simpcity` - Extended SimpCity search
- `get_random_creator` - Random creator selection

### ContentWorker
- `load_content` - Load creator content
- `load_more_pages` - Pagination

## Deployment Scenarios

### Scenario 1: Single Server (Development)
```
Server 1:
├── Redis (localhost:6379)
├── Coordinator Bot
└── Worker Bot
```

### Scenario 2: Two Servers (Small Production)
```
Server 1:
├── Redis (exposed on 6379)
└── Coordinator Bot

Server 2:
└── Worker Bot (connects to Server 1 Redis)
```

### Scenario 3: Multi-Server (Large Production)
```
Server 1:
├── Redis Cluster
└── Coordinator Bot

Server 2:
├── Worker Bot 1
└── Worker Bot 2

Server 3:
├── Worker Bot 3
└── Worker Bot 4
```

## Configuration

### Coordinator Bot
```env
TELEGRAM_BOT_TOKEN=<your_token>
REDIS_URL=redis://localhost:6379
```

### Worker Bot
```env
REDIS_URL=redis://localhost:6379
SUPABASE_URL=<your_url>
SUPABASE_KEY=<your_key>
```

## Scaling

### Horizontal Scaling
Add more worker instances:
```bash
# Worker 1
docker run -d --name worker-1 --env-file .env freefans-worker

# Worker 2
docker run -d --name worker-2 --env-file .env freefans-worker

# Worker 3
docker run -d --name worker-3 --env-file .env freefans-worker
```

All workers pull from the same queue - tasks are automatically distributed.

### Vertical Scaling
- Increase Redis memory
- Increase worker CPU/RAM
- Optimize task execution time

## Monitoring

### Queue Metrics
```python
# Get queue size
queue_size = await task_queue.get_queue_size()

# Get task status
status = await task_queue.get_task_status(task_id)
```

### Worker Health
- Monitor task processing rate
- Track task success/failure ratio
- Watch for stuck tasks (timeout)

## Advantages

✅ **Scalability**: Add workers without touching coordinator
✅ **Resilience**: Workers can crash/restart without losing tasks
✅ **Separation**: Deploy coordinator and workers independently
✅ **Load Balancing**: Automatic task distribution
✅ **Flexibility**: Different worker types on different servers

## Migration from In-Process

### Before (In-Process)
```python
# Coordinator directly calls worker
result = await worker.handle_task(task)
```

### After (Distributed)
```python
# Coordinator submits to queue
task_id = await task_queue.submit_task(task)
result = await task_queue.get_result(task_id)
```

Workers run in separate processes/servers and pull tasks automatically.

## Files Changed

### New Files
- `workers/task_queue.py` - Redis queue operations
- `workers/distributed_registry.py` - Distributed task routing
- `DEPLOYMENT.md` - Deployment guide
- `DISTRIBUTED_ARCHITECTURE.md` - This file

### Modified Files
- `coordinator_bot.py` - Uses DistributedWorkerRegistry
- `worker_bot.py` - Processes tasks from queue
- `requirements.txt` - Added redis[hiredis]

### Unchanged Files
- `workers/base_worker.py` - Task/TaskResult definitions
- `workers/search_worker/` - Search logic
- `workers/content_worker/` - Content logic
- All business logic remains the same
