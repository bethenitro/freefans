"""
Worker Handlers - Worker commands for submitting video titles
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from managers.permissions_manager import get_permissions_manager
from managers.title_manager import get_title_manager
from core.user_session import UserSession

logger = logging.getLogger(__name__)


async def handle_worker_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance=None) -> bool:
    """
    Handle worker replies to video messages with title suggestions.
    
    Returns:
        True if handled as worker reply, False otherwise
    """
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    # Check if user is a worker
    if not permissions.is_worker(user_id):
        logger.debug(f"User {user_id} is not a worker, skipping worker reply handler")
        return False
    
    logger.info(f"Worker {user_id} sent a message, checking if it's a reply to video")
    
    # Initialize session if needed
    if bot_instance and hasattr(bot_instance, 'user_sessions'):
        if user_id not in bot_instance.user_sessions:
            bot_instance.user_sessions[user_id] = UserSession(user_id)
            # Clear any awaiting_request state for workers
            bot_instance.user_sessions[user_id].awaiting_request = None
            logger.info(f"Created session for worker {user_id}")
    
    # Check if replying to a message
    if not update.message.reply_to_message:
        logger.info(f"Worker {user_id} message is not a reply, skipping")
        return False
    
    logger.info(f"Worker {user_id} is replying to a message, extracting video URL")
    
    # Check if the replied message contains a video URL
    replied_message = update.message.reply_to_message
    video_url = None
    creator_name = None
    video_title = None
    
    # Try to extract video URL from the replied message
    if replied_message.text:
        text = replied_message.text
        
        # First check if message has entities (links from markdown)
        if replied_message.entities:
            for entity in replied_message.entities:
                if entity.type == 'text_link':
                    url = entity.url
                    # Check if this is the Original Link (should be second link for workers)
                    if 'bunkr' in url or 'gofile' in url or 'pixeldrain' in url or 'streamtape' in url or \
                       'streamlare' in url or 'doodstream' in url or 'mixdrop' in url or 'sendvid' in url or \
                       'filejoker' in url or 'anonfiles' in url or 'cyberdrop' in url or 'mediafire' in url or \
                       'mega.nz' in url or 'dropbox' in url or 'drive.google' in url or 'coomer.su' in url:
                        video_url = url
                        logger.info(f"Extracted video URL from markdown entity: {url[:50]}...")
                        break
        
        # Extract title from message (first line after 🎬)
        if '🎬' in text:
            lines = text.strip().split('\n')
            for line in lines:
                if '🎬' in line:
                    video_title = line.replace('🎬', '').strip()
                    break
        
        # Try to find URLs in text as fallback
        if not video_url:
            import re
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            urls = re.findall(url_pattern, text)
        
            # Check if this is a video library message (with landing URL or direct video URL)
            # Format: 🎬 {title}\n\n🔗 Access Link: {landing_url}\n📎 Original: {original_url}
            if '🎬' in text and urls:
                # Extract title (first line after 🎬)
                lines = text.strip().split('\n')
                for line in lines:
                    if '🎬' in line:
                        video_title = line.replace('🎬', '').strip()
                        break
                
                # Extract original URL if present (preferred for cache updates)
                original_url = None
                for line in lines:
                    if '📎 Original:' in line or '📎Original:' in line:
                        # Get URL after "Original:"
                        url_match = re.search(r'Original:\s*(https?://[^\s<>"{}|\\^`\[\]]+)', line)
                        if url_match:
                            original_url = url_match.group(1)
                            break
                
                # Use original URL if found, otherwise use landing URL
                video_url = original_url if original_url else urls[0]
                
                logger.info(f"Extracted URLs - Landing: {urls[0][:50]}..., Original: {original_url[:50] if original_url else 'None'}...")
                
                # Try to get creator from session
                if bot_instance and user_id in bot_instance.user_sessions:
                    session = bot_instance.user_sessions[user_id]
                    # Check session.current_creator first
                    if hasattr(session, 'current_creator') and session.current_creator:
                        creator_name = session.current_creator
                        logger.info(f"Got creator from session.current_creator: {creator_name}")
                    # Fallback to current_directory if available
                    elif session.current_directory:
                        creator_name = session.current_directory.get('creator_name')
                        logger.info(f"Got creator from session.current_directory: {creator_name}")
                
                # If still no creator name, mark as Unknown
                if not creator_name:
                    creator_name = 'Unknown'
                    logger.warning(f"Could not determine creator name from session")
            
            else:
                # Look for direct video URLs with common domains
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
                if "Creator:" in text or "creator:" in text:
                    lines = text.split('\n')
                    for line in lines:
                        if 'creator:' in line.lower():
                            creator_name = line.split(':', 1)[1].strip()
                            break
                
                # Alternative: look for name in first line
                if not creator_name and urls:
                    parts = text.split(urls[0])[0].strip().split('\n')
                    if parts:
                        creator_name = parts[0].strip()
    
    if not video_url:
        # Not a video message, ignore
        logger.info(f"Worker {user_id} replied to a message but no video URL found, skipping")
        logger.debug(f"Message text: {replied_message.text[:100] if replied_message.text else 'No text'}")
        return False
    
    logger.info(f"Worker {user_id} replying to video: {video_url[:80]}...")
    logger.info(f"Existing title: {video_title}, Creator: {creator_name}")
    
    # Get the suggested title from the reply
    suggested_title = update.message.text.strip()
    
    # Check if worker is reporting video as NOT FOUND
    if suggested_title.upper() == 'NOT FOUND':
        from managers.cache_factory import get_cache_manager
        cache_manager = get_cache_manager()
        
        # Delete the video from database
        success = cache_manager.delete_video(video_url)
        
        if success:
            await update.message.reply_text(
                f"✅ **Video Removal Confirmed!**\n\n"
                f"🗑️ The video has been successfully removed from the database.\n"
                f"🔗 URL: {video_url[:50]}...\n\n"
                f"Thank you for keeping the database clean! 🧹",
                parse_mode='Markdown'
            )
            logger.info(f"Worker {user_id} marked video as NOT FOUND and deleted: {video_url[:80]}...")
        else:
            await update.message.reply_text(
                f"⚠️ **Video Not Found in Database**\n\n"
                f"The video may have already been removed or wasn't in the database.\n"
                f"🔗 URL: {video_url[:50]}...",
                parse_mode='Markdown'
            )
            logger.warning(f"Worker {user_id} tried to delete video but it wasn't found: {video_url[:80]}...")
        
        return True
    
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
        f"✅ **Title Submission Confirmed!**\n\n"
        f"🆔 Submission ID: `{submission_id}`\n"
        f"🎬 Suggested Title: {suggested_title}\n"
        f"👤 Creator: {creator_name or 'Unknown'}\n"
        f"🔗 Video: {video_url[:50]}...\n\n"
        f"⏳ Your submission is now pending admin review.\n"
        f"📊 Use /mystats to track your submission status.",
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
