"""
User Session Management - Handles user state and preferences
"""

from typing import Dict, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # User preferences and filters
        self.filters = {
            'content_type': 'all',  # 'all', 'photos', 'videos'
            'date_range': 'all',    # 'all', 'recent', 'week', 'month'
            'quality': 'any'        # 'any', 'hd', 'standard'
        }
        
        # Current session state
        self.current_creator = None
        self.current_directory = None
        self.current_page = 0
        self.search_history = []
        self.pending_content = None  # For confirmation flow
        self.pending_creator_options = None  # For multiple creator selection
        self.pending_creator_name = None  # For storing the searched name
        self.creator_selection_page = 0  # For paginating creator options
        self.is_simpcity_search = False  # Flag to indicate SimpCity search results
        
        # Request system
        self.awaiting_request = None  # 'creator' or 'content' or 'search'
        self.request_data = {}  # Store request details step by step
        
        # Admin setup system
        self.awaiting_admin_setup_password = False  # Flag for password entry
        self.awaiting_admin_removal_confirmation = False  # Flag for removal confirmation
        
        # Onlyfans Feed data
        self.of_feed_posts = None  # Store fetched Onlyfans Feed posts
        self.of_feed_username = None  # Store OF username
        
        # User interaction tracking
        self.total_searches = 0
        self.total_downloads = 0
        
        logger.info(f"Created new session for user {user_id}")
    
    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
    
    def set_filter(self, filter_type: str, value: str):
        """Set a specific filter value."""
        if filter_type in self.filters:
            old_value = self.filters[filter_type]
            self.filters[filter_type] = value
            self.update_activity()
            logger.info(f"User {self.user_id} changed filter {filter_type}: {old_value} -> {value}")
        else:
            logger.warning(f"Invalid filter type: {filter_type}")
    
    def reset_filters(self):
        """Reset all filters to default values."""
        old_filters = self.filters.copy()
        self.filters = {
            'content_type': 'all',
            'date_range': 'all',
            'quality': 'any'
        }
        self.update_activity()
        logger.info(f"User {self.user_id} reset filters from {old_filters} to {self.filters}")
    
    def add_search(self, creator_name: str, results_count: int = 0):
        """Add a search to the user's history."""
        search_entry = {
            'creator_name': creator_name,
            'timestamp': datetime.now(),
            'filters_used': self.filters.copy(),
            'results_count': results_count
        }
        
        self.search_history.append(search_entry)
        self.total_searches += 1
        self.update_activity()
        
        # Keep only last 10 searches
        if len(self.search_history) > 10:
            self.search_history.pop(0)
        
        logger.info(f"User {self.user_id} searched for '{creator_name}', found {results_count} results")
    
    def increment_downloads(self):
        """Increment the download counter."""
        self.total_downloads += 1
        self.update_activity()
        logger.info(f"User {self.user_id} download count: {self.total_downloads}")
    
    def get_session_duration(self) -> int:
        """Get session duration in minutes."""
        duration = datetime.now() - self.created_at
        return int(duration.total_seconds() / 60)
    
    def get_formatted_filters(self) -> str:
        """Get a formatted string representation of current filters."""
        filter_labels = {
            'content_type': {
                'all': 'All Content',
                'photos': 'Photos Only',
                'videos': 'Videos Only'
            },
            'date_range': {
                'all': 'All Time',
                'recent': 'Recent (24h)',
                'week': 'This Week',
                'month': 'This Month'
            },
            'quality': {
                'any': 'Any Quality',
                'hd': 'HD Quality',
                'standard': 'Standard Quality'
            }
        }
        
        formatted = []
        for filter_type, value in self.filters.items():
            if filter_type in filter_labels and value in filter_labels[filter_type]:
                formatted.append(filter_labels[filter_type][value])
            else:
                formatted.append(f"{filter_type}: {value}")
        
        return " | ".join(formatted)
    
    def get_recent_searches(self, limit: int = 5) -> list:
        """Get recent search history."""
        return self.search_history[-limit:] if self.search_history else []
    
    def clear_search_history(self):
        """Clear the search history."""
        old_count = len(self.search_history)
        self.search_history.clear()
        self.update_activity()
        logger.info(f"User {self.user_id} cleared {old_count} search history entries")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get comprehensive session statistics."""
        return {
            'user_id': self.user_id,
            'session_duration_minutes': self.get_session_duration(),
            'total_searches': self.total_searches,
            'total_downloads': self.total_downloads,
            'current_filters': self.filters.copy(),
            'search_history_count': len(self.search_history),
            'current_creator': self.current_creator,
            'last_activity': self.last_activity.isoformat(),
            'created_at': self.created_at.isoformat()
        }
    
    def is_active(self, timeout_minutes: int = 30) -> bool:
        """Check if the session is still active based on last activity."""
        time_diff = datetime.now() - self.last_activity
        return time_diff.total_seconds() < (timeout_minutes * 60)
    
    def get(self, key: str, default=None):
        """Get an attribute value with a default if it doesn't exist."""
        return getattr(self, key, default)
    
    def __str__(self) -> str:
        """String representation of the session."""
        return f"UserSession(user_id={self.user_id}, duration={self.get_session_duration()}min, searches={self.total_searches})"
    
    def __repr__(self) -> str:
        """Detailed string representation of the session."""
        return (f"UserSession(user_id={self.user_id}, created_at={self.created_at}, "
                f"filters={self.filters}, searches={self.total_searches}, "
                f"downloads={self.total_downloads})")

class SessionManager:
    """Manages multiple user sessions."""
    
    def __init__(self):
        self.sessions: Dict[int, UserSession] = {}
        logger.info("Session manager initialized")
    
    def get_session(self, user_id: int) -> UserSession:
        """Get or create a session for a user."""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id)
        else:
            self.sessions[user_id].update_activity()
        
        return self.sessions[user_id]
    
    def remove_session(self, user_id: int) -> bool:
        """Remove a user session."""
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info(f"Removed session for user {user_id}")
            return True
        return False
    
    def cleanup_inactive_sessions(self, timeout_minutes: int = 30) -> int:
        """Remove inactive sessions and return count of removed sessions."""
        inactive_users = []
        
        for user_id, session in self.sessions.items():
            if not session.is_active(timeout_minutes):
                inactive_users.append(user_id)
        
        for user_id in inactive_users:
            self.remove_session(user_id)
        
        if inactive_users:
            logger.info(f"Cleaned up {len(inactive_users)} inactive sessions")
        
        return len(inactive_users)
    
    def get_active_session_count(self) -> int:
        """Get the count of active sessions."""
        return len(self.sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get overall session statistics."""
        total_searches = sum(session.total_searches for session in self.sessions.values())
        total_downloads = sum(session.total_downloads for session in self.sessions.values())
        
        return {
            'active_sessions': len(self.sessions),
            'total_searches': total_searches,
            'total_downloads': total_downloads,
            'user_ids': list(self.sessions.keys())
        }