"""Task definitions for Search Worker."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class SearchTask:
    """Task for searching creators."""
    query: str
    filters: Optional[Dict[str, Any]] = None
    search_simpcity: bool = False  # Whether to search SimpCity if CSV fails
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Task params."""
        return {
            'query': self.query,
            'filters': self.filters,
            'search_simpcity': self.search_simpcity
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchTask':
        """Create from dictionary."""
        return cls(
            query=data['query'],
            filters=data.get('filters'),
            search_simpcity=data.get('search_simpcity', False)
        )


@dataclass
class CreatorOption:
    """A single creator search result."""
    name: str
    url: str
    source: str  # 'csv' or 'simpcity'
    score: float = 0.0  # Fuzzy match score
    replies: Optional[int] = None  # For SimpCity results
    date: Optional[str] = None
    snippet: Optional[str] = None
    thumbnail: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'url': self.url,
            'source': self.source,
            'score': self.score,
            'replies': self.replies,
            'date': self.date,
            'snippet': self.snippet,
            'thumbnail': self.thumbnail
        }


@dataclass
class SearchResult:
    """Result of a creator search."""
    query: str
    creators: List[CreatorOption]
    exact_match: bool = False
    fuzzy_match: bool = False
    source: str = 'csv'  # 'csv' or 'simpcity'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TaskResult data."""
        return {
            'query': self.query,
            'creators': [c.to_dict() for c in self.creators],
            'exact_match': self.exact_match,
            'fuzzy_match': self.fuzzy_match,
            'source': self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        """Create from dictionary."""
        return cls(
            query=data['query'],
            creators=[
                CreatorOption(**c) for c in data['creators']
            ],
            exact_match=data.get('exact_match', False),
            fuzzy_match=data.get('fuzzy_match', False),
            source=data.get('source', 'csv')
        )
