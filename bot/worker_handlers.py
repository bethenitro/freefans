"""
Worker Handlers - Worker commands for submitting video titles
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from permissions_manager import get_permissions_manager
from title_manager import get_title_manager
from user_session import UserSession

logger = logging.getLogger(__name__)


async def handle_worker_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle worker replies to video messages with title suggestions.
    
    Returns:
        True if handled as worker reply, False otherwise
    """
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Check if user is a worker
    if not permissions.is_worker(user_id):
        return False
    
    # Check if replying to a message
    if not update.message.reply_to_message:
        return False
    
    # Check if the replied message contains a video URL
    replied_message = update.message.reply_to_message
    video_url = None
    creator_name = None
    
    # Try to extract video URL from the replied message
    if replied_message.text:
        # Look for common video domains in the message
        text = replied_message.text
        
        # Try to find URLs in text
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        
        # Look for video URLs (checking common video domains)
        video_domains = [
            'bunkr', 'gofile', 'pixeldrain', 'streamtape', 'streamlare',
            'doodstream', 'mixdrop', 'sendvid', 'filejoker', 'anonfiles',
            'cyberdrop', 'mediafire', 'mega.nz', 'dropbox', 'drive.google'
        ]
        
        for url in urls:
            if any(domain in url.lower() for domain in video_domains):
                video_url = url
                break
        
        # Try to extract creator name from the message
        # Look for patterns like "Creator: Name" or just the creator name
        if "Creator:" in text or "creator:" in text:
            lines = text.split('\n')
            for line in lines:
                if 'creator:' in line.lower():
                    creator_name = line.split(':', 1)[1].strip()
                    break
        
        # Alternative: look for name in first line or before URL
        if not creator_name and urls:
            parts = text.split(urls[0])[0].strip().split('\n')
            if parts:
                creator_name = parts[0].strip()
    
    if not video_url:
        # Not a video message, ignore
        return False
    
    # Get the suggested title from the reply
    suggested_title = update.message.text.strip()
    
    if not suggested_title or len(suggested_title) < 3:
        await update.message.reply_text(
            "❌ Title too short. Please provide a descriptive title (at least 3 characters)."
        )
        return True
    
    if len(suggested_title) > 200:
        await update.message.reply_text(
            "❌ Title too long. Please keep it under 200 characters."
        )
        return True
    
    # Submit the title
    title_manager = get_title_manager()
    username = update.effective_user.username or update.effective_user.first_name
    
    submission_id = title_manager.submit_title(
        worker_id=user_id,
        worker_username=username,
        video_url=video_url,
        creator_name=creator_name or 'Unknown',
        title=suggested_title
    )
    
    await update.message.reply_text(
        f"✅ **Title Submitted!**\n\n"
        f"🆔 Submission ID: `{submission_id}`\n"
        f"🎬 Title: {suggested_title}\n"
        f"👤 Creator: {creator_name or 'Unknown'}\n\n"
        f"⏳ Your submission will be reviewed by an admin.\n"
        f"Use /mystats to check your submission status.",
        parse_mode='Markdown'
    )
    
    logger.info(f"Worker {user_id} submitted title: {submission_id}")
    return True


async def worker_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # Get pending submissions
    pending = title_manager.get_pending_titles(worker_id=user_id)
    
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
    
    if pending:
        message += f"\n⏳ **Recent Pending ({min(5, len(pending))}):**\n"
        for submission in pending[:5]:
            message += f"\n• {submission['submission_id']}\n"
            message += f"  Title: {submission['suggested_title'][:50]}...\n"
            message += f"  Creator: {submission['creator_name']}\n"
    
    message += "\n💡 **How to submit:**\n"
    message += "Reply to any video message with your suggested title."
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def worker_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show worker help information."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_worker(user_id):
        await update.message.reply_text(
            "❌ You are not registered as a worker."
        )
        return
    
    message = """
📘 **Worker Guide**

Welcome, worker! Your job is to help improve video titles in our content library.

**How to Submit Titles:**

1️⃣ Find a video in the content library
2️⃣ Reply to the video message
3️⃣ Type your suggested title in the reply
4️⃣ Wait for admin approval

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

**Commands:**
• /mystats - View your submission statistics
• /workerhelp - Show this help message

💡 Tip: The more titles you submit that get approved, the higher your approval rate!
"""
    
    await update.message.reply_text(message, parse_mode='Markdown')
