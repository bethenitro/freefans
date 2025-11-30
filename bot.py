"""
FreeFans Telegram Bot - Main Bot File (Modularized)
A bot for accessing creator content with filtering capabilities
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest, RetryAfter
from decouple import config
import asyncio

# Import modular components
from content_manager import ContentManager
from user_session import UserSession
from bot.command_handlers import start_command, help_command
from bot.search_handler import handle_creator_search
from bot.callback_handlers import handle_callback_query

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class FreeFansBot:
    """Main bot class that coordinates all bot operations."""
    
    def __init__(self):
        self.content_manager = ContentManager()
        self.user_sessions = {}
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        await start_command(update, context, self)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        await help_command(update, context)

    async def handle_creator_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle creator name input and search for content."""
        await handle_creator_search(update, context, self)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        await handle_callback_query(update, context, self)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors caused by Updates."""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        error_message = "❌ An unexpected error occurred. Please try again later."
        
        try:
            if isinstance(context.error, TimedOut):
                error_message = "⏱️ Request timed out. Please check your connection and try again."
                logger.error("Telegram API timeout occurred")
            elif isinstance(context.error, NetworkError):
                error_message = "🌐 Network error. Please check your internet connection and try again."
                logger.error(f"Network error: {context.error}")
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                error_message = f"⏸️ Too many requests. Please wait {retry_after} seconds before trying again."
                logger.error(f"Rate limited. Retry after {retry_after}s")
            elif isinstance(context.error, BadRequest):
                error_message = "❌ Invalid request. Please try a different action."
                logger.error(f"Bad request: {context.error}")
            elif isinstance(context.error, RuntimeError) and "no bot associated" in str(context.error):
                error_message = "⚠️ Internal error occurred. Please try your action again."
                logger.error(f"Bot association error: {context.error}")
            else:
                logger.error(f"Unhandled error type: {type(context.error).__name__}: {context.error}")
            
            # Try to notify the user
            if update and hasattr(update, 'effective_message') and update.effective_message:
                try:
                    await asyncio.sleep(1)
                    await update.effective_message.reply_text(error_message)
                except Exception as e:
                    logger.error(f"Failed to send error message to user: {e}")
            elif update and hasattr(update, 'callback_query') and update.callback_query:
                try:
                    await asyncio.sleep(1)
                    await update.callback_query.answer(error_message, show_alert=True)
                except Exception as e:
                    logger.error(f"Failed to send error answer to callback query: {e}")
                    
        except Exception as e:
            logger.error(f"Error in error handler: {e}")


def main():
    """Start the bot."""
    # Get token from environment variable
    try:
        TOKEN = config('TELEGRAM_BOT_TOKEN')
    except:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file")
        print("Please add your Telegram bot token to the .env file:")
        print("TELEGRAM_BOT_TOKEN=your_bot_token_here")
        return
    
    # Create application with custom settings for better timeout handling
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    # Initialize bot
    bot = FreeFansBot()
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CallbackQueryHandler(bot.handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_creator_search))
    
    # Register error handler
    application.add_error_handler(bot.error_handler)
    
    # Run the bot
    print("🤖 FreeFans Bot is starting...")
    print("✅ Error handlers registered")
    print("✅ Timeout settings configured")
    print("🔄 Starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
