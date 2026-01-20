"""
Session Manager - Manages user sessions for the coordinator.

Handles user state without business logic.
"""

from typing import Dict, Optional
import logging
try:
    # When running from project root
    from telegram_bot.core.user_session import UserSession
except ImportError:
    # When running from telegram_bot directory
    from core.user_session import UserSession

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages user sessions for the coordinator bot.
    
    Responsibilities:
    - Create and retrieve user sessions
    - Store session state
    - Clean up expired sessions
    """
    
    def __init__(self):
        """Initialize session manager."""
        self._sessions: Dict[int, UserSession] = {}
        logger.info("Initialized SessionManager")
    
    def get_session(self, user_id: int) -> UserSession:
        """
        Get or create a session for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserSession for the user
        """
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id)
            logger.info(f"Created new session for user {user_id}")
        
        return self._sessions[user_id]
    
    def has_session(self, user_id: int) -> bool:
        """
        Check if a session exists for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if session exists
        """
        return user_id in self._sessions
    
    def remove_session(self, user_id: int) -> bool:
        """
        Remove a user's session.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if session was removed, False if not found
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"Removed session for user {user_id}")
            return True
        return False
    
    def get_session_count(self) -> int:
        """
        Get the number of active sessions.
        
        Returns:
            Number of sessions
        """
        return len(self._sessions)
    
    def clear_all_sessions(self) -> None:
        """Clear all sessions (for testing/maintenance)."""
        count = len(self._sessions)
        self._sessions.clear()
        logger.info(f"Cleared {count} sessions")
