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
from cache_manager import CacheManager
from background_scraper import BackgroundScraper
from content_scraper import SimpleCityScraper

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
    
    def __init__(self, cache_manager: CacheManager, background_scraper: BackgroundScraper):
        self.cache_manager = cache_manager
        self.background_scraper = background_scraper
        self.content_manager = ContentManager(cache_manager)
        self.user_sessions = {}

    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        await start_command(update, context, self)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        await help_command(update, context)
    
    async def cache_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show enhanced cache statistics with smart caching info."""
        try:
            stats = self.background_scraper.get_stats()
            cache_stats = stats['cache_stats']
            
            status_emoji = {
                'running': '🔄',
                'waiting': '⏳',
                'stopped': '⏹️',
                'error': '❌'
            }
            
            # Smart caching status
            initial_complete = getattr(self.background_scraper, '_initial_cache_complete', False)
            background_complete = getattr(self.background_scraper, '_background_cache_complete', False)
            
            smart_status = ""
            if initial_complete and background_complete:
                smart_status = "✅ All phases complete"
            elif initial_complete:
                smart_status = "🎯 Phase 1 complete, Phase 2 in progress"
            else:
                smart_status = "🚀 Phase 1 in progress"
            
            message = f"""
📊 **Enhanced Cache Statistics**

**Smart Caching Status:** {smart_status}
• Phase 1 (Priority): {"✅ Complete" if initial_complete else "🔄 Running"}
• Phase 2 (Background): {"✅ Complete" if background_complete else "⏳ Pending" if initial_complete else "⏸️ Waiting"}

**SimpCity Content:**
• Cached Creators: {cache_stats['total_creators']}
• Content Items: {cache_stats['total_content_items']}
• Preview Images: {cache_stats['total_preview_images']}
• Video Links: {cache_stats['total_video_links']}

**OnlyFans/Coomer Data:**
• Cached Users: {cache_stats['total_onlyfans_users']}
• Cached Posts: {cache_stats['total_onlyfans_posts']}

**Database Info:**
• Size: {cache_stats['database_size_mb']} MB

**Background Scraper:**
{status_emoji.get(stats['current_status'], '❓')} Status: {stats['current_status']}
• Total Processed: {stats['total_processed']}
• Success Rate: {stats.get('success_rate', 0)*100:.1f}%
• Pending Retries: {stats.get('pending_retries', 0)}

**Performance:**
• Processing Rate: {stats['performance']['processing_rate']:.1f} creators/min
• Avg Time/Creator: {stats['performance']['average_time_per_creator']:.1f}s
• Active Workers: {stats['performance']['active_workers']}

**Last Refresh:** {stats.get('last_run', 'Never')[:19] if stats.get('last_run') else 'Never'}
**Next Refresh:** {stats.get('next_run', 'Not scheduled')[:19] if stats.get('next_run') else 'Not scheduled'}

💡 Smart caching prioritizes uncached creators first!
🔄 Periodic refresh every {self.background_scraper.refresh_interval.total_seconds()/3600:.0f} hours
            """
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing cache stats: {e}")
            await update.message.reply_text("❌ Failed to retrieve cache statistics.")

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
    
    # Initialize cache manager
    print("💾 Initializing cache manager...")
    cache_manager = CacheManager()
    cache_stats = cache_manager.get_cache_stats()
    print(f"✅ Cache ready: {cache_stats['total_creators']} creators, "
          f"{cache_stats['total_content_items']} items cached")
    
    # Initialize background scraper with enhanced multithreading and configurable settings
    print("🔄 Initializing enhanced background scraper...")
    scraper = SimpleCityScraper()
    
    # Get configuration from environment variables
    refresh_interval = int(config('CACHE_REFRESH_INTERVAL_HOURS', default=12))
    max_workers = int(config('SCRAPER_MAX_WORKERS', default=6))
    batch_size = int(config('SCRAPER_BATCH_SIZE', default=4))
    concurrent_requests = int(config('SCRAPER_CONCURRENT_REQUESTS', default=3))
    
    background_scraper = BackgroundScraper(
        cache_manager=cache_manager,
        scraper=scraper,
        refresh_interval_hours=refresh_interval,
        max_pages_per_creator=None,     # Scrape ALL pages per creator (unlimited)
        batch_size=batch_size,
        max_workers=max_workers,
        concurrent_requests=concurrent_requests
    )
    
    print(f"⚙️  Configuration:")
    print(f"   • Refresh interval: {refresh_interval} hours")
    print(f"   • Max workers: {max_workers}")
    print(f"   • Batch size: {batch_size}")
    print(f"   • Concurrent requests: {concurrent_requests}")
    
    # Smart caching strategy: Priority phase (uncached creators first)
    print("\n🚀 Starting SMART CACHING with priority system...")
    print("📥 PHASE 1: Caching uncached creators first (PRIORITY - blocks bot startup)")
    print("📥 PHASE 2: Refresh cached creators in background (after bot starts)")
    print("⚡ Enhanced features:")
    print("   • Smart priority system (uncached first)")
    print("   • Multithreaded processing with configurable workers")
    print("   • Intelligent rate limiting with adaptive delays")
    print("   • Rotating headers to avoid bot detection")
    print("   • Exponential backoff retry logic")
    print("   • Real-time performance monitoring")
    print("⏱️  Estimated priority phase time: 5-15 minutes (only uncached creators)")
    print("⏸️  Bot will START after priority phase completes.\n")
    
    import asyncio
    print("🎯 Starting PHASE 1: Priority caching (uncached creators only)...")
    asyncio.run(background_scraper.initialize_cache_from_csv(max_creators=None))  # None = unlimited
    print("✅ PHASE 1 complete! Bot can now start.\n")
    
    # Start background scraper for periodic updates and background caching
    background_scraper.start()
    print("✅ Enhanced background scraper started:")
    print(f"   • PHASE 2 will run in background (refresh cached creators)")
    print(f"   • Periodic full refresh every {refresh_interval} hours")
    print("   • Bot is now operational!\n")
    
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
    
    # Initialize bot with cache and scraper
    bot = FreeFansBot(cache_manager, background_scraper)
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("cache", bot.cache_stats_command))
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
    finally:
        # Stop background scraper on shutdown
        background_scraper.stop()
        print("✅ Background scraper stopped")
        print("👋 Bot shutdown complete")


if __name__ == '__main__':
    main()

