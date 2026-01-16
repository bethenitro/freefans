"""
Celery Tasks - Distributed task definitions

All tasks that can be executed by workers.
"""

import logging
from typing import Dict, Any
from celery import Task as CeleryTask
from .celery_app import celery_app
from .base_worker import Task, TaskResult
from .search_worker import SearchWorker
from .content_worker import ContentWorker
from core.content_manager import ContentManager
from managers.cache_factory import get_cache_manager

logger = logging.getLogger(__name__)

# Initialize shared resources (per worker process)
_cache_manager = None
_content_manager = None
_search_worker = None
_content_worker = None


def get_workers():
    """Get or initialize worker instances (lazy initialization)."""
    global _cache_manager, _content_manager, _search_worker, _content_worker
    
    if _cache_manager is None:
        _cache_manager = get_cache_manager()
        _content_manager = ContentManager(_cache_manager)
        _search_worker = SearchWorker(_content_manager)
        _content_worker = ContentWorker(_content_manager)
        logger.info("✅ Initialized workers in Celery process")
    
    return _search_worker, _content_worker


# ==================== SEARCH TASKS ====================

@celery_app.task(
    name='workers.celery_tasks.search_creator',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def search_creator(self: CeleryTask, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for a creator (CSV search).
    
    Args:
        task_data: Task data dictionary
        
    Returns:
        TaskResult as dictionary
    """
    try:
        search_worker, _ = get_workers()
        
        # Create Task object
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        # Execute task synchronously (Celery handles async)
        import asyncio
        result = asyncio.run(search_worker.handle_task(task))
        
        # Return as dictionary
        return {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata
        }
        
    except Exception as e:
        logger.exception(f"Error in search_creator task: {e}")
        return {
            'success': False,
            'data': None,
            'error': str(e),
            'metadata': {}
        }


@celery_app.task(
    name='workers.celery_tasks.search_simpcity',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def search_simpcity(self: CeleryTask, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for a creator on SimpCity (extended search).
    
    Args:
        task_data: Task data dictionary
        
    Returns:
        TaskResult as dictionary
    """
    try:
        search_worker, _ = get_workers()
        
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        import asyncio
        result = asyncio.run(search_worker.handle_task(task))
        
        return {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata
        }
        
    except Exception as e:
        logger.exception(f"Error in search_simpcity task: {e}")
        return {
            'success': False,
            'data': None,
            'error': str(e),
            'metadata': {}
        }


@celery_app.task(
    name='workers.celery_tasks.get_random_creator',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def get_random_creator(self: CeleryTask, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a random creator with content.
    
    Args:
        task_data: Task data dictionary
        
    Returns:
        TaskResult as dictionary
    """
    try:
        search_worker, _ = get_workers()
        
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        import asyncio
        result = asyncio.run(search_worker.handle_task(task))
        
        return {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata
        }
        
    except Exception as e:
        logger.exception(f"Error in get_random_creator task: {e}")
        return {
            'success': False,
            'data': None,
            'error': str(e),
            'metadata': {}
        }


# ==================== CONTENT TASKS ====================

@celery_app.task(
    name='workers.celery_tasks.load_content',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def load_content(self: CeleryTask, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load content for a creator.
    
    Args:
        task_data: Task data dictionary
        
    Returns:
        TaskResult as dictionary
    """
    try:
        _, content_worker = get_workers()
        
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        import asyncio
        result = asyncio.run(content_worker.handle_task(task))
        
        return {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata
        }
        
    except Exception as e:
        logger.exception(f"Error in load_content task: {e}")
        return {
            'success': False,
            'data': None,
            'error': str(e),
            'metadata': {}
        }


@celery_app.task(
    name='workers.celery_tasks.load_more_pages',
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def load_more_pages(self: CeleryTask, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load more pages for a creator.
    
    Args:
        task_data: Task data dictionary
        
    Returns:
        TaskResult as dictionary
    """
    try:
        _, content_worker = get_workers()
        
        task = Task(
            task_id=task_data['task_id'],
            user_id=task_data['user_id'],
            task_type=task_data['task_type'],
            params=task_data['params']
        )
        
        import asyncio
        result = asyncio.run(content_worker.handle_task(task))
        
        return {
            'success': result.success,
            'data': result.data,
            'error': result.error,
            'metadata': result.metadata
        }
        
    except Exception as e:
        logger.exception(f"Error in load_more_pages task: {e}")
        return {
            'success': False,
            'data': None,
            'error': str(e),
            'metadata': {}
        }


# Task name mapping for easy lookup
TASK_MAP = {
    'search_creator': search_creator,
    'search_simpcity': search_simpcity,
    'get_random_creator': get_random_creator,
    'load_content': load_content,
    'load_more_pages': load_more_pages,
}
