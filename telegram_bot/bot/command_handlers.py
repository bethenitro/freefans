"""
Command Handlers - Handles bot commands like /start, /help
"""

import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError
from bot.utilities import send_message_with_retry
from bot.ui_components import create_welcome_keyboard
from core.user_session import UserSession

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

💋 Use the menu buttons below to get started!
"""

HELP_TEXT = """
📖 FreeFans Bot Help 📖

🔍 Search Creator
Type any creator's name and I'll find their hottest content. The search is smart - even partial names work!

🎲 Random Creator
Get a random creator with lots of content (25+ items). Perfect for discovering new creators!

📝 Request Creator
Don't see a creator? Request them to be added! I'll need:
  • Social media platform (OnlyFans, Instagram, etc.)
  • Creator's username
  
🎯 Request Content  
Looking for specific content from a creator? Let me know:
  • Creator's social media & username
  • Exact details of what you're looking for
  
📁 What You Get Access To

🖼️ Photos - High-res galleries, full albums
🎬 Videos - Stream or download premium clips  
📱 OnlyFans Archives - Complete feed history
💎 Exclusive Content - Hard to find anywhere else

⚡ Quick Commands

/start - Get started with the bot
/help - Show this guide again
/cancel - Cancel current operation

Ready to explore? Use the menu buttons below! 😈
"""


def create_main_menu_keyboard():
    """Create the main menu reply keyboard"""
    keyboard = [
        [KeyboardButton("🔍 Search Creator")],
        [KeyboardButton("🎲 Random Creator")],
        [KeyboardButton("📝 Request Creator"), KeyboardButton("🎯 Request Content")],
        [KeyboardButton("❓ Help")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    reply_markup = create_main_menu_keyboard()
    
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
    from managers.permissions_manager import get_permissions_manager
    
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    help_text = HELP_TEXT
    
    # Add main admin commands if user is main admin
    if permissions.is_main_admin(user_id):
        help_text += "\n\n👑 **Main Admin Commands:**\n\n"
        help_text += "**Main Admin Management:**\n"
        help_text += "• /removemainadmin - Remove yourself as main admin\n\n"
        help_text += "**Sub-Admin Management:**\n"
        help_text += "• /addadmin <user_id> - Add a sub-admin\n"
        help_text += "• /removeadmin <user_id> - Remove a sub-admin\n"
        help_text += "• /listadmins - List all admins\n\n"
        help_text += "**Worker Management:**\n"
        help_text += "• /addworker <user_id> - Add a worker\n"
        help_text += "• /removeworker <user_id> - Remove a worker\n"
        help_text += "• /listworkers - List all workers\n\n"
        help_text += "**Content Management:**\n"
        help_text += "• /requests - View pending user requests\n"
        help_text += "• /titles - View pending title submissions\n"
        help_text += "• /approve <id> - Approve a title\n"
        help_text += "• /reject <id> - Reject a title\n"
        help_text += "• /bulkapprove <worker_id> - Bulk approve worker\n"
        help_text += "• /bulkreject <worker_id> - Bulk reject worker\n"
        help_text += "• /deletions - View pending deletion requests\n"
        help_text += "• /approvedelete <id> - Approve video deletion\n"
        help_text += "• /rejectdelete <id> - Reject video deletion\n"
        help_text += "• /adminstats - View system statistics\n\n"
        help_text += "**Community Pools:**\n"
        help_text += "• /createpool - Create a new community pool\n"
        help_text += "• /poolstats - View pool system statistics\n"
        help_text += "• /completepool - Mark a pool as completed\n"
        help_text += "• /cancelpool - Cancel a pool and refund contributors\n"
        help_text += "• /poolrequests - View pending requests for pool creation\n\n"
        help_text += "**Channel Management:**\n"
        help_text += "• /addrequiredchannel <id> <name> - Add required channel\n"
        help_text += "• /removerequiredchannel <id> - Remove required channel\n"
        help_text += "• /listrequiredchannels - List all required channels\n"
        help_text += "• /channelsettings - Configure channel settings\n"
        help_text += "• /setwelcomemessage <text> - Set welcome message\n"
        help_text += "• /setmembershipmessage <text> - Set membership message\n"
        help_text += "\n**Permission Hierarchy:**\n"
        help_text += "• Main Admin → Can manage sub-admins and workers\n"
        help_text += "• Sub-Admins → Can manage workers only\n"
        help_text += "• Workers → Can submit title suggestions\n"
    # Add sub-admin commands if user is admin (but not main admin)
    elif permissions.is_admin(user_id):
        help_text += "\n\n🔧 **Sub-Admin Commands:**\n\n"
        help_text += "**Worker Management:**\n"
        help_text += "• /addworker <user_id> - Add a worker\n"
        help_text += "• /removeworker <user_id> - Remove a worker\n"
        help_text += "• /listworkers - List all workers\n\n"
        help_text += "**Content Management:**\n"
        help_text += "• /requests - View pending user requests\n"
        help_text += "• /titles - View pending title submissions\n"
        help_text += "• /approve <id> - Approve a title\n"
        help_text += "• /reject <id> - Reject a title\n"
        help_text += "• /bulkapprove <worker_id> - Bulk approve worker\n"
        help_text += "• /bulkreject <worker_id> - Bulk reject worker\n"
        help_text += "• /deletions - View pending deletion requests\n"
        help_text += "• /approvedelete <id> - Approve video deletion\n"
        help_text += "• /rejectdelete <id> - Reject video deletion\n"
        help_text += "• /adminstats - View system statistics\n\n"
        help_text += "**Community Pools:**\n"
        help_text += "• /createpool - Create a new community pool\n"
        help_text += "• /poolstats - View pool system statistics\n"
        help_text += "• /completepool - Mark a pool as completed\n"
        help_text += "• /cancelpool - Cancel a pool and refund contributors\n"
        help_text += "• /poolrequests - View pending requests for pool creation\n\n"
        help_text += "**Channel Management:**\n"
        help_text += "• /addrequiredchannel <id> <name> - Add required channel\n"
        help_text += "• /removerequiredchannel <id> - Remove required channel\n"
        help_text += "• /listrequiredchannels - List all required channels\n"
        help_text += "• /channelsettings - Configure channel settings\n"
        help_text += "• /setwelcomemessage <text> - Set welcome message\n"
        help_text += "• /setmembershipmessage <text> - Set membership message\n"
    
    # Add worker commands if user is worker
    if permissions.is_worker(user_id):
        help_text += "\n\n👷 **Worker Commands:**\n\n"
        help_text += "• Reply to videos with titles to submit\n"
        help_text += "• Reply with 'NOT FOUND' to remove broken videos\n"
        help_text += "• /mystats - View your submission stats\n"
        help_text += "• /workerhelp - Worker guide\n"
    
    reply_markup = create_main_menu_keyboard()
    try:
        await send_message_with_retry(
            update.message.reply_text, 
            help_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send help message: {e}")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Cancel any ongoing operation"""
    user_id = update.effective_user.id
    
    if user_id in bot_instance.user_sessions:
        session = bot_instance.user_sessions[user_id]
        # Clear any pending states
        session.pending_creator_options = None
        session.pending_creator_name = None
        session.awaiting_request = None
        session.request_data = {}
        session.awaiting_admin_setup_password = False
        session.awaiting_admin_removal_confirmation = False
    
    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text(
        "❌ Operation cancelled. Use the menu buttons to start again.",
        reply_markup=reply_markup
    )
