"""Task definitions for Content Worker."""

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class LoadContentTask:
    """Task for loading creator content."""
    creator_name: str
    creator_url: str
    filters: Optional[Dict[str, Any]] = None
    cache_only: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'creator_name': self.creator_name,
            'creator_url': self.creator_url,
            'filters': self.filters,
            'cache_only': self.cache_only
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LoadContentTask':
        return cls(
            creator_name=data['creator_name'],
            creator_url=data['creator_url'],
            filters=data.get('filters'),
            cache_only=data.get('cache_only', True)
        )


@dataclass
class LoadMorePagesTask:
    """Task for loading more pages."""
    creator_name: str
    filters: Optional[Dict[str, Any]] = None
    current_content: Optional[Dict[str, Any]] = None
    pages_to_fetch: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'creator_name': self.creator_name,
            'filters': self.filters,
            'current_content': self.current_content,
            'pages_to_fetch': self.pages_to_fetch
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LoadMorePagesTask':
        return cls(
            creator_name=data['creator_name'],
            filters=data.get('filters'),
            current_content=data.get('current_content'),
            pages_to_fetch=data.get('pages_to_fetch', 3)
        )


@dataclass
class ContentResult:
    """Result of content loading."""
    creator_name: str
    content_directory: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'creator_name': self.creator_name,
            'content_directory': self.content_directory
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentResult':
        return cls(
            creator_name=data['creator_name'],
            content_directory=data['content_directory']
        )
