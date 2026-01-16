"""
Distributed Worker Registry - Routes tasks through Redis queue

Replaces in-process worker execution with distributed task queue.
"""

import logging
import uuid
from typing import Dict, Optional, List
from .base_worker import BaseWorker, Task, TaskResult
from .task_queue import get_task_queue, TaskQueue

logger = logging.getLogger(__name__)


class DistributedWorkerRegistry:
    """
    Distributed worker registry using Redis task queue.
    
    Coordinator side:
    - Submits tasks to queue
    - Waits for results
    
    Worker side:
    - Pulls tasks from queue
    - Executes and stores results
    """
    
    def __init__(self, redis_url: str = None):
        """
        Initialize distributed registry.
        
        Args:
            redis_url: Redis connection URL
        """
        self.task_queue = get_task_queue(redis_url)
        self._workers: Dict[str, BaseWorker] = {}  # Only used on worker side
        self._task_type_map: Dict[str, str] = {}
        logger.info("Initialized DistributedWorkerRegistry")
    
    def register_worker(self, worker: BaseWorker) -> None:
        """
        Register a worker (worker side only).
        
        Args:
            worker: Worker instance to register
        """
        worker_name = worker.worker_name
        
        if worker_name in self._workers:
            logger.warning(f"Worker '{worker_name}' already registered, replacing")
        
        self._workers[worker_name] = worker
        
        for task_type in worker.get_supported_tasks():
            if task_type in self._task_type_map:
                logger.warning(
                    f"Task type '{task_type}' already mapped to "
                    f"'{self._task_type_map[task_type]}', overriding with '{worker_name}'"
                )
            self._task_type_map[task_type] = worker_name
        
        logger.info(
            f"Registered worker '{worker_name}' with tasks: "
            f"{worker.get_supported_tasks()}"
        )
    
    async def execute_task(self, task: Task) -> TaskResult:
        """
        Execute task via distributed queue (coordinator side).
        
        Args:
            task: Task to execute
            
        Returns:
            TaskResult from worker
        """
        # Submit task to queue
        task_id = await self.task_queue.submit_task(task)
        
        logger.info(
            f"Submitted task {task_id} (type: {task.task_type}) to distributed queue"
        )
        
        # Wait for result (with timeout)
        result = await self.task_queue.get_result(task_id, timeout=120)
        
        if result is None:
            logger.error(f"Task {task_id} timed out")
            return TaskResult(
                success=False,
                error="Task execution timeout"
            )
        
        return result
    
    async def process_tasks(self) -> None:
        """
        Process tasks from queue (worker side).
        
        This runs in a loop, pulling tasks and executing them.
        Should be run in worker processes only.
        """
        logger.info("🔄 Starting task processing loop...")
        
        while True:
            try:
                # Get task from queue (blocking)
                task = await self.task_queue.get_task(timeout=5)
                
                if task is None:
                    continue
                
                logger.info(
                    f"Processing task {task.task_id} (type: {task.task_type})"
                )
                
                # Find worker for task
                worker = self.get_worker_for_task(task.task_type)
                
                if not worker:
                    logger.error(f"No worker for task type '{task.task_type}'")
                    result = TaskResult(
                        success=False,
                        error=f"No worker available for task type: {task.task_type}"
                    )
                else:
                    # Execute task
                    result = await worker.handle_task(task)
                
                # Store result
                await self.task_queue.store_result(task.task_id, result)
                
                logger.info(
                    f"Completed task {task.task_id} (success: {result.success})"
                )
                
            except KeyboardInterrupt:
                logger.info("Received interrupt, stopping task processing")
                break
            except Exception as e:
                logger.exception(f"Error processing task: {e}")
                # Continue processing next task
    
    def get_worker_for_task(self, task_type: str) -> Optional[BaseWorker]:
        """
        Get worker that handles a task type (worker side).
        
        Args:
            task_type: Type of task
            
        Returns:
            Worker instance or None
        """
        worker_name = self._task_type_map.get(task_type)
        if not worker_name:
            logger.error(f"No worker registered for task type '{task_type}'")
            return None
        return self._workers.get(worker_name)
    
    def list_workers(self) -> List[Dict]:
        """
        List registered workers (worker side).
        
        Returns:
            List of worker info
        """
        return [
            worker.get_worker_info()
            for worker in self._workers.values()
        ]
    
    def get_worker_count(self) -> int:
        """
        Get number of registered workers (worker side).
        
        Returns:
            Worker count
        """
        return len(self._workers)
    
    async def get_queue_stats(self) -> Dict:
        """
        Get queue statistics.
        
        Returns:
            Queue stats dictionary
        """
        queue_size = await self.task_queue.get_queue_size()
        return {
            'pending_tasks': queue_size,
            'registered_workers': len(self._workers)
        }


# Global registry instance
_distributed_registry: Optional[DistributedWorkerRegistry] = None


def get_distributed_registry(redis_url: str = None) -> DistributedWorkerRegistry:
    """
    Get the global distributed registry instance.
    
    Args:
        redis_url: Redis URL (only used on first call)
        
    Returns:
        DistributedWorkerRegistry singleton
    """
    global _distributed_registry
    if _distributed_registry is None:
        _distributed_registry = DistributedWorkerRegistry(redis_url)
    return _distributed_registry


def reset_distributed_registry() -> None:
    """Reset the global distributed registry (for testing)."""
    global _distributed_registry
    _distributed_registry = None
