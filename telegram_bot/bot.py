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
from core.content_manager import ContentManager
from core.user_session import UserSession
from bot.command_handlers import start_command, help_command, cancel_command
from bot.search_handler import handle_creator_search
from bot.callback_handlers import handle_callback_query
from bot.admin_handlers import (
    admin_requests_command, admin_titles_command, approve_title_command,
    reject_title_command, bulk_approve_command, bulk_reject_command, admin_stats_command
)
from bot.worker_handlers import (
    handle_worker_reply, worker_stats_command, worker_help_command
)
from managers.cache_factory import get_cache_manager
from core.content_scraper import SimpleCityScraper

# Add shared directory to path for config and data access
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared'))

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Reduce httpx logging noise (only show warnings and errors)
logging.getLogger('httpx').setLevel(logging.WARNING)


class FreeFansBot:
    """Main bot class that coordinates all bot operations."""
    
    def __init__(self, cache_manager=None):
        self.cache_manager = cache_manager or get_cache_manager()
        self.content_manager = ContentManager(self.cache_manager)
        self.user_sessions = {}

    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        await start_command(update, context, self)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        await help_command(update, context)
    
    async def cache_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show cache statistics."""
        try:
            cache_stats = self.cache_manager.get_cache_stats()
            
            # Build database info section
            db_info = f"• Storage: {cache_stats.get('storage_type', 'SQLite only')}\n"
            db_info += f"• Local Size: {cache_stats['database_size_mb']} MB\n"
            
            if cache_stats.get('supabase_enabled', False):
                db_info += f"• Supabase: ✅ Connected\n"
                db_info += f"• Remote Creators: {cache_stats.get('supabase_creators', 0)}\n"
                db_info += f"• Remote Posts: {cache_stats.get('supabase_onlyfans_posts', 0)}"
            else:
                db_info += "• Supabase: ❌ Disabled"
            
            message = f"""
📊 **Cache Statistics**

**SimpCity Content:**
• Cached Creators: {cache_stats['total_creators']}
• Content Items: {cache_stats['total_content_items']}
• Preview Images: {cache_stats['total_preview_images']}
• Video Links: {cache_stats['total_video_links']}

**OnlyFans/Coomer Data:**
• Cached Users: {cache_stats['total_onlyfans_users']}
• Cached Posts: {cache_stats['total_onlyfans_posts']}

**Database Info:**
{db_info}

💡 Cache updates when new queries are made
            """
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing cache stats: {e}")
            await update.message.reply_text("❌ Failed to retrieve cache statistics.")

    async def handle_creator_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle creator name input and search for content."""
        # Check if this is a worker reply to a video first
        if await handle_worker_reply(update, context, self):
            return
        
        # Check if this is a menu button or request flow
        from bot.menu_handlers import handle_menu_button, handle_request_flow
        
        # Handle menu buttons
        if await handle_menu_button(update, context, self):
            return
        
        # Handle request flow (multi-step)
        if await handle_request_flow(update, context, self):
            return
        
        # Otherwise, handle as creator search (only if awaiting_request == 'search')
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            session = self.user_sessions[user_id]
            if session.awaiting_request == 'search':
                session.awaiting_request = None  # Clear the search state
                await handle_creator_search(update, context, self)
            else:
                # Not in search mode, show help
                from bot.command_handlers import create_main_menu_keyboard
                reply_markup = create_main_menu_keyboard()
                await update.message.reply_text(
                    "💡 Please use the menu buttons below to search or make a request.",
                    reply_markup=reply_markup
                )
        else:
            # No session, show help
            from bot.command_handlers import create_main_menu_keyboard
            reply_markup = create_main_menu_keyboard()
            await update.message.reply_text(
                "💡 Please use the menu buttons below to search or make a request.",
                reply_markup=reply_markup
            )

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
    
    # Initialize cache manager based on configuration
    print("💾 Initializing cache manager...")
    cache_manager = get_cache_manager()
    cache_stats = cache_manager.get_cache_stats()
    print(f"✅ Cache ready: {cache_stats['total_creators']} creators, "
          f"{cache_stats['total_content_items']} items cached")
    
    print("\n� Caching strategy:")
    print("   • Cache updates on-demand when queries are made")
    print("   • Use 'python manual_cache.py' for background caching")
    print("✅ Bot starting immediately!\n")
    
    # Preload CSV cache for faster searches
    print("📂 Preloading CSV cache...")
    from scrapers.csv_handler import preload_csv_cache
    try:
        count = preload_csv_cache()
        print(f"✅ Preloaded {count} models into CSV cache\n")
    except Exception as e:
        print(f"⚠️ Warning: Failed to preload CSV cache: {e}\n")
    
    # Create application with custom settings for better timeout handling
    print("🤖 Initializing Telegram bot...")
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    # Initialize bot with cache manager
    bot = FreeFansBot()
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("cache", bot.cache_stats_command))
    application.add_handler(CommandHandler("cancel", lambda update, context: cancel_command(update, context, bot)))
    
    # Admin commands
    application.add_handler(CommandHandler("requests", admin_requests_command))
    application.add_handler(CommandHandler("titles", admin_titles_command))
    application.add_handler(CommandHandler("approve", approve_title_command))
    application.add_handler(CommandHandler("reject", reject_title_command))
    application.add_handler(CommandHandler("bulkapprove", bulk_approve_command))
    application.add_handler(CommandHandler("bulkreject", bulk_reject_command))
    application.add_handler(CommandHandler("adminstats", admin_stats_command))
    
    # Worker commands
    application.add_handler(CommandHandler("mystats", worker_stats_command))
    application.add_handler(CommandHandler("workerhelp", worker_help_command))
    
    application.add_handler(CallbackQueryHandler(bot.handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_creator_search))
    
    # Register error handler
    application.add_error_handler(bot.error_handler)
    
    # Run the bot
    print("✅ All systems ready!")
    print("✅ Error handlers registered")
    print("✅ Timeout settings configured")
    print("✅ Cache system enabled and populated")
    print("� Starting bot polling...\n")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n⏹️  Stopping bot...")
        print("👋 Bot shutdown complete")


if __name__ == '__main__':
    main()

