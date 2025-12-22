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
🔥 Welcome to FreeFans Bot 🔥

Your personal gateway to exclusive creator content

What I can do for you:

🔍 Search any creator instantly
🖼️ Browse hot photo galleries
🎬 Stream premium videos
📱 Access OnlyFans archives
💾 Download everything you want

💋 Just send me a creator's name and let's get started!
"""

HELP_TEXT = """
� FreeFans Bot Help �

� How to Find What You Want

Type any creator's name and I'll find their hottest content. The search is smart - even partial names work!

� What You Get Access To

🖼️ Photos - High-res galleries, full albums
🎬 Videos - Stream or download premium clips  
📱 OnlyFans Archives - Complete feed history
💎 Exclusive Content - Hard to find anywhere else

⚙️ Customize Your Experience

Use filters to find exactly what you're looking for:
📁 Photos only, videos only, or everything
📅 Recent uploads or all-time favorites
🎬 HD quality or any resolution

⚡ Quick Commands

/start - Get started with the bot
/help - Show this guide again
/filters - Set up your preferences

Ready to explore? Just send me a creator's name! 😈
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
