"""Content Worker - Handles content loading and filtering."""

import logging
from ..base_worker import BaseWorker, Task, TaskResult
from .tasks import LoadContentTask, LoadMorePagesTask, ContentResult

logger = logging.getLogger(__name__)


class ContentWorker(BaseWorker):
    """Worker for content operations."""
    
    TASK_LOAD_CONTENT = "load_content"
    TASK_LOAD_MORE_PAGES = "load_more_pages"
    TASK_GET_RANDOM_CREATOR = "get_random_creator"
    
    def __init__(self, content_manager):
        super().__init__("content_worker")
        self.content_manager = content_manager
    
    def get_supported_tasks(self) -> list[str]:
        return [
            self.TASK_LOAD_CONTENT,
            self.TASK_LOAD_MORE_PAGES,
            self.TASK_GET_RANDOM_CREATOR
        ]
    
    async def execute(self, task: Task) -> TaskResult:
        if task.task_type == self.TASK_LOAD_CONTENT:
            return await self._load_content(task)
        elif task.task_type == self.TASK_LOAD_MORE_PAGES:
            return await self._load_more_pages(task)
        elif task.task_type == self.TASK_GET_RANDOM_CREATOR:
            return await self._get_random_creator(task)
        else:
            return TaskResult(success=False, error=f"Unknown task: {task.task_type}")
    
    async def _load_content(self, task: Task) -> TaskResult:
        try:
            load_task = LoadContentTask.from_dict(task.params)
            
            self.logger.info(f"Loading content for: {load_task.creator_name}")
            
            content_directory = await self.content_manager.search_creator_content(
                load_task.creator_name,
                load_task.filters,
                direct_url=load_task.creator_url,
                cache_only=load_task.cache_only
            )
            
            if not content_directory:
                return TaskResult(success=False, error="Failed to load content")
            
            result = ContentResult(
                creator_name=load_task.creator_name,
                content_directory=content_directory
            )
            
            self.logger.info(f"Loaded {len(content_directory.get('items', []))} items")
            
            return TaskResult(success=True, data=result.to_dict())
            
        except Exception as e:
            self.logger.exception(f"Error loading content: {e}")
            return TaskResult(success=False, error=str(e))
    
    async def _load_more_pages(self, task: Task) -> TaskResult:
        try:
            load_task = LoadMorePagesTask.from_dict(task.params)
            
            self.logger.info(f"Loading more pages for: {load_task.creator_name}")
            
            updated_content = await self.content_manager.fetch_more_pages(
                load_task.creator_name,
                load_task.filters,
                load_task.current_content,
                pages_to_fetch=load_task.pages_to_fetch
            )
            
            if not updated_content:
                return TaskResult(success=False, error="Failed to load more pages")
            
            result = ContentResult(
                creator_name=load_task.creator_name,
                content_directory=updated_content
            )
            
            self.logger.info(f"Loaded more pages, total items: {len(updated_content.get('items', []))}")
            
            return TaskResult(success=True, data=result.to_dict())
            
        except Exception as e:
            self.logger.exception(f"Error loading more pages: {e}")
            return TaskResult(success=False, error=str(e))
    
    async def _get_random_creator(self, task: Task) -> TaskResult:
        try:
            min_items = task.params.get('min_items', 25)
            
            self.logger.info(f"Getting random creator with min {min_items} items")
            
            random_creator = await self.content_manager.get_random_creator_with_content(min_items)
            
            if not random_creator:
                return TaskResult(success=False, error="No creators found with enough content")
            
            return TaskResult(
                success=True,
                data={
                    'creator_name': random_creator['name'],
                    'creator_url': random_creator['url'],
                    'item_count': random_creator['item_count']
                }
            )
            
        except Exception as e:
            self.logger.exception(f"Error getting random creator: {e}")
            return TaskResult(success=False, error=str(e))
