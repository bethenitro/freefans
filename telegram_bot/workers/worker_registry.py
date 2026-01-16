"""
Worker Registry - Central registry for all functional workers

Manages worker instances and routes tasks to appropriate workers.
"""

from typing import Dict, Optional, List
import logging
from .base_worker import BaseWorker, Task, TaskResult

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """
    Central registry for managing all workers.
    
    Provides:
    - Worker registration
    - Task routing
    - Worker discovery
    """
    
    def __init__(self):
        """Initialize empty worker registry."""
        self._workers: Dict[str, BaseWorker] = {}
        self._task_type_map: Dict[str, str] = {}  # task_type -> worker_name
        logger.info("Initialized WorkerRegistry")
    
    def register_worker(self, worker: BaseWorker) -> None:
        """
        Register a worker in the registry.
        
        Args:
            worker: Worker instance to register
        """
        worker_name = worker.worker_name
        
        if worker_name in self._workers:
            logger.warning(f"Worker '{worker_name}' already registered, replacing")
        
        # Register worker
        self._workers[worker_name] = worker
        
        # Map task types to worker
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
    
    def unregister_worker(self, worker_name: str) -> bool:
        """
        Unregister a worker from the registry.
        
        Args:
            worker_name: Name of worker to unregister
            
        Returns:
            True if worker was unregistered, False if not found
        """
        if worker_name not in self._workers:
            logger.warning(f"Worker '{worker_name}' not found in registry")
            return False
        
        # Remove task type mappings
        worker = self._workers[worker_name]
        for task_type in worker.get_supported_tasks():
            if self._task_type_map.get(task_type) == worker_name:
                del self._task_type_map[task_type]
        
        # Remove worker
        del self._workers[worker_name]
        logger.info(f"Unregistered worker '{worker_name}'")
        return True
    
    def get_worker(self, worker_name: str) -> Optional[BaseWorker]:
        """
        Get a worker by name.
        
        Args:
            worker_name: Name of worker to retrieve
            
        Returns:
            Worker instance or None if not found
        """
        return self._workers.get(worker_name)
    
    def get_worker_for_task(self, task_type: str) -> Optional[BaseWorker]:
        """
        Get the worker that handles a specific task type.
        
        Args:
            task_type: Type of task
            
        Returns:
            Worker instance or None if no worker handles this task
        """
        worker_name = self._task_type_map.get(task_type)
        if not worker_name:
            logger.error(f"No worker registered for task type '{task_type}'")
            return None
        return self._workers.get(worker_name)
    
    async def execute_task(self, task: Task) -> TaskResult:
        """
        Route and execute a task using the appropriate worker.
        
        Args:
            task: Task to execute
            
        Returns:
            TaskResult from worker execution
        """
        # Find worker for task type
        worker = self.get_worker_for_task(task.task_type)
        
        if not worker:
            logger.error(f"No worker found for task type '{task.task_type}'")
            return TaskResult(
                success=False,
                error=f"No worker available for task type: {task.task_type}"
            )
        
        # Execute task
        logger.info(
            f"Routing task {task.task_id} (type: {task.task_type}) "
            f"to worker '{worker.worker_name}'"
        )
        
        return await worker.handle_task(task)
    
    def list_workers(self) -> List[Dict]:
        """
        List all registered workers and their info.
        
        Returns:
            List of worker info dictionaries
        """
        return [
            worker.get_worker_info()
            for worker in self._workers.values()
        ]
    
    def list_task_types(self) -> List[str]:
        """
        List all supported task types across all workers.
        
        Returns:
            List of task type strings
        """
        return list(self._task_type_map.keys())
    
    def get_worker_count(self) -> int:
        """
        Get the number of registered workers.
        
        Returns:
            Number of workers
        """
        return len(self._workers)


# Global registry instance
_registry: Optional[WorkerRegistry] = None


def get_worker_registry() -> WorkerRegistry:
    """
    Get the global worker registry instance.
    
    Returns:
        WorkerRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = WorkerRegistry()
    return _registry


def reset_worker_registry() -> None:
    """Reset the global worker registry (for testing)."""
    global _registry
    _registry = None
