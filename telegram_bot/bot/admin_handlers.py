"""
Admin Handlers - Admin commands for managing requests and permissions
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from managers.permissions_manager import get_permissions_manager
from managers.request_manager import get_request_manager
from managers.title_manager import get_title_manager
from managers.cache_factory import get_cache_manager

logger = logging.getLogger(__name__)


async def admin_requests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all pending requests (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    request_manager = get_request_manager()
    
    # Get pending creator requests
    creator_requests = request_manager.get_pending_creator_requests()
    content_requests = request_manager.get_pending_content_requests()
    
    if not creator_requests and not content_requests:
        await update.message.reply_text("📭 No pending requests at the moment.")
        return
    
    message = "📋 **Pending Requests**\n\n"
    
    if creator_requests:
        message += f"🎭 **Creator Requests ({len(creator_requests)}):**\n\n"
        for req in creator_requests[:10]:  # Show first 10
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
        for req in content_requests[:10]:  # Show first 10
            message += f"🆔 {req['request_id']}\n"
            message += f"👤 User: {req['user_id']}\n"
            message += f"📱 Platform: {req['platform']}\n"
            message += f"👥 Username: {req['username']}\n"
            message += f"📝 Details: {req['content_details'][:50]}...\n"
            message += f"📅 {req['timestamp'][:10]}\n"
            message += "─" * 30 + "\n"
        
        if len(content_requests) > 10:
            message += f"\n... and {len(content_requests) - 10} more\n"
    
    # Send in chunks if too long
    if len(message) > 4000:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, parse_mode='Markdown')


async def admin_titles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    for submission in pending[:15]:  # Show first 15
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
    
    # Send in chunks if too long
    if len(message) > 4000:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, parse_mode='Markdown')


async def approve_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a title submission (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/approve <submission_id>`\n\n"
            "Example: `/approve TS-20251223120000-123456789`",
            parse_mode='Markdown'
        )
        return
    
    submission_id = context.args[0]
    title_manager = get_title_manager()
    cache_manager = get_cache_manager()
    
    # Approve the title
    submission = title_manager.approve_title(submission_id, user_id)
    
    if not submission:
        await update.message.reply_text(f"❌ Submission `{submission_id}` not found.", parse_mode='Markdown')
        return
    
    # Update the cache
    video_url = submission['video_url']
    new_title = submission['suggested_title']
    
    updated = cache_manager.update_video_title(video_url, new_title)
    
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
    logger.info(f"Admin {user_id} approved title {submission_id}")


async def reject_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject a title submission (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/reject <submission_id>`\n\n"
            "Example: `/reject TS-20251223120000-123456789`",
            parse_mode='Markdown'
        )
        return
    
    submission_id = context.args[0]
    reason = 'Rejected by admin'
    
    title_manager = get_title_manager()
    
    # Reject the title
    submission = title_manager.reject_title(submission_id, user_id, reason)
    
    if not submission:
        await update.message.reply_text(f"❌ Submission `{submission_id}` not found.", parse_mode='Markdown')
        return
    
    message = f"❌ **Title Rejected**\n\n"
    message += f"🆔 {submission_id}\n"
    message += f"👷 Worker: {submission['worker_username']}\n"
    message += f"👤 Creator: {submission['creator_name']}\n"
    message += f"🎬 Title: {submission['suggested_title']}\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"Admin {user_id} rejected title {submission_id}")


async def bulk_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk reject all titles from a worker (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/bulkreject <worker_id>`\n\n"
            "Example: `/bulkreject 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        worker_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid worker ID. Must be a number.")
        return
    
    title_manager = get_title_manager()
    
    # Get pending titles for this worker
    pending = title_manager.get_pending_titles(worker_id=worker_id)
    
    if not pending:
        await update.message.reply_text(f"📭 No pending titles from worker {worker_id}.")
        return
    
    await update.message.reply_text(f"⏳ Rejecting {len(pending)} titles from worker {worker_id}...")
    
    # Bulk reject
    rejected = title_manager.bulk_reject_worker(worker_id, user_id, reason='Bulk rejected by admin')
    
    message = f"❌ **Bulk Rejection Complete!**\n\n"
    message += f"👷 Worker ID: {worker_id}\n"
    message += f"✗ Rejected: {len(rejected)} titles\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"Admin {user_id} bulk rejected {len(rejected)} titles from worker {worker_id}")


async def bulk_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk approve all titles from a worker (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/bulkapprove <worker_id>`\n\n"
            "Example: `/bulkapprove 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        worker_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid worker ID. Must be a number.")
        return
    
    title_manager = get_title_manager()
    cache_manager = get_cache_manager()
    
    # Get pending titles for this worker
    pending = title_manager.get_pending_titles(worker_id=worker_id)
    
    if not pending:
        await update.message.reply_text(f"📭 No pending titles from worker {worker_id}.")
        return
    
    await update.message.reply_text(f"⏳ Approving {len(pending)} titles from worker {worker_id}...")
    
    # Bulk approve
    approved = title_manager.bulk_approve_worker(worker_id, user_id)
    
    # Update cache for each approved title
    updated_count = 0
    for submission in approved:
        if cache_manager.update_video_title(submission['video_url'], submission['suggested_title']):
            updated_count += 1
    
    message = f"✅ **Bulk Approval Complete!**\n\n"
    message += f"👷 Worker ID: {worker_id}\n"
    message += f"✓ Approved: {len(approved)} titles\n"
    message += f"💾 Cache updated: {updated_count} videos\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"Admin {user_id} bulk approved {len(approved)} titles from worker {worker_id}")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View system statistics (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    request_manager = get_request_manager()
    title_manager = get_title_manager()
    
    # Get request stats
    req_stats = request_manager.get_request_stats()
    
    # Get title stats for all workers
    workers = permissions.get_workers()
    total_pending = len(title_manager.get_pending_titles())
    
    message = "📊 **System Statistics**\n\n"
    
    message += "📋 **User Requests:**\n"
    message += f"• Creator requests: {req_stats['total_creator_requests']}\n"
    message += f"• Content requests: {req_stats['total_content_requests']}\n"
    message += f"• Pending creator: {req_stats['pending_creator_requests']}\n"
    message += f"• Pending content: {req_stats['pending_content_requests']}\n\n"
    
    message += f"📝 **Title Submissions:**\n"
    message += f"• Pending: {total_pending}\n\n"
    
    message += f"👥 **Users:**\n"
    message += f"• Admins: {len(permissions.get_admins())}\n"
    message += f"• Workers: {len(workers)}\n"
    
    if workers:
        message += "\n👷 **Worker Stats:**\n"
        for worker_id in workers[:5]:  # Show first 5
            stats = title_manager.get_worker_stats(worker_id)
            message += f"\n• Worker {worker_id}:\n"
            message += f"  Pending: {stats['pending']} | "
            message += f"Approved: {stats['approved']} | "
            message += f"Rejected: {stats['rejected']}\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def setupmainadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance):
    """Setup the main admin - first time only, password protected."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Check if main admin already exists
    if permissions.has_main_admin():
        await update.message.reply_text(
            "❌ Main admin already configured. Only the current main admin can remove themselves."
        )
        return
    
    # Initialize user session if needed
    if user_id not in bot_instance.user_sessions:
        from core.user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    # Set flag to await password
    session = bot_instance.user_sessions[user_id]
    session.awaiting_admin_setup_password = True
    
    await update.message.reply_text(
        "🔐 To become the main admin, please enter the setup password:\n\n"
        "⚠️ Warning: Send the password as a regular message (not a command)."
    )
    logger.info(f"User {user_id} initiated main admin setup")


async def removemainadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance):
    """Remove yourself as main admin - confirmation required."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Check if user is the current main admin
    if not permissions.is_main_admin(user_id):
        await update.message.reply_text(
            "❌ Only the main admin can remove themselves."
        )
        return
    
    # Initialize user session if needed
    if user_id not in bot_instance.user_sessions:
        from core.user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    # Set flag to await confirmation
    session = bot_instance.user_sessions[user_id]
    session.awaiting_admin_removal_confirmation = True
    
    await update.message.reply_text(
        "⚠️ **Are you sure you want to remove yourself as main admin?**\n\n"
        "This will allow someone else to become main admin using /setupmainadmin\n\n"
        "Send `/confirmmainadminremoval` to confirm, or /cancel to abort.",
        parse_mode='Markdown'
    )
    logger.info(f"Main admin {user_id} requested removal confirmation")


async def confirmmainadminremoval_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance):
    """Confirm removal of main admin status."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Initialize user session if needed
    if user_id not in bot_instance.user_sessions:
        await update.message.reply_text(
            "❌ No removal request in progress. Use /removemainadmin first."
        )
        return
    
    session = bot_instance.user_sessions[user_id]
    
    # Check if confirmation was requested
    if not session.awaiting_admin_removal_confirmation:
        await update.message.reply_text(
            "❌ No removal request in progress. Use /removemainadmin first."
        )
        return
    
    # Check if user is still the main admin
    if not permissions.is_main_admin(user_id):
        session.awaiting_admin_removal_confirmation = False
        await update.message.reply_text(
            "❌ You are not the main admin."
        )
        return
    
    # Remove main admin
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


async def handle_admin_setup_password(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> bool:
    """
    Handle password verification for main admin setup.
    Returns True if message was handled, False otherwise.
    """
    from decouple import config
    
    user_id = update.effective_user.id
    
    # Check if user has an active session awaiting password
    if user_id not in bot_instance.user_sessions:
        return False
    
    session = bot_instance.user_sessions[user_id]
    
    if not session.awaiting_admin_setup_password:
        return False
    
    # Clear the flag immediately
    session.awaiting_admin_setup_password = False
    
    # Get the password from message
    provided_password = update.message.text.strip()
    
    # Get correct password from .env
    try:
        correct_password = config('ADMIN_SETUP_PASSWORD')
    except Exception as e:
        logger.error(f"Failed to get ADMIN_SETUP_PASSWORD from .env: {e}")
        await update.message.reply_text(
            "❌ Server configuration error. Please contact the developer."
        )
        return True
    
    # Verify password
    if provided_password == correct_password:
        permissions = get_permissions_manager()
        success = permissions.set_main_admin(user_id)
        
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
            logger.info(f"User {user_id} successfully became main admin")
        else:
            await update.message.reply_text(
                "❌ Setup failed. Main admin may have been set by someone else."
            )
            logger.error(f"Failed to set user {user_id} as main admin")
    else:
        await update.message.reply_text(
            "❌ Incorrect password. Setup cancelled.\n\n"
            "If you need to try again, use /setupmainadmin"
        )
        logger.warning(f"User {user_id} provided incorrect admin setup password")
    
    return True


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a sub-admin (main admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Only main admin can add sub-admins
    if not permissions.is_main_admin(user_id):
        await update.message.reply_text(
            "❌ Only the main admin can add sub-admins."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/addadmin <user_id>`\n\n"
            "Example: `/addadmin 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        return
    
    # Cannot add main admin as sub-admin
    if permissions.is_main_admin(target_user_id):
        await update.message.reply_text("❌ This user is the main admin.")
        return
    
    success = permissions.add_admin(target_user_id)
    
    if success:
        await update.message.reply_text(
            f"✅ User `{target_user_id}` has been added as a sub-admin.\n\n"
            f"They can now manage workers and use admin commands.",
            parse_mode='Markdown'
        )
        logger.info(f"Main admin {user_id} added sub-admin {target_user_id}")
    else:
        await update.message.reply_text(
            f"⚠️ User `{target_user_id}` is already a sub-admin.",
            parse_mode='Markdown'
        )


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a sub-admin (main admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Only main admin can remove sub-admins
    if not permissions.is_main_admin(user_id):
        await update.message.reply_text(
            "❌ Only the main admin can remove sub-admins."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/removeadmin <user_id>`\n\n"
            "Example: `/removeadmin 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        return
    
    # Cannot remove main admin this way
    if permissions.is_main_admin(target_user_id):
        await update.message.reply_text(
            "❌ Cannot remove main admin this way. Main admin must use /removemainadmin"
        )
        return
    
    success = permissions.remove_admin(target_user_id)
    
    if success:
        await update.message.reply_text(
            f"✅ User `{target_user_id}` has been removed as a sub-admin.",
            parse_mode='Markdown'
        )
        logger.info(f"Main admin {user_id} removed sub-admin {target_user_id}")
    else:
        await update.message.reply_text(
            f"⚠️ User `{target_user_id}` is not a sub-admin.",
            parse_mode='Markdown'
        )


async def addworker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a worker (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Any admin can add workers
    if not permissions.is_admin(user_id):
        await update.message.reply_text(
            "❌ Only admins can add workers."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/addworker <user_id>`\n\n"
            "Example: `/addworker 123456789`",
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
            f"✅ User `{target_user_id}` has been added as a worker.\n\n"
            f"They can now submit title suggestions.",
            parse_mode='Markdown'
        )
        logger.info(f"Admin {user_id} added worker {target_user_id}")
    else:
        await update.message.reply_text(
            f"⚠️ User `{target_user_id}` is already a worker.",
            parse_mode='Markdown'
        )


async def removeworker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a worker (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Any admin can remove workers
    if not permissions.is_admin(user_id):
        await update.message.reply_text(
            "❌ Only admins can remove workers."
        )
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: `/removeworker <user_id>`\n\n"
            "Example: `/removeworker 123456789`",
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
        logger.info(f"Admin {user_id} removed worker {target_user_id}")
    else:
        await update.message.reply_text(
            f"⚠️ User `{target_user_id}` is not a worker.",
            parse_mode='Markdown'
        )


async def listadmins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text(
            "❌ Only admins can view the admin list."
        )
        return
    
    main_admin = permissions.get_main_admin()
    admins = permissions.get_admins()
    
    message = "👑 **Admin List**\n\n"
    
    if main_admin:
        message += f"**Main Admin:** `{main_admin}`\n\n"
    else:
        message += "**Main Admin:** None (use /setupmainadmin)\n\n"
    
    if admins:
        message += f"**Sub-Admins ({len(admins)}):**\n"
        for admin_id in admins:
            if admin_id != main_admin:  # Don't list main admin twice
                message += f"• `{admin_id}`\n"
    else:
        message += "**Sub-Admins:** None\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def listworkers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all workers (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text(
            "❌ Only admins can view the worker list."
        )
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
