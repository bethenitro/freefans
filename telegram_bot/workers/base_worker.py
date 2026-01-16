"""
Base Worker Class - Foundation for all functional workers

Workers are stateless components that execute business logic
without any direct Telegram communication.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Base task class for worker operations."""
    task_id: str
    user_id: int
    task_type: str
    params: Dict[str, Any]
    
    def __post_init__(self):
        """Validate task after initialization."""
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.task_type:
            raise ValueError("task_type is required")


@dataclass
class TaskResult:
    """Base result class for worker responses."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate result after initialization."""
        if not self.success and not self.error:
            raise ValueError("error message required when success=False")


class BaseWorker(ABC):
    """
    Base class for all functional workers.
    
    Workers should:
    - Be stateless (or minimally stateful)
    - Not communicate with Telegram directly
    - Execute business logic only
    - Return structured data
    """
    
    def __init__(self, worker_name: str):
        """
        Initialize worker.
        
        Args:
            worker_name: Unique identifier for this worker
        """
        self.worker_name = worker_name
        self.logger = logging.getLogger(f"worker.{worker_name}")
        self.logger.info(f"Initialized {worker_name} worker")
    
    @abstractmethod
    async def execute(self, task: Task) -> TaskResult:
        """
        Execute a task and return result.
        
        Args:
            task: Task to execute
            
        Returns:
            TaskResult with success status and data/error
        """
        pass
    
    @abstractmethod
    def get_supported_tasks(self) -> list[str]:
        """
        Get list of task types this worker supports.
        
        Returns:
            List of task type strings
        """
        pass
    
    def validate_task(self, task: Task) -> bool:
        """
        Validate that this worker can handle the task.
        
        Args:
            task: Task to validate
            
        Returns:
            True if task is valid for this worker
        """
        if task.task_type not in self.get_supported_tasks():
            self.logger.error(
                f"Task type '{task.task_type}' not supported by {self.worker_name}"
            )
            return False
        return True
    
    async def handle_task(self, task: Task) -> TaskResult:
        """
        Handle a task with validation and error handling.
        
        Args:
            task: Task to handle
            
        Returns:
            TaskResult with success status and data/error
        """
        try:
            # Validate task
            if not self.validate_task(task):
                return TaskResult(
                    success=False,
                    error=f"Invalid task type: {task.task_type}"
                )
            
            # Log task execution
            self.logger.info(
                f"Executing task {task.task_id} (type: {task.task_type}) "
                f"for user {task.user_id}"
            )
            
            # Execute task
            result = await self.execute(task)
            
            # Log result
            if result.success:
                self.logger.info(f"Task {task.task_id} completed successfully")
            else:
                self.logger.error(f"Task {task.task_id} failed: {result.error}")
            
            return result
            
        except Exception as e:
            self.logger.exception(f"Unexpected error in task {task.task_id}: {e}")
            return TaskResult(
                success=False,
                error=f"Internal worker error: {str(e)}"
            )
    
    def get_worker_info(self) -> Dict[str, Any]:
        """
        Get information about this worker.
        
        Returns:
            Dictionary with worker metadata
        """
        return {
            'name': self.worker_name,
            'supported_tasks': self.get_supported_tasks(),
            'status': 'active'
        }
