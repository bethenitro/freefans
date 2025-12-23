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
