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
    reject_title_command, bulk_approve_command, bulk_reject_command, admin_stats_command,
    setupmainadmin_command, removemainadmin_command, confirmmainadminremoval_command,
    addadmin_command, removeadmin_command, addworker_command, removeworker_command,
    listadmins_command, listworkers_command, deletions_command, approvedelete_command,
    rejectdelete_command
)
from bot.worker_handlers import (
    handle_worker_reply, worker_stats_command, worker_help_command
)
# Import pool handlers
from bot.pool_handlers import get_pool_handlers
from bot.admin_pool_handlers import get_admin_pool_handlers
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
        
        # Initialize pool handlers
        self.pool_handlers = get_pool_handlers()
        self.admin_pool_handlers = get_admin_pool_handlers()

    
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
            db_info = f"• Storage: {cache_stats.get('storage_type', 'Supabase only')}\n"
            db_info += f"• Database Size: N/A (Supabase)\n"
            
            if cache_stats.get('supabase_enabled', True):
                db_info += f"• Supabase: ✅ Connected\n"
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
        # Check if this is admin setup password first
        from bot.admin_handlers import handle_admin_setup_password
        if await handle_admin_setup_password(update, context, self):
            return
        
        # Check if this is a pool custom amount message
        if await self.pool_handlers.handle_custom_amount_message(update, context):
            return
        
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
        query = update.callback_query
        data = query.data
        
        # Route pool-related callbacks to pool handlers
        if (data.startswith("view_pool_") or data.startswith("contribute_") or 
            data.startswith("custom_contribute_") or data == "my_balance" or 
            data == "my_contributions" or data.startswith("buy_stars_") or 
            data == "back_to_pools" or data == "buy_stars_menu" or
            data.startswith("join_pool_")):
            await self.pool_handlers.handle_pool_callback(update, context)
        # Route admin pool callbacks
        elif (data == "admin_pool_stats" or data == "admin_view_pools" or 
              data == "admin_cleanup_pools"):
            await self.admin_pool_handlers.handle_admin_callback(update, context)
        else:
            # Route to existing callback handler
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
    print("\n" + "="*60)
    print("⚡ PERFORMANCE OPTIMIZATIONS")
    print("="*60)
    
    # Check fast libraries
    try:
        from scrapers.parsers import USING_FAST_PARSER
        from scrapers.csv_handler import PANDAS_AVAILABLE, RAPIDFUZZ_AVAILABLE
        
        print(f"HTML Parser:   {'✅ selectolax (10-100x faster)' if USING_FAST_PARSER else '⚠️  lxml (fallback)'}")
        print(f"CSV Ops:       {'✅ pandas (10-100x faster)' if PANDAS_AVAILABLE else '⚠️  standard csv'}")
        print(f"Fuzzy Match:   {'✅ rapidfuzz (10-20x faster)' if RAPIDFUZZ_AVAILABLE else '⚠️  difflib (slow)'}")
        
        try:
            import ujson
            print(f"JSON:          ✅ ujson (2-4x faster)")
        except ImportError:
            print(f"JSON:          ⚠️  standard json")
        
        # Show recommendations
        missing = []
        if not USING_FAST_PARSER:
            missing.append("selectolax")
        if not PANDAS_AVAILABLE:
            missing.append("pandas")
        
        if missing:
            print(f"\n💡 Install for better speed: pip install {' '.join(missing)}")
    except Exception as e:
        logger.warning(f"Could not check optimization status: {e}")
    
    print("="*60 + "\n")
    
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
    application.add_handler(CommandHandler("setupmainadmin", lambda update, context: setupmainadmin_command(update, context, bot)))
    application.add_handler(CommandHandler("removemainadmin", lambda update, context: removemainadmin_command(update, context, bot)))
    application.add_handler(CommandHandler("confirmmainadminremoval", lambda update, context: confirmmainadminremoval_command(update, context, bot)))
    application.add_handler(CommandHandler("addadmin", addadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
    application.add_handler(CommandHandler("addworker", addworker_command))
    application.add_handler(CommandHandler("removeworker", removeworker_command))
    application.add_handler(CommandHandler("listadmins", listadmins_command))
    application.add_handler(CommandHandler("listworkers", listworkers_command))
    application.add_handler(CommandHandler("deletions", deletions_command))
    application.add_handler(CommandHandler("approvedelete", approvedelete_command))
    application.add_handler(CommandHandler("rejectdelete", rejectdelete_command))
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
    
    # Pool commands
    application.add_handler(CommandHandler("pools", bot.pool_handlers.handle_pools_command))
    
    # Create a wrapper for balance command
    async def balance_command_wrapper(update, context):
        # Create a fake callback query for the balance handler
        from telegram import CallbackQuery
        fake_query = type('FakeQuery', (), {
            'from_user': update.effective_user,
            'message': update.message,
            'edit_message_text': update.message.reply_text,
            'answer': lambda: None
        })()
        await bot.pool_handlers._handle_my_balance(fake_query)
    
    application.add_handler(CommandHandler("balance", balance_command_wrapper))
    
    # Admin pool commands
    application.add_handler(CommandHandler("createpool", bot.admin_pool_handlers.handle_create_pool_command))
    application.add_handler(CommandHandler("poolstats", bot.admin_pool_handlers.handle_pool_stats_command))
    application.add_handler(CommandHandler("completepool", bot.admin_pool_handlers.handle_complete_pool_command))
    application.add_handler(CommandHandler("cancelpool", bot.admin_pool_handlers.handle_cancel_pool_command))
    application.add_handler(CommandHandler("poolrequests", bot.admin_pool_handlers.handle_requests_command))
    
    # Payment handlers
    from telegram.ext import PreCheckoutQueryHandler
    application.add_handler(PreCheckoutQueryHandler(bot.pool_handlers.handle_successful_payment))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, bot.pool_handlers.handle_successful_payment))
    
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

