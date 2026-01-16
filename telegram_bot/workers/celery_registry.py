"""
Celery Worker Registry - Routes tasks through Celery

Uses Celery for distributed task execution with RabbitMQ.
"""

import logging
import uuid
from typing import Dict, Optional
from celery.result import AsyncResult
from .base_worker import Task, TaskResult
from .celery_tasks import TASK_MAP

logger = logging.getLogger(__name__)


class CeleryWorkerRegistry:
    """
    Celery-based worker registry.
    
    Coordinator side:
    - Submits tasks to Celery
    - Waits for results
    
    Worker side:
    - Celery workers execute tasks automatically
    """
    
    def __init__(self):
        """Initialize Celery registry."""
        logger.info("Initialized CeleryWorkerRegistry")
    
    async def execute_task(self, task: Task) -> TaskResult:
        """
        Execute task via Celery (coordinator side).
        
        Args:
            task: Task to execute
            
        Returns:
            TaskResult from worker
        """
        # Get Celery task function
        celery_task = TASK_MAP.get(task.task_type)
        
        if not celery_task:
            logger.error(f"No Celery task found for type '{task.task_type}'")
            return TaskResult(
                success=False,
                error=f"No task handler for type: {task.task_type}"
            )
        
        # Prepare task data
        task_data = {
            'task_id': task.task_id,
            'user_id': task.user_id,
            'task_type': task.task_type,
            'params': task.params
        }
        
        logger.info(
            f"Submitting task {task.task_id} (type: {task.task_type}) to Celery"
        )
        
        # Submit to Celery
        async_result = celery_task.apply_async(
            args=[task_data],
            task_id=task.task_id
        )
        
        # Wait for result (with timeout)
        try:
            result_dict = async_result.get(timeout=120)  # 2 minute timeout
            
            return TaskResult(
                success=result_dict['success'],
                data=result_dict.get('data'),
                error=result_dict.get('error'),
                metadata=result_dict.get('metadata', {})
            )
            
        except Exception as e:
            logger.exception(f"Error waiting for Celery result: {e}")
            return TaskResult(
                success=False,
                error=f"Task execution failed: {str(e)}"
            )
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """
        Get task status from Celery.
        
        Args:
            task_id: Task ID
            
        Returns:
            Status string (PENDING, STARTED, SUCCESS, FAILURE, RETRY)
        """
        result = AsyncResult(task_id)
        return result.state
    
    def get_worker_count(self) -> int:
        """
        Get number of active Celery workers.
        
        Returns:
            Worker count
        """
        from .celery_app import celery_app
        
        try:
            stats = celery_app.control.inspect().stats()
            if stats:
                return len(stats)
            return 0
        except Exception as e:
            logger.error(f"Error getting worker count: {e}")
            return 0
    
    def list_workers(self) -> list:
        """
        List active Celery workers.
        
        Returns:
            List of worker info
        """
        from .celery_app import celery_app
        
        try:
            stats = celery_app.control.inspect().stats()
            if not stats:
                return []
            
            workers = []
            for worker_name, worker_stats in stats.items():
                workers.append({
                    'name': worker_name,
                    'pool': worker_stats.get('pool', {}).get('implementation', 'unknown'),
                    'max_concurrency': worker_stats.get('pool', {}).get('max-concurrency', 0)
                })
            
            return workers
        except Exception as e:
            logger.error(f"Error listing workers: {e}")
            return []


# Global registry instance
_celery_registry: Optional[CeleryWorkerRegistry] = None


def get_celery_registry() -> CeleryWorkerRegistry:
    """
    Get the global Celery registry instance.
    
    Returns:
        CeleryWorkerRegistry singleton
    """
    global _celery_registry
    if _celery_registry is None:
        _celery_registry = CeleryWorkerRegistry()
    return _celery_registry


def reset_celery_registry() -> None:
    """Reset the global Celery registry (for testing)."""
    global _celery_registry
    _celery_registry = None
