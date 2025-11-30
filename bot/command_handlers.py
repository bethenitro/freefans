"""
Command Handlers - Handles bot commands like /start, /help
"""

import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError
from bot.utilities import send_message_with_retry
from bot.ui_components import create_welcome_keyboard
from user_session import UserSession

logger = logging.getLogger(__name__)

WELCOME_TEXT = """
🎉 Welcome to FreeFans Bot! 🎉

I can help you discover content from your favorite creators.

🔍 How to use:
• Send me a creator's name to search for content
• Use filters to narrow down your search
• Browse through organized content directories
• Get direct links to content you want

Type a creator's name to get started!
"""

HELP_TEXT = """
📖 FreeFans Bot Help

🔍 Searching for Content:
• Simply type a creator's name
• The bot will search and return organized content

🏷️ Content Filters:
• Content Type: Photos, Videos, All
• Date Range: Recent, This Week, This Month, All Time
• Quality: HD, Standard, Any

📁 Content Directory Structure:
• Content is organized by upload date
• Each item shows preview info
• Click to get direct download link

💡 Commands:
/start - Start the bot
/help - Show this help message
/filters - Set content filters
/clear - Clear search history

Need help? Contact support!
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    reply_markup = create_welcome_keyboard()
    
    try:
        await send_message_with_retry(
            update.message.reply_text,
            WELCOME_TEXT,
            reply_markup=reply_markup
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send welcome message after retries: {e}")
        # Try to send a simpler message without keyboard
        try:
            await asyncio.sleep(2)
            await update.message.reply_text(
                "⚠️ Welcome to FreeFans Bot! The bot is experiencing connection issues. Please try again in a moment."
            )
        except Exception:
            pass  # If this also fails, let the error handler deal with it


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    try:
        await send_message_with_retry(update.message.reply_text, HELP_TEXT)
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send help message: {e}")
