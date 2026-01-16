"""
Task Queue - Distributed task queue using Redis

Enables coordinator and workers to run on separate servers.
"""

import json
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import redis.asyncio as redis
from .base_worker import Task, TaskResult

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Distributed task queue using Redis.
    
    Features:
    - Task submission from coordinator
    - Task consumption by workers
    - Result storage and retrieval
    - Task timeout handling
    """
    
    # Redis keys
    TASK_QUEUE_KEY = "freefans:tasks:queue"
    TASK_RESULT_PREFIX = "freefans:tasks:result:"
    TASK_STATUS_PREFIX = "freefans:tasks:status:"
    
    # Timeouts
    RESULT_TTL = 300  # Results expire after 5 minutes
    TASK_TIMEOUT = 120  # Tasks timeout after 2 minutes
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Initialize task queue.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        logger.info(f"Initialized TaskQueue with Redis URL: {redis_url}")
    
    async def connect(self) -> None:
        """Connect to Redis."""
        if self.redis_client is None:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("✅ Connected to Redis")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Disconnected from Redis")
    
    async def submit_task(self, task: Task) -> str:
        """
        Submit a task to the queue.
        
        Args:
            task: Task to submit
            
        Returns:
            Task ID
        """
        await self.connect()
        
        # Serialize task
        task_data = {
            'task_id': task.task_id,
            'user_id': task.user_id,
            'task_type': task.task_type,
            'params': task.params,
            'submitted_at': datetime.now().isoformat()
        }
        
        # Push to queue
        await self.redis_client.rpush(
            self.TASK_QUEUE_KEY,
            json.dumps(task_data)
        )
        
        # Set task status
        await self.redis_client.setex(
            f"{self.TASK_STATUS_PREFIX}{task.task_id}",
            self.RESULT_TTL,
            "pending"
        )
        
        logger.info(f"Submitted task {task.task_id} (type: {task.task_type}) to queue")
        return task.task_id
    
    async def get_task(self, timeout: int = 0) -> Optional[Task]:
        """
        Get a task from the queue (blocking).
        
        Args:
            timeout: Timeout in seconds (0 = block forever)
            
        Returns:
            Task or None if timeout
        """
        await self.connect()
        
        # Block and wait for task
        result = await self.redis_client.blpop(
            self.TASK_QUEUE_KEY,
            timeout=timeout
        )
        
        if not result:
            return None
        
        # Deserialize task
        _, task_json = result
        task_data = json.loads(task_json)
        
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        # Update status to processing
        await self.redis_client.setex(
            f"{self.TASK_STATUS_PREFIX}{task.task_id}",
            self.RESULT_TTL,
            "processing"
        )
        
        logger.info(f"Retrieved task {task.task_id} (type: {task.task_type}) from queue")
        return task
    
    async def store_result(self, task_id: str, result: TaskResult) -> None:
        """
        Store task result.
        
        Args:
            task_id: Task ID
            result: Task result
        """
        await self.connect()
        
        # Serialize result
        result_data = {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata,
            'completed_at': datetime.now().isoformat()
        }
        
        # Store result with TTL
        await self.redis_client.setex(
            f"{self.TASK_RESULT_PREFIX}{task_id}",
            self.RESULT_TTL,
            json.dumps(result_data)
        )
        
        # Update status
        status = "completed" if result.success else "failed"
        await self.redis_client.setex(
            f"{self.TASK_STATUS_PREFIX}{task_id}",
            self.RESULT_TTL,
            status
        )
        
        logger.info(f"Stored result for task {task_id} (success: {result.success})")
    
    async def get_result(self, task_id: str, timeout: int = 30) -> Optional[TaskResult]:
        """
        Get task result (with polling).
        
        Args:
            task_id: Task ID
            timeout: Maximum time to wait in seconds
            
        Returns:
            TaskResult or None if timeout
        """
        await self.connect()
        
        start_time = datetime.now()
        poll_interval = 0.5  # Poll every 500ms
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # Check if result exists
            result_json = await self.redis_client.get(
                f"{self.TASK_RESULT_PREFIX}{task_id}"
            )
            
            if result_json:
                # Deserialize result
                result_data = json.loads(result_json)
                return TaskResult(
                    success=result_data['success'],
                    data=result_data.get('data'),
                    error=result_data.get('error'),
                    metadata=result_data.get('metadata', {})
                )
            
            # Check if task failed/timed out
            status = await self.redis_client.get(
                f"{self.TASK_STATUS_PREFIX}{task_id}"
            )
            
            if status == "failed":
                return TaskResult(
                    success=False,
                    error="Task failed"
                )
            
            # Wait before next poll
            await asyncio.sleep(poll_interval)
        
        # Timeout
        logger.warning(f"Timeout waiting for result of task {task_id}")
        return TaskResult(
            success=False,
            error="Task timeout - no result received"
        )
    
    async def get_task_status(self, task_id: str) -> Optional[str]:
        """
        Get task status.
        
        Args:
            task_id: Task ID
            
        Returns:
            Status string or None
        """
        await self.connect()
        return await self.redis_client.get(f"{self.TASK_STATUS_PREFIX}{task_id}")
    
    async def get_queue_size(self) -> int:
        """
        Get number of pending tasks in queue.
        
        Returns:
            Queue size
        """
        await self.connect()
        return await self.redis_client.llen(self.TASK_QUEUE_KEY)
    
    async def clear_queue(self) -> None:
        """Clear all tasks from queue (for maintenance)."""
        await self.connect()
        await self.redis_client.delete(self.TASK_QUEUE_KEY)
        logger.info("Cleared task queue")


# Global task queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue(redis_url: str = None) -> TaskQueue:
    """
    Get the global task queue instance.
    
    Args:
        redis_url: Redis URL (only used on first call)
        
    Returns:
        TaskQueue singleton
    """
    global _task_queue
    if _task_queue is None:
        if redis_url is None:
            # Try to get from environment
            import os
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        _task_queue = TaskQueue(redis_url)
    return _task_queue


def reset_task_queue() -> None:
    """Reset the global task queue (for testing)."""
    global _task_queue
    if _task_queue:
        asyncio.create_task(_task_queue.disconnect())
    _task_queue = None
