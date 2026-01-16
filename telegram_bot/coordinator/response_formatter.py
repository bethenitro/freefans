"""
Response Formatter - Formats worker responses for Telegram.

Converts structured worker data into user-friendly Telegram messages.
"""

from typing import Dict, Any, Optional, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """
    Formats worker responses into Telegram messages.
    
    Responsibilities:
    - Convert worker data to text messages
    - Create inline keyboards
    - Format errors for users
    """
    
    @staticmethod
    def format_search_results(
        result_data: Dict[str, Any],
        needs_selection: bool = False
    ) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
        """
        Format search results for display.
        
        Args:
            result_data: Search result data from worker
            needs_selection: Whether user needs to select from multiple options
            
        Returns:
            Tuple of (message_text, reply_markup)
        """
        query = result_data.get('query', 'Unknown')
        creators = result_data.get('creators', [])
        source = result_data.get('source', 'csv')
        
        if not creators:
            text = (
                f"😔 No content found for '{query}'\n\n"
                f"Try this:\n"
                f"• Double-check the spelling\n"
                f"• Try a different name or alias\n"
                f"• Search for another creator\n\n"
                f"We're always adding new content, so check back soon! 💋"
            )
            return text, None
        
        if needs_selection:
            # Multiple options - show selection menu
            if source == 'simpcity':
                text = f"🔥 Extended Search Results 🔥\n\n"
                text += f"Found {len(creators)} matches for '{query}'\n\n"
            else:
                text = f"✨ Found {len(creators)} creators ✨\n\n"
                text += f"Searching for: '{query}'\n\n"
            
            text += "Select the creator you want 👇\n"
            
            # Create selection keyboard
            keyboard = []
            for i, creator in enumerate(creators[:10]):  # Show first 10
                name = creator['name']
                if len(name) > 60:
                    name = name[:57] + "..."
                
                callback_data = f"select_creator|{i}"
                keyboard.append([InlineKeyboardButton(name, callback_data=callback_data)])
            
            # Add search more button for CSV results
            if source == 'csv':
                keyboard.append([
                    InlineKeyboardButton("🔍 Not found? Search More", callback_data="search_on_simpcity")
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="search_creator")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            return text, reply_markup
        
        # Single exact match - no selection needed
        creator = creators[0]
        text = f"✅ Found: {creator['name']}\n🔄 Loading content..."
        return text, None
    
    @staticmethod
    def format_error(error_message: str) -> str:
        """
        Format an error message for users.
        
        Args:
            error_message: Raw error message
            
        Returns:
            User-friendly error message
        """
        # Map technical errors to user-friendly messages
        error_map = {
            'No worker available': '⚠️ Service temporarily unavailable. Please try again.',
            'Search failed': '❌ Search failed. Please try again later.',
            'Internal worker error': '⚠️ Server issue. Please try again.',
        }
        
        for key, friendly_msg in error_map.items():
            if key in error_message:
                return friendly_msg
        
        # Generic error message
        return "❌ An error occurred. Please try again later."
    
    @staticmethod
    def format_loading_message(operation: str, creator_name: Optional[str] = None) -> str:
        """
        Format a loading message.
        
        Args:
            operation: Operation being performed
            creator_name: Optional creator name
            
        Returns:
            Loading message text
        """
        if operation == 'search':
            if creator_name:
                return (
                    f"🔍 Searching for {creator_name}...\n\n"
                    f"Finding the hottest content for you 🔥"
                )
            return "🔍 Searching...\n\nPlease wait..."
        
        elif operation == 'load_content':
            if creator_name:
                return f"✅ Selected: {creator_name}\n🔄 Loading content..."
            return "🔄 Loading content...\nPlease wait..."
        
        elif operation == 'load_more':
            if creator_name:
                return (
                    f"⏳ Loading more content for '{creator_name}'...\n"
                    f"Please wait..."
                )
            return "⏳ Loading more content...\nPlease wait..."
        
        # Generic loading message
        return "⏳ Processing...\nPlease wait..."
    
    @staticmethod
    def format_success_message(operation: str, details: Optional[str] = None) -> str:
        """
        Format a success message.
        
        Args:
            operation: Operation that succeeded
            details: Optional details
            
        Returns:
            Success message text
        """
        messages = {
            'search': '✅ Search completed!',
            'load_content': '✅ Content loaded!',
            'load_more': '✅ More content loaded!',
        }
        
        base_message = messages.get(operation, '✅ Operation completed!')
        
        if details:
            return f"{base_message}\n\n{details}"
        
        return base_message
