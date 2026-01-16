"""
Coordinator Bot - Main bot that handles ALL Telegram communication.

This bot:
- Receives ALL Telegram updates
- Routes tasks to worker bots
- Formats responses for users
- NO business logic
"""

import logging
import os
import sys
import uuid
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest
from decouple import config

# Import coordinator components
from coordinator.session_manager import SessionManager
from coordinator.response_formatter import ResponseFormatter

# Import workers
from workers.distributed_registry import get_distributed_registry
from workers.base_worker import Task
from workers.search_worker.tasks import SearchTask
from workers.content_worker.tasks import LoadContentTask, LoadMorePagesTask

# Import existing components
from core.content_manager import ContentManager
from managers.cache_factory import get_cache_manager
from managers.permissions_manager import get_permissions_manager
from managers.request_manager import get_request_manager
from managers.title_manager import get_title_manager

# Import UI components
from bot.ui_components import (
    format_directory_text, create_content_directory_keyboard,
    create_picture_navigation_keyboard, create_video_navigation_keyboard
)
from bot.utilities import send_message_with_retry

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)


class CoordinatorBot:
    """Main coordinator bot - handles Telegram communication only."""
    
    def __init__(self):
        """Initialize coordinator bot."""
        # Coordinator components
        self.session_manager = SessionManager()
        self.formatter = ResponseFormatter()
        
        # Use distributed worker registry
        redis_url = config('REDIS_URL', default='redis://localhost:6379')
        self.worker_registry = get_distributed_registry(redis_url)
        
        # Initialize content manager and cache
        self.cache_manager = get_cache_manager()
        self.content_manager = ContentManager(self.cache_manager)
        
        logger.info("✅ Coordinator Bot initialized (distributed mode)")
        logger.info(f"✅ Redis URL: {redis_url}")
    
    # ==================== COMMAND HANDLERS ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        welcome_text = """
🔥 Welcome to FreeFans Bot 🔥

Your personal gateway to exclusive creator content

What I can do for you:

🔍 Search any creator instantly
🖼️ Browse hot photo galleries
🎬 Stream premium videos
📱 Access OnlyFans archives

💋 Use the menu buttons below to get started!
"""
        
        keyboard = [
            [KeyboardButton("🔍 Search Creator")],
            [KeyboardButton("🎲 Random Creator")],
            [KeyboardButton("📝 Request Creator"), KeyboardButton("🎯 Request Content")],
            [KeyboardButton("❓ Help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        help_text = """
📖 FreeFans Bot Help 📖

🔍 Search Creator
Type any creator's name and I'll find their hottest content.

🎲 Random Creator
Get a random creator with lots of content (25+ items).

📝 Request Creator
Don't see a creator? Request them to be added!

🎯 Request Content  
Looking for specific content from a creator? Let me know!

⚡ Quick Commands
/start - Get started with the bot
/help - Show this guide again
/cancel - Cancel current operation
"""
        
        # Add admin commands if user is admin
        if permissions.is_main_admin(user_id):
            help_text += "\n\n👑 **Main Admin Commands:**\n\n"
            help_text += "/addadmin <user_id> - Add a sub-admin\n"
            help_text += "/removeadmin <user_id> - Remove a sub-admin\n"
            help_text += "/addworker <user_id> - Add a worker\n"
            help_text += "/removeworker <user_id> - Remove a worker\n"
            help_text += "/listadmins - List all admins\n"
            help_text += "/listworkers - List all workers\n"
            help_text += "/requests - View pending user requests\n"
            help_text += "/titles - View pending title submissions\n"
            help_text += "/adminstats - View system statistics\n"
        elif permissions.is_admin(user_id):
            help_text += "\n\n🔧 **Admin Commands:**\n\n"
            help_text += "/addworker <user_id> - Add a worker\n"
            help_text += "/removeworker <user_id> - Remove a worker\n"
            help_text += "/listworkers - List all workers\n"
            help_text += "/requests - View pending user requests\n"
            help_text += "/titles - View pending title submissions\n"
            help_text += "/adminstats - View system statistics\n"
        
        # Add worker commands if user is worker
        if permissions.is_worker(user_id):
            help_text += "\n\n👷 **Worker Commands:**\n\n"
            help_text += "Reply to videos with titles to submit\n"
            help_text += "/mystats - View your submission stats\n"
        
        keyboard = [
            [KeyboardButton("🔍 Search Creator")],
            [KeyboardButton("🎲 Random Creator")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(help_text, reply_markup=reply_markup)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command."""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        # Clear session state
        session.awaiting_request = None
        session.pending_creator_options = None
        session.pending_creator_name = None
        session.request_data = {}
        
        keyboard = [
            [KeyboardButton("🔍 Search Creator")],
            [KeyboardButton("🎲 Random Creator")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "❌ Operation cancelled. Use the menu buttons to start again.",
            reply_markup=reply_markup
        )
    
    # ==================== ADMIN COMMANDS ====================
    
    async def admin_requests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View all pending requests (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        request_manager = get_request_manager()
        creator_requests = request_manager.get_pending_creator_requests()
        content_requests = request_manager.get_pending_content_requests()
        
        if not creator_requests and not content_requests:
            await update.message.reply_text("📭 No pending requests at the moment.")
            return
        
        message = "📋 **Pending Requests**\n\n"
        
        if creator_requests:
            message += f"🎭 **Creator Requests ({len(creator_requests)}):**\n\n"
            for req in creator_requests[:10]:
                message += f"🆔 {req['request_id']}\n"
                message += f"👤 User: {req['user_id']}\n"
                message += f"📱 Platform: {req['platform']}\n"
                message += f"👥 Username: {req['username']}\n"
                message += f"📅 {req['timestamp'][:10]}\n"
                message += "─" * 30 + "\n"
            
            if len(creator_requests) > 10:
                message += f"\n... and {len(creator_requests) - 10} more\n\n"
        
        if content_requests:
            message += f"\n🎯 **Content Requests ({len(content_requests)}):**\n\n"
            for req in content_requests[:10]:
                message += f"🆔 {req['request_id']}\n"
                message += f"👤 User: {req['user_id']}\n"
                message += f"📱 Platform: {req['platform']}\n"
                message += f"👥 Username: {req['username']}\n"
                message += f"📝 Details: {req['content_details'][:50]}...\n"
                message += f"📅 {req['timestamp'][:10]}\n"
                message += "─" * 30 + "\n"
            
            if len(content_requests) > 10:
                message += f"\n... and {len(content_requests) - 10} more\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View system statistics (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        request_manager = get_request_manager()
        req_stats = request_manager.get_request_stats()
        
        workers = permissions.get_workers()
        
        message = "📊 **System Statistics**\n\n"
        message += "📋 **User Requests:**\n"
        message += f"• Creator requests: {req_stats['total_creator_requests']}\n"
        message += f"• Content requests: {req_stats['total_content_requests']}\n"
        message += f"• Pending creator: {req_stats['pending_creator_requests']}\n"
        message += f"• Pending content: {req_stats['pending_content_requests']}\n\n"
        message += f"👥 **Users:**\n"
        message += f"• Admins: {len(permissions.get_admins())}\n"
        message += f"• Workers: {len(workers)}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def addadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a sub-admin (main admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_main_admin(user_id):
            await update.message.reply_text("❌ Only the main admin can add sub-admins.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/addadmin <user_id>`\n\nExample: `/addadmin 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return
        
        success = permissions.add_admin(target_user_id)
        
        if success:
            await update.message.reply_text(
                f"✅ User `{target_user_id}` has been added as a sub-admin.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ User `{target_user_id}` is already a sub-admin.",
                parse_mode='Markdown'
            )
    
    async def removeadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a sub-admin (main admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_main_admin(user_id):
            await update.message.reply_text("❌ Only the main admin can remove sub-admins.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/removeadmin <user_id>`\n\nExample: `/removeadmin 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return
        
        success = permissions.remove_admin(target_user_id)
        
        if success:
            await update.message.reply_text(
                f"✅ User `{target_user_id}` has been removed as a sub-admin.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ User `{target_user_id}` is not a sub-admin.",
                parse_mode='Markdown'
            )
    
    async def addworker_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a worker (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ Only admins can add workers.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/addworker <user_id>`\n\nExample: `/addworker 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return
        
        success = permissions.add_worker(target_user_id)
        
        if success:
            await update.message.reply_text(
                f"✅ User `{target_user_id}` has been added as a worker.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ User `{target_user_id}` is already a worker.",
                parse_mode='Markdown'
            )
    
    async def removeworker_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a worker (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ Only admins can remove workers.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/removeworker <user_id>`\n\nExample: `/removeworker 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Must be a number.")
            return
        
        success = permissions.remove_worker(target_user_id)
        
        if success:
            await update.message.reply_text(
                f"✅ User `{target_user_id}` has been removed as a worker.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"⚠️ User `{target_user_id}` is not a worker.",
                parse_mode='Markdown'
            )
    
    async def listadmins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all admins (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ Only admins can view the admin list.")
            return
        
        main_admin = permissions.get_main_admin()
        admins = permissions.get_admins()
        
        message = "👑 **Admin List**\n\n"
        
        if main_admin:
            message += f"**Main Admin:** `{main_admin}`\n\n"
        else:
            message += "**Main Admin:** None\n\n"
        
        if admins:
            message += f"**Sub-Admins ({len(admins)}):**\n"
            for admin_id in admins:
                if admin_id != main_admin:
                    message += f"• `{admin_id}`\n"
        else:
            message += "**Sub-Admins:** None\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def listworkers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all workers (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ Only admins can view the worker list.")
            return
        
        workers = permissions.get_workers()
        
        message = "👷 **Worker List**\n\n"
        
        if workers:
            message += f"**Workers ({len(workers)}):**\n"
            for worker_id in workers:
                message += f"• `{worker_id}`\n"
        else:
            message += "**Workers:** None\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def worker_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View worker's own statistics."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_worker(user_id):
            await update.message.reply_text(
                "❌ You are not registered as a worker.\n\n"
                "Workers can submit video titles for approval."
            )
            return
        
        title_manager = get_title_manager()
        stats = title_manager.get_worker_stats(user_id)
        
        message = f"📊 **Your Worker Statistics**\n\n"
        message += f"👷 Worker ID: `{user_id}`\n\n"
        message += "📝 **Title Submissions:**\n"
        message += f"• ⏳ Pending: {stats['pending']}\n"
        message += f"• ✅ Approved: {stats['approved']}\n"
        message += f"• ❌ Rejected: {stats['rejected']}\n"
        message += f"• 📊 Total: {stats['total']}\n"
        
        if stats['total'] > 0:
            approval_rate = (stats['approved'] / stats['total']) * 100
            message += f"\n✨ Approval Rate: {approval_rate:.1f}%\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def cache_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show cache statistics."""
        try:
            cache_stats = self.cache_manager.get_cache_stats()
            
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
    
    async def titles_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View pending title submissions (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        title_manager = get_title_manager()
        pending = title_manager.get_pending_titles()
        
        if not pending:
            await update.message.reply_text("📭 No pending title submissions.")
            return
        
        message = f"📝 **Pending Title Submissions ({len(pending)}):**\n\n"
        
        for submission in pending[:15]:
            message += f"🆔 {submission['submission_id']}\n"
            message += f"👷 Worker: {submission['worker_username']} (ID: {submission['worker_id']})\n"
            message += f"👤 Creator: {submission['creator_name']}\n"
            message += f"🎬 Title: {submission['suggested_title']}\n"
            message += f"🔗 URL: {submission['video_url'][:50]}...\n"
            message += f"📅 {submission['timestamp'][:10]}\n"
            message += "─" * 30 + "\n"
        
        if len(pending) > 15:
            message += f"\n... and {len(pending) - 15} more\n"
        
        message += "\n💡 **Commands:**\n"
        message += "• `/approve <submission_id>` - Approve a title\n"
        message += "• `/reject <submission_id>` - Reject a title\n"
        message += "• `/bulkapprove <worker_id>` - Approve all from a worker\n"
        message += "• `/bulkreject <worker_id>` - Reject all from a worker\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def approve_title_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve a title submission (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/approve <submission_id>`\n\nExample: `/approve TS-20251223120000-123456789`",
                parse_mode='Markdown'
            )
            return
        
        submission_id = context.args[0]
        title_manager = get_title_manager()
        
        submission = title_manager.approve_title(submission_id, user_id)
        
        if not submission:
            await update.message.reply_text(f"❌ Submission `{submission_id}` not found.", parse_mode='Markdown')
            return
        
        video_url = submission['video_url']
        new_title = submission['suggested_title']
        
        updated = self.cache_manager.update_video_title(video_url, new_title)
        
        message = f"✅ **Title Approved!**\n\n"
        message += f"🆔 {submission_id}\n"
        message += f"👷 Worker: {submission['worker_username']}\n"
        message += f"👤 Creator: {submission['creator_name']}\n"
        message += f"🎬 Title: {new_title}\n"
        
        if updated:
            message += "\n✓ Cache updated successfully!"
        else:
            message += "\n⚠️ Video not found in cache (title saved anyway)"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def reject_title_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reject a title submission (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/reject <submission_id>`\n\nExample: `/reject TS-20251223120000-123456789`",
                parse_mode='Markdown'
            )
            return
        
        submission_id = context.args[0]
        title_manager = get_title_manager()
        
        submission = title_manager.reject_title(submission_id, user_id, 'Rejected by admin')
        
        if not submission:
            await update.message.reply_text(f"❌ Submission `{submission_id}` not found.", parse_mode='Markdown')
            return
        
        message = f"❌ **Title Rejected**\n\n"
        message += f"🆔 {submission_id}\n"
        message += f"👷 Worker: {submission['worker_username']}\n"
        message += f"👤 Creator: {submission['creator_name']}\n"
        message += f"🎬 Title: {submission['suggested_title']}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def bulkapprove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bulk approve all titles from a worker (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/bulkapprove <worker_id>`\n\nExample: `/bulkapprove 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            worker_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid worker ID. Must be a number.")
            return
        
        title_manager = get_title_manager()
        pending = title_manager.get_pending_titles(worker_id=worker_id)
        
        if not pending:
            await update.message.reply_text(f"📭 No pending titles from worker {worker_id}.")
            return
        
        await update.message.reply_text(f"⏳ Approving {len(pending)} titles from worker {worker_id}...")
        
        approved = title_manager.bulk_approve_worker(worker_id, user_id)
        
        updated_count = 0
        for submission in approved:
            if self.cache_manager.update_video_title(submission['video_url'], submission['suggested_title']):
                updated_count += 1
        
        message = f"✅ **Bulk Approval Complete!**\n\n"
        message += f"👷 Worker ID: {worker_id}\n"
        message += f"✓ Approved: {len(approved)} titles\n"
        message += f"💾 Cache updated: {updated_count} videos\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def bulkreject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bulk reject all titles from a worker (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/bulkreject <worker_id>`\n\nExample: `/bulkreject 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            worker_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid worker ID. Must be a number.")
            return
        
        title_manager = get_title_manager()
        pending = title_manager.get_pending_titles(worker_id=worker_id)
        
        if not pending:
            await update.message.reply_text(f"📭 No pending titles from worker {worker_id}.")
            return
        
        await update.message.reply_text(f"⏳ Rejecting {len(pending)} titles from worker {worker_id}...")
        
        rejected = title_manager.bulk_reject_worker(worker_id, user_id, reason='Bulk rejected by admin')
        
        message = f"❌ **Bulk Rejection Complete!**\n\n"
        message += f"👷 Worker ID: {worker_id}\n"
        message += f"✗ Rejected: {len(rejected)} titles\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def deletions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View pending deletion requests (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        title_manager = get_title_manager()
        pending = title_manager.get_pending_deletion_requests()
        
        if not pending:
            await update.message.reply_text("📭 No pending deletion requests.")
            return
        
        message = f"🗑️ **Pending Deletion Requests ({len(pending)}):**\n\n"
        
        for request in pending[:15]:
            message += f"🆔 {request['request_id']}\n"
            message += f"👷 Worker: {request['worker_username']} (ID: {request['worker_id']})\n"
            message += f"👤 Creator: {request['creator_name']}\n"
            message += f"🎬 Video: {request['video_title']}\n"
            message += f"🔗 URL: {request['video_url'][:50]}...\n"
            message += f"📅 {request['timestamp'][:10]}\n"
            message += "─" * 30 + "\n"
        
        if len(pending) > 15:
            message += f"\n... and {len(pending) - 15} more\n"
        
        message += "\n💡 **Commands:**\n"
        message += "• `/approvedelete <request_id>` - Approve deletion\n"
        message += "• `/rejectdelete <request_id>` - Reject deletion\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def approvedelete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve a deletion request (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/approvedelete <request_id>`\n\nExample: `/approvedelete DR-20260106120000-123456789`",
                parse_mode='Markdown'
            )
            return
        
        request_id = context.args[0]
        title_manager = get_title_manager()
        
        request = title_manager.approve_deletion_request(request_id, user_id)
        
        if not request:
            await update.message.reply_text(f"❌ Request `{request_id}` not found.", parse_mode='Markdown')
            return
        
        video_url = request['video_url']
        deleted = self.cache_manager.delete_video(video_url)
        
        message = f"✅ **Deletion Approved!**\n\n"
        message += f"🆔 {request_id}\n"
        message += f"👷 Worker: {request['worker_username']}\n"
        message += f"👤 Creator: {request['creator_name']}\n"
        message += f"🎬 Video: {request['video_title']}\n"
        
        if deleted:
            message += "\n✓ Video deleted from cache!"
        else:
            message += "\n⚠️ Video not found in cache (request marked as approved)"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def rejectdelete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reject a deletion request (admin only)."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Usage: `/rejectdelete <request_id>`\n\nExample: `/rejectdelete DR-20260106120000-123456789`",
                parse_mode='Markdown'
            )
            return
        
        request_id = context.args[0]
        title_manager = get_title_manager()
        
        request = title_manager.reject_deletion_request(request_id, user_id, 'Rejected by admin')
        
        if not request:
            await update.message.reply_text(f"❌ Request `{request_id}` not found.", parse_mode='Markdown')
            return
        
        message = f"❌ **Deletion Rejected**\n\n"
        message += f"🆔 {request_id}\n"
        message += f"👷 Worker: {request['worker_username']}\n"
        message += f"👤 Creator: {request['creator_name']}\n"
        message += f"🎬 Video: {request['video_title']}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def workerhelp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show worker help information."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_worker(user_id):
            await update.message.reply_text("❌ You are not registered as a worker.")
            return
        
        message = """
📘 **Worker Guide**

Welcome, worker! Your job is to help improve video titles in our content library.

**How to Submit Titles:**

1️⃣ Find a video in the content library
2️⃣ Reply to the video message
3️⃣ Type your suggested title in the reply
4️⃣ Wait for admin approval

**How to Report Broken Videos:**

🗑️ If a video link is broken or not found:
1️⃣ Reply to the video message
2️⃣ Type: `NOT FOUND`
3️⃣ The video will be removed from the database

**Good Title Examples:**
✅ "Hot Tub Stream - Bikini Try-On Haul"
✅ "Beach Photoshoot Behind The Scenes"
✅ "Exclusive Private Show Highlights"

**Bad Title Examples:**
❌ "video1"
❌ "untitled"
❌ "watch this"

**Guidelines:**
• Be descriptive and accurate
• Keep titles under 200 characters
• Include key details (location, activity, etc.)
• Avoid clickbait or misleading titles
• Use proper capitalization
• Report broken videos with "NOT FOUND"

**Commands:**
• /mystats - View your submission statistics
• /workerhelp - Show this help message

💡 Tip: The more titles you submit that get approved, the higher your approval rate!
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def setupmainadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Setup the main admin - first time only, password protected."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if permissions.has_main_admin():
            await update.message.reply_text(
                "❌ Main admin already configured. Only the current main admin can remove themselves."
            )
            return
        
        session = self.session_manager.get_session(user_id)
        session.awaiting_admin_setup_password = True
        
        await update.message.reply_text(
            "🔐 To become the main admin, please enter the setup password:\n\n"
            "⚠️ Warning: Send the password as a regular message (not a command)."
        )
        logger.info(f"User {user_id} initiated main admin setup")
    
    async def removemainadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove yourself as main admin - confirmation required."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        if not permissions.is_main_admin(user_id):
            await update.message.reply_text(
                "❌ Only the main admin can remove themselves."
            )
            return
        
        session = self.session_manager.get_session(user_id)
        session.awaiting_admin_removal_confirmation = True
        
        await update.message.reply_text(
            "⚠️ **Are you sure you want to remove yourself as main admin?**\n\n"
            "This will allow someone else to become main admin using /setupmainadmin\n\n"
            "Send `/confirmmainadminremoval` to confirm, or /cancel to abort.",
            parse_mode='Markdown'
        )
        logger.info(f"Main admin {user_id} requested removal confirmation")
    
    async def confirmmainadminremoval_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm removal of main admin status."""
        user_id = update.effective_user.id
        permissions = get_permissions_manager()
        
        session = self.session_manager.get_session(user_id)
        
        if not session.awaiting_admin_removal_confirmation:
            await update.message.reply_text(
                "❌ No removal request in progress. Use /removemainadmin first."
            )
            return
        
        if not permissions.is_main_admin(user_id):
            session.awaiting_admin_removal_confirmation = False
            await update.message.reply_text(
                "❌ You are not the main admin."
            )
            return
        
        session.awaiting_admin_removal_confirmation = False
        success = permissions.remove_main_admin()
        
        if success:
            await update.message.reply_text(
                "✅ You have been removed as main admin.\n\n"
                "Someone else can now set up as main admin using /setupmainadmin"
            )
            logger.info(f"Main admin {user_id} removed themselves")
        else:
            await update.message.reply_text(
                "❌ Failed to remove main admin. Please try again."
            )
            logger.error(f"Failed to remove main admin {user_id}")
    
    async def _handle_admin_setup_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, session) -> bool:
        """Handle password verification for main admin setup. Returns True if handled."""
        if not session.awaiting_admin_setup_password:
            return False
        
        session.awaiting_admin_setup_password = False
        provided_password = text
        
        try:
            correct_password = config('ADMIN_SETUP_PASSWORD')
        except Exception as e:
            logger.error(f"Failed to get ADMIN_SETUP_PASSWORD from .env: {e}")
            await update.message.reply_text(
                "❌ Server configuration error. Please contact the developer."
            )
            return True
        
        if provided_password == correct_password:
            permissions = get_permissions_manager()
            success = permissions.set_main_admin(update.effective_user.id)
            
            if success:
                await update.message.reply_text(
                    "🎉 **Congratulations!** You are now the main admin!\n\n"
                    "As the main admin, you can:\n"
                    "• Add and remove sub-admins\n"
                    "• Add and remove workers\n"
                    "• Use all admin commands\n\n"
                    "Use /help to see available commands.",
                    parse_mode='Markdown'
                )
                logger.info(f"User {update.effective_user.id} successfully became main admin")
            else:
                await update.message.reply_text(
                    "❌ Setup failed. Main admin may have been set by someone else."
                )
                logger.error(f"Failed to set user {update.effective_user.id} as main admin")
        else:
            await update.message.reply_text(
                "❌ Incorrect password. Setup cancelled.\n\n"
                "If you need to try again, use /setupmainadmin"
            )
            logger.warning(f"User {update.effective_user.id} provided incorrect admin setup password")
        
        return True
    
    # ==================== MESSAGE HANDLER ====================
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        session = self.session_manager.get_session(user_id)
        
        # Handle admin setup password
        if await self._handle_admin_setup_password(update, context, text, session):
            return
        
        # Handle menu buttons
        if text == "🔍 Search Creator":
            session.awaiting_request = 'search'
            await update.message.reply_text("🔍 Please send me the name of the creator you want to search for:")
            return
        
        elif text == "🎲 Random Creator":
            await self._handle_random_creator(update, context)
            return
        
        elif text == "📝 Request Creator":
            session.awaiting_request = 'creator_platform'
            session.request_data = {'type': 'creator'}
            await update.message.reply_text(
                "📝 Request New Creator\n\n"
                "Step 1/2: What social media platform?\n\n"
                "Examples: OnlyFans, Instagram, Twitter/X, TikTok, Fansly\n\n"
                "📝 Send /cancel to cancel"
            )
            return
        
        elif text == "🎯 Request Content":
            session.awaiting_request = 'content_platform'
            session.request_data = {'type': 'content'}
            await update.message.reply_text(
                "🎯 Request Specific Content\n\n"
                "Step 1/3: What social media platform is the creator on?\n\n"
                "Examples: OnlyFans, Instagram, Twitter/X, TikTok, Fansly\n\n"
                "📝 Send /cancel to cancel"
            )
            return
        
        elif text == "❓ Help":
            await self.help_command(update, context)
            return
        
        # Handle request flows
        if await self._handle_request_flow(update, context, text, session):
            return
        
        # Handle search input
        if session.awaiting_request == 'search':
            await self._handle_search(update, context, text, session)
            return
        
        # Default response
        keyboard = [
            [KeyboardButton("🔍 Search Creator")],
            [KeyboardButton("🎲 Random Creator")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "💡 Please use the menu buttons below to search or make a request.",
            reply_markup=reply_markup
        )
    
    async def _handle_request_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, session) -> bool:
        """Handle multi-step request flow. Returns True if handled."""
        if not session.awaiting_request or session.awaiting_request == 'search':
            return False
        
        request_manager = get_request_manager()
        
        # Creator request flow
        if session.awaiting_request == 'creator_platform':
            session.request_data['platform'] = text
            session.awaiting_request = 'creator_username'
            await update.message.reply_text(
                f"📝 Request New Creator\n\n"
                f"Platform: {text}\n\n"
                f"Step 2/2: What is the creator's username?\n\n"
                f"📝 Send /cancel to cancel"
            )
            return True
        
        elif session.awaiting_request == 'creator_username':
            session.request_data['username'] = text
            session.awaiting_request = None
            
            platform = session.request_data.get('platform', 'Unknown')
            username = text
            
            request_id = request_manager.save_creator_request(session.user_id, platform, username)
            
            keyboard = [
                [KeyboardButton("🔍 Search Creator")],
                [KeyboardButton("🎲 Random Creator")],
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"✅ Request Submitted!\n\n"
                f"📋 Request ID: {request_id}\n"
                f"Platform: {platform}\n"
                f"Username: {username}\n\n"
                f"⏰ New creators are typically added within 24-48 hours.",
                reply_markup=reply_markup
            )
            
            session.request_data = {}
            return True
        
        # Content request flow
        elif session.awaiting_request == 'content_platform':
            session.request_data['platform'] = text
            session.awaiting_request = 'content_username'
            await update.message.reply_text(
                f"🎯 Request Specific Content\n\n"
                f"Platform: {text}\n\n"
                f"Step 2/3: What is the creator's username?\n\n"
                f"📝 Send /cancel to cancel"
            )
            return True
        
        elif session.awaiting_request == 'content_username':
            session.request_data['username'] = text
            session.awaiting_request = 'content_details'
            await update.message.reply_text(
                f"🎯 Request Specific Content\n\n"
                f"Platform: {session.request_data.get('platform')}\n"
                f"Username: {text}\n\n"
                f"Step 3/3: What specific content are you looking for?\n\n"
                f"Be as detailed as possible.\n\n"
                f"📝 Send /cancel to cancel"
            )
            return True
        
        elif session.awaiting_request == 'content_details':
            session.request_data['details'] = text
            session.awaiting_request = None
            
            platform = session.request_data.get('platform', 'Unknown')
            username = session.request_data.get('username', 'Unknown')
            details = text
            
            request_id = request_manager.save_content_request(session.user_id, platform, username, details)
            
            keyboard = [
                [KeyboardButton("🔍 Search Creator")],
                [KeyboardButton("🎲 Random Creator")],
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"✅ Content Request Submitted!\n\n"
                f"📋 Request ID: {request_id}\n"
                f"Platform: {platform}\n"
                f"Username: {username}\n\n"
                f"⏰ Specific content requests are typically fulfilled within 2-3 days.",
                reply_markup=reply_markup
            )
            
            session.request_data = {}
            return True
        
        return False
    
    async def _handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, session):
        """Handle creator search."""
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
            
            # Execute via worker
            result = await self.worker_registry.execute_task(task)
            
            if not result.success:
                error_msg = self.formatter.format_error(result.error)
                await search_message.edit_text(error_msg)
                return
            
            # Format and display results
            needs_selection = result.metadata.get('needs_selection', False)
            
            if needs_selection:
                # Store options in session
                session.pending_creator_options = result.data.get('creators', [])
                session.pending_creator_name = query
                session.creator_selection_page = 0
                
                # Show selection menu
                await self._show_creator_selection(search_message, session, result.data)
            else:
                # Single result - load content directly
                creators = result.data.get('creators', [])
                if creators:
                    creator = creators[0]
                    await self._load_creator_content(
                        search_message,
                        session,
                        creator['name'],
                        creator['url']
                    )
            
            # Clear awaiting state
            session.awaiting_request = None
            
        except Exception as e:
            logger.exception(f"Error handling search: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
    
    async def _show_creator_selection(self, message, session, search_data):
        """Show creator selection menu."""
        creators = search_data.get('creators', [])
        query = search_data.get('query', '')
        source = search_data.get('source', 'csv')
        
        if source == 'simpcity':
            text = f"🔥 Extended Search Results 🔥\n\n"
            text += f"Found {len(creators)} matches for '{query}'\n\n"
        else:
            text = f"✨ Found {len(creators)} creators ✨\n\n"
            text += f"Searching for: '{query}'\n\n"
        
        text += "Select the creator you want 👇\n"
        
        # Create keyboard
        keyboard = []
        for i, creator in enumerate(creators[:10]):  # Show first 10
            name = creator['name']
            if len(name) > 60:
                name = name[:57] + "..."
            keyboard.append([InlineKeyboardButton(name, callback_data=f"select_creator|{i}")])
        
        # Add search more button for CSV results
        if source == 'csv':
            keyboard.append([InlineKeyboardButton("🔍 Not found? Search More", callback_data="search_on_simpcity")])
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(text, reply_markup=reply_markup)
    
    async def _load_creator_content(self, message, session, creator_name, creator_url):
        """Load content for a selected creator."""
        try:
            # Show loading message
            await message.edit_text(f"✅ Selected: {creator_name}\n🔄 Loading content...")
            
            # Create load content task
            task = Task(
                task_id=str(uuid.uuid4()),
                user_id=session.user_id,
                task_type='load_content',
                params=LoadContentTask(
                    creator_name=creator_name,
                    creator_url=creator_url,
                    filters=getattr(session, 'filters', None),
                    cache_only=True
                ).to_dict()
            )
            
            # Execute via worker
            result = await self.worker_registry.execute_task(task)
            
            if not result.success:
                await message.edit_text(f"❌ Failed to load content for '{creator_name}'.")
                return
            
            # Get content directory
            content_directory = result.data['content_directory']
            
            # Check if empty
            total_pictures = len(content_directory.get('preview_images', []))
            total_videos = len(content_directory.get('video_links', []))
            total_items = len(content_directory.get('items', []))
            
            if total_pictures == 0 and total_videos == 0 and total_items == 0:
                await message.edit_text(
                    f"📭 No content currently available for '{creator_name}'.\n\n"
                    f"This creator's thread may be empty or all content has been filtered out."
                )
                return
            
            # Store in session
            session.current_directory = content_directory
            session.current_creator = creator_name
            
            # Display content directory
            directory_text = format_directory_text(creator_name, content_directory, getattr(session, 'filters', {}))
            
            has_more_pages = content_directory.get('has_more_pages', False)
            social_links = content_directory.get('social_links', {})
            has_onlyfans = social_links.get('onlyfans') is not None
            
            reply_markup = create_content_directory_keyboard(
                total_pictures, total_videos, has_onlyfans, has_more_pages
            )
            
            await message.edit_text(directory_text, reply_markup=reply_markup, disable_web_page_preview=True)
            
        except Exception as e:
            logger.exception(f"Error loading creator content: {e}")
            await message.edit_text("❌ An error occurred while loading content.")
    
    async def _handle_random_creator(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle random creator request."""
        try:
            loading_msg = await update.message.reply_text("🎲 Finding a random creator with lots of content...")
            
            # Create task
            task = Task(
                task_id=str(uuid.uuid4()),
                user_id=update.effective_user.id,
                task_type='get_random_creator',
                params={'min_items': 25}
            )
            
            # Execute via worker
            result = await self.worker_registry.execute_task(task)
            
            if not result.success:
                await loading_msg.edit_text("❌ No creators found with enough content. Try searching for a specific creator!")
                return
            
            # Load the random creator
            creator_name = result.data['creator_name']
            creator_url = result.data['creator_url']
            
            session = self.session_manager.get_session(update.effective_user.id)
            await self._load_creator_content(loading_msg, session, creator_name, creator_url)
            
        except Exception as e:
            logger.exception(f"Error getting random creator: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
    
    # ==================== CALLBACK HANDLER ====================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        session = self.session_manager.get_session(user_id)
        
        # Route callbacks
        if data.startswith("select_creator|"):
            await self._handle_select_creator(query, session, data)
        elif data == "search_on_simpcity":
            await self._handle_search_simpcity(query, session)
        elif data == "cancel_search":
            await query.edit_message_text("❌ Search cancelled.")
        elif data == "search_creator":
            session.awaiting_request = 'search'
            await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")
        elif data == "view_pictures":
            await self._handle_view_pictures(query, session)
        elif data == "view_videos":
            await self._handle_view_videos(query, session)
        elif data == "load_more_pages":
            await self._handle_load_more_pages(query, session)
        elif data.startswith("picture_page_"):
            await self._handle_picture_page(query, session, data)
        elif data.startswith("video_page_"):
            await self._handle_video_page(query, session, data)
        elif data == "back_to_list":
            await self._handle_back_to_list(query, session)
        elif data == "view_of_feed":
            await self._handle_view_of_feed(query, session)
        else:
            await query.answer("Feature coming soon!", show_alert=True)
    
    async def _handle_select_creator(self, query, session, data):
        """Handle creator selection."""
        try:
            idx = int(data.split("|")[1])
            creators = session.pending_creator_options
            
            if not creators or idx >= len(creators):
                await query.edit_message_text("⚠️ Invalid selection")
                return
            
            selected = creators[idx]
            await self._load_creator_content(
                query.message,
                session,
                selected['name'],
                selected['url']
            )
            
        except Exception as e:
            logger.exception(f"Error selecting creator: {e}")
            await query.edit_message_text("❌ An error occurred.")
    
    async def _handle_search_simpcity(self, query, session):
        """Handle extended SimpCity search."""
        if not session.pending_creator_name:
            await query.edit_message_text("⚠️ Please start a new search.")
            return
        
        creator_name = session.pending_creator_name
        await query.edit_message_text(f"🔍 Performing extended search for '{creator_name}'...")
        
        # Create SimpCity search task
        task = Task(
            task_id=str(uuid.uuid4()),
            user_id=session.user_id,
            task_type='search_simpcity',
            params=SearchTask(query=creator_name).to_dict()
        )
        
        result = await self.worker_registry.execute_task(task)
        
        if not result.success or not result.data.get('creators'):
            await query.edit_message_text(f"❌ No additional results found for '{creator_name}'.")
            return
        
        # Show SimpCity results
        await self._show_creator_selection(query.message, session, result.data)
    
    async def _handle_view_pictures(self, query, session):
        """Handle view pictures request."""
        if not session.current_directory:
            await query.edit_message_text("⚠️ No content available.")
            return
        
        pictures = session.current_directory.get('preview_images', [])
        if not pictures:
            await query.answer("No pictures available", show_alert=True)
            return
        
        # Show first picture
        await self._show_picture_page(query.message, session, 0)
    
    async def _handle_view_videos(self, query, session):
        """Handle view videos request."""
        if not session.current_directory:
            await query.edit_message_text("⚠️ No content available.")
            return
        
        videos = session.current_directory.get('video_links', [])
        if not videos:
            await query.answer("No videos available", show_alert=True)
            return
        
        # Show first video
        await self._show_video_page(query.message, session, 0)
    
    async def _show_picture_page(self, message, session, page):
        """Show a picture page."""
        pictures = session.current_directory.get('preview_images', [])
        if page < 0 or page >= len(pictures):
            return
        
        picture = pictures[page]
        text = f"🖼️ Picture {page + 1} of {len(pictures)}\n\n"
        text += f"📎 {picture['url']}\n"
        
        keyboard = create_picture_navigation_keyboard(page, len(pictures))
        await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    
    async def _show_video_page(self, message, session, page):
        """Show a video page."""
        videos = session.current_directory.get('video_links', [])
        if page < 0 or page >= len(videos):
            return
        
        video = videos[page]
        text = f"🎬 Video {page + 1} of {len(videos)}\n\n"
        text += f"Title: {video.get('title', 'Untitled')}\n"
        text += f"📎 {video['url']}\n"
        
        keyboard = create_video_navigation_keyboard(page, len(videos))
        await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    
    async def _handle_picture_page(self, query, session, data):
        """Handle picture pagination."""
        page = int(data.split("_")[-1])
        await self._show_picture_page(query.message, session, page)
    
    async def _handle_video_page(self, query, session, data):
        """Handle video pagination."""
        page = int(data.split("_")[-1])
        await self._show_video_page(query.message, session, page)
    
    async def _handle_load_more_pages(self, query, session):
        """Handle load more pages request."""
        if not session.current_directory or not session.current_creator:
            await query.edit_message_text("⚠️ No content available.")
            return
        
        await query.edit_message_text(f"⏳ Loading more content for '{session.current_creator}'...")
        
        # Create load more pages task
        task = Task(
            task_id=str(uuid.uuid4()),
            user_id=session.user_id,
            task_type='load_more_pages',
            params=LoadMorePagesTask(
                creator_name=session.current_creator,
                filters=getattr(session, 'filters', None),
                current_content=session.current_directory,
                pages_to_fetch=3
            ).to_dict()
        )
        
        result = await self.worker_registry.execute_task(task)
        
        if not result.success:
            await query.edit_message_text("⚠️ Failed to load more content.")
            return
        
        # Update session
        content_directory = result.data['content_directory']
        session.current_directory = content_directory
        
        # Display updated directory
        total_pictures = len(content_directory.get('preview_images', []))
        total_videos = len(content_directory.get('video_links', []))
        has_more_pages = content_directory.get('has_more_pages', False)
        social_links = content_directory.get('social_links', {})
        has_onlyfans = social_links.get('onlyfans') is not None
        
        directory_text = format_directory_text(session.current_creator, content_directory, getattr(session, 'filters', {}))
        reply_markup = create_content_directory_keyboard(total_pictures, total_videos, has_onlyfans, has_more_pages)
        
        await query.edit_message_text(directory_text, reply_markup=reply_markup, disable_web_page_preview=True)
    
    async def _handle_back_to_list(self, query, session):
        """Return to content directory."""
        if not session.current_directory:
            await query.edit_message_text("⚠️ No content available.")
            return
        
        creator_name = session.current_creator
        content_directory = session.current_directory
        total_pictures = len(content_directory.get('preview_images', []))
        total_videos = len(content_directory.get('video_links', []))
        has_more_pages = content_directory.get('has_more_pages', False)
        social_links = content_directory.get('social_links', {})
        has_onlyfans = social_links.get('onlyfans') is not None
        
        directory_text = format_directory_text(creator_name, content_directory, session.filters)
        reply_markup = create_content_directory_keyboard(total_pictures, total_videos, has_onlyfans, has_more_pages)
        
        await query.edit_message_text(directory_text, reply_markup=reply_markup, disable_web_page_preview=True)
    
    async def _handle_view_of_feed(self, query, session):
        """Handle OnlyFans feed view request."""
        if not session.current_directory:
            await query.edit_message_text("⚠️ No content available.")
            return
        
        social_links = session.current_directory.get('social_links', {})
        onlyfans_link = social_links.get('onlyfans')
        
        if not onlyfans_link:
            await query.answer("OnlyFans link not available", show_alert=True)
            return
        
        await query.edit_message_text(
            f"📱 **OnlyFans Feed**\n\n"
            f"OnlyFans integration coming soon!\n\n"
            f"Link: {onlyfans_link}",
            parse_mode='Markdown'
        )
    
    # ==================== ERROR HANDLER ====================
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        error_message = "❌ An unexpected error occurred. Please try again later."
        
        try:
            if isinstance(context.error, TimedOut):
                error_message = "⏱️ Request timed out. Please try again."
            elif isinstance(context.error, NetworkError):
                error_message = "🌐 Network error. Please check your connection."
            
            if update and hasattr(update, 'effective_message') and update.effective_message:
                await update.effective_message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Error in error handler: {e}")


def main():
    """Start the coordinator bot."""
    try:
        TOKEN = config('TELEGRAM_BOT_TOKEN')
    except:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file")
        return
    
    print("💾 Initializing cache manager...")
    cache_manager = get_cache_manager()
    print("✅ Cache ready")
    
    print("🤖 Initializing Coordinator Bot...")
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    # Initialize coordinator bot
    bot = CoordinatorBot()
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("cancel", bot.cancel_command))
    
    # Main admin setup commands
    application.add_handler(CommandHandler("setupmainadmin", bot.setupmainadmin_command))
    application.add_handler(CommandHandler("removemainadmin", bot.removemainadmin_command))
    application.add_handler(CommandHandler("confirmmainadminremoval", bot.confirmmainadminremoval_command))
    
    # Admin commands
    application.add_handler(CommandHandler("requests", bot.admin_requests_command))
    application.add_handler(CommandHandler("adminstats", bot.admin_stats_command))
    application.add_handler(CommandHandler("addadmin", bot.addadmin_command))
    application.add_handler(CommandHandler("removeadmin", bot.removeadmin_command))
    application.add_handler(CommandHandler("addworker", bot.addworker_command))
    application.add_handler(CommandHandler("removeworker", bot.removeworker_command))
    application.add_handler(CommandHandler("listadmins", bot.listadmins_command))
    application.add_handler(CommandHandler("listworkers", bot.listworkers_command))
    application.add_handler(CommandHandler("cache", bot.cache_stats_command))
    application.add_handler(CommandHandler("titles", bot.titles_command))
    application.add_handler(CommandHandler("approve", bot.approve_title_command))
    application.add_handler(CommandHandler("reject", bot.reject_title_command))
    application.add_handler(CommandHandler("bulkapprove", bot.bulkapprove_command))
    application.add_handler(CommandHandler("bulkreject", bot.bulkreject_command))
    application.add_handler(CommandHandler("deletions", bot.deletions_command))
    application.add_handler(CommandHandler("approvedelete", bot.approvedelete_command))
    application.add_handler(CommandHandler("rejectdelete", bot.rejectdelete_command))
    
    # Worker commands
    application.add_handler(CommandHandler("mystats", bot.worker_stats_command))
    application.add_handler(CommandHandler("workerhelp", bot.workerhelp_command))
    
    # Callback and message handlers
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_error_handler(bot.error_handler)
    
    print("✅ Coordinator Bot ready (distributed mode)!")
    print(f"✅ Connected to Redis for task distribution")
    print("🚀 Starting bot polling...\n")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n⏹️  Stopping bot...")
        print("👋 Bot shutdown complete")


if __name__ == '__main__':
    main()
