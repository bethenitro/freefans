"""
Message Router - Routes text messages to appropriate workers.

This handler is lightweight and only routes messages, no business logic.
"""

import logging
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from ..session_manager import SessionManager
from ..response_formatter import ResponseFormatter
from workers.worker_registry import get_worker_registry
from workers.base_worker import Task
from workers.search_worker.tasks import SearchTask

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes text messages to workers."""
    
    def __init__(self, session_manager: SessionManager):
        """
        Initialize message router.
        
        Args:
            session_manager: Session manager instance
        """
        self.session_manager = session_manager
        self.formatter = ResponseFormatter()
        self.worker_registry = get_worker_registry()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle incoming text message.
        
        Args:
            update: Telegram update
            context: Telegram context
        """
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        # Get or create session
        session = self.session_manager.get_session(user_id)
        
        # Check what the user is expecting to do
        awaiting_request = getattr(session, 'awaiting_request', None)
        
        if awaiting_request == 'search':
            # User is searching for a creator
            await self._handle_search(update, context, message_text, session)
        else:
            # Default: show help or menu
            await self._handle_default(update, context)
    
    async def _handle_search(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        query: str,
        session
    ) -> None:
        """
        Handle creator search request.
        
        Args:
            update: Telegram update
            context: Telegram context
            query: Search query
            session: User session
        """
        try:
            # Show loading message
            loading_msg = self.formatter.format_loading_message('search', query)
            search_message = await update.message.reply_text(loading_msg)
            
            # Create search task
            task = Task(
                task_id=str(uuid.uuid4()),
                user_id=update.effective_user.id,
                task_type='search_creator',
                params=SearchTask(
                    query=query,
                    filters=getattr(session, 'filters', None)
                ).to_dict()
            )
            
            # Execute task via worker registry
            result = await self.worker_registry.execute_task(task)
            
            if not result.success:
                # Show error
                error_msg = self.formatter.format_error(result.error)
                await search_message.edit_text(error_msg)
                return
            
            # Format and display results
            needs_selection = result.metadata.get('needs_selection', False)
            text, keyboard = self.formatter.format_search_results(
                result.data,
                needs_selection
            )
            
            if keyboard:
                # Store options in session for callback handling
                session.pending_creator_options = result.data.get('creators', [])
                session.pending_creator_name = query
                session.creator_selection_page = 0
                
                await search_message.edit_text(text, reply_markup=keyboard)
            else:
                # Single result - proceed to load content
                await search_message.edit_text(text)
                # TODO: Trigger content loading
            
            # Clear awaiting state
            session.awaiting_request = None
            
        except Exception as e:
            logger.exception(f"Error handling search: {e}")
            error_msg = self.formatter.format_error(str(e))
            try:
                await update.message.reply_text(error_msg)
            except Exception:
                pass
    
    async def _handle_default(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle default message (show help/menu).
        
        Args:
            update: Telegram update
            context: Telegram context
        """
        from bot.command_handlers import create_main_menu_keyboard
        
        reply_markup = create_main_menu_keyboard()
        await update.message.reply_text(
            "💡 Please use the menu buttons below to search or make a request.",
            reply_markup=reply_markup
        )
