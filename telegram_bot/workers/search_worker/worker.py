"""
Search Worker - Handles all creator search operations.

This worker is responsible for:
- Searching creators in CSV database
- Fuzzy matching creator names
- Searching SimpCity when CSV fails
- Ranking and returning search results
"""

import logging
from typing import List, Optional
from ..base_worker import BaseWorker, Task, TaskResult
from .tasks import SearchTask, SearchResult, CreatorOption

logger = logging.getLogger(__name__)


class SearchWorker(BaseWorker):
    """Worker for handling creator search operations."""
    
    TASK_SEARCH_CREATOR = "search_creator"
    TASK_SEARCH_SIMPCITY = "search_simpcity"
    
    def __init__(self, content_manager):
        """
        Initialize Search Worker.
        
        Args:
            content_manager: ContentManager instance for search operations
        """
        super().__init__("search_worker")
        self.content_manager = content_manager
    
    def get_supported_tasks(self) -> list[str]:
        """Get list of supported task types."""
        return [
            self.TASK_SEARCH_CREATOR,
            self.TASK_SEARCH_SIMPCITY
        ]
    
    async def execute(self, task: Task) -> TaskResult:
        """
        Execute a search task.
        
        Args:
            task: Task to execute
            
        Returns:
            TaskResult with search results
        """
        if task.task_type == self.TASK_SEARCH_CREATOR:
            return await self._search_creator(task)
        elif task.task_type == self.TASK_SEARCH_SIMPCITY:
            return await self._search_simpcity(task)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown task type: {task.task_type}"
            )
    
    async def _search_creator(self, task: Task) -> TaskResult:
        """
        Search for creators in CSV database.
        
        Args:
            task: Task with search parameters
            
        Returns:
            TaskResult with search results
        """
        try:
            # Parse task params
            search_task = SearchTask.from_dict(task.params)
            query = search_task.query
            
            self.logger.info(f"Searching for creator: {query}")
            
            # Search using content manager
            search_options = await self.content_manager.search_creator_options(query)
            
            if not search_options:
                self.logger.info(f"No results found for: {query}")
                return TaskResult(
                    success=True,
                    data=SearchResult(
                        query=query,
                        creators=[],
                        exact_match=False,
                        fuzzy_match=False,
                        source='csv'
                    ).to_dict()
                )
            
            # Check if multiple options need selection
            if search_options.get('needs_selection'):
                options = search_options['options']
                
                # Convert to CreatorOption objects
                creators = []
                for opt in options:
                    creators.append(CreatorOption(
                        name=opt['name'],
                        url=opt['url'],
                        source='csv',
                        score=opt.get('score', 0.0)
                    ))
                
                result = SearchResult(
                    query=query,
                    creators=creators,
                    exact_match=False,
                    fuzzy_match=True,
                    source='csv'
                )
                
                self.logger.info(f"Found {len(creators)} creator options for: {query}")
                
                return TaskResult(
                    success=True,
                    data=result.to_dict(),
                    metadata={'needs_selection': True}
                )
            
            # Single exact match - return it
            if 'creator_name' in search_options and 'creator_url' in search_options:
                creator = CreatorOption(
                    name=search_options['creator_name'],
                    url=search_options['creator_url'],
                    source='csv',
                    score=1.0
                )
                
                result = SearchResult(
                    query=query,
                    creators=[creator],
                    exact_match=True,
                    fuzzy_match=False,
                    source='csv'
                )
                
                self.logger.info(f"Found exact match for: {query}")
                
                return TaskResult(
                    success=True,
                    data=result.to_dict(),
                    metadata={'needs_selection': False}
                )
            
            # Unexpected format
            self.logger.warning(f"Unexpected search_options format: {search_options}")
            return TaskResult(
                success=False,
                error="Unexpected search result format"
            )
            
        except Exception as e:
            self.logger.exception(f"Error searching creator: {e}")
            return TaskResult(
                success=False,
                error=f"Search failed: {str(e)}"
            )
    
    async def _search_simpcity(self, task: Task) -> TaskResult:
        """
        Search for creators on SimpCity.
        
        Args:
            task: Task with search parameters
            
        Returns:
            TaskResult with SimpCity search results
        """
        try:
            # Parse task params
            search_task = SearchTask.from_dict(task.params)
            query = search_task.query
            
            self.logger.info(f"Searching SimpCity for: {query}")
            
            # Search SimpCity
            simpcity_results = await self.content_manager.scraper.search_simpcity(query)
            
            if not simpcity_results:
                self.logger.info(f"No SimpCity results found for: {query}")
                return TaskResult(
                    success=True,
                    data=SearchResult(
                        query=query,
                        creators=[],
                        exact_match=False,
                        fuzzy_match=False,
                        source='simpcity'
                    ).to_dict()
                )
            
            # Convert to CreatorOption objects
            creators = []
            for result in simpcity_results:
                creators.append(CreatorOption(
                    name=result['title'],
                    url=result['url'],
                    source='simpcity',
                    score=0.0,  # SimpCity doesn't provide scores
                    replies=result.get('replies'),
                    date=result.get('date'),
                    snippet=result.get('snippet'),
                    thumbnail=result.get('thumbnail')
                ))
            
            result = SearchResult(
                query=query,
                creators=creators,
                exact_match=False,
                fuzzy_match=False,
                source='simpcity'
            )
            
            self.logger.info(f"Found {len(creators)} SimpCity results for: {query}")
            
            return TaskResult(
                success=True,
                data=result.to_dict(),
                metadata={'needs_selection': True}
            )
            
        except Exception as e:
            self.logger.exception(f"Error searching SimpCity: {e}")
            return TaskResult(
                success=False,
                error=f"SimpCity search failed: {str(e)}"
            )
