"""
Search Handler - Handles creator search functionality
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest
from bot.utilities import send_message_with_retry
from bot.ui_components import format_directory_text, create_content_keyboard

logger = logging.getLogger(__name__)


async def handle_creator_search(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Handle creator name input and search for content."""
    user_id = update.effective_user.id
    creator_name = update.message.text.strip()
    
    if user_id not in bot_instance.user_sessions:
        from user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    session = bot_instance.user_sessions[user_id]
    
    # Show typing indicator
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except (TimedOut, NetworkError):
        pass  # Non-critical, continue anyway
    
    # Search for creator content
    try:
        search_message = await send_message_with_retry(
            update.message.reply_text,
            f"🔍 Searching for content from '{creator_name}'...\n"
            "This may take a few moments."
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send search message: {e}")
        return
    
    try:
        # Get content directory
        content_directory = await bot_instance.content_manager.search_creator_content(creator_name, session.filters)
        
        if not content_directory:
            try:
                await send_message_with_retry(
                    search_message.edit_text,
                    f"❌ No content found for '{creator_name}'.\n\n"
                    "Try checking the spelling or searching for a different creator."
                )
            except (TimedOut, NetworkError):
                pass
            return
        
        # Check if confirmation is needed
        if content_directory.get('needs_confirmation', False):
            matched_name = content_directory['creator']
            social_links = content_directory.get('social_links', {})
            
            # Build the confirmation text
            confirm_text = f"🔍 Did you mean: **{matched_name}**?\n\n"
            
            # Add OnlyFans link if available
            if social_links.get('onlyfans'):
                confirm_text += f"🔗 OnlyFans: {social_links['onlyfans']}\n"
            
            # Add Instagram link if available
            if social_links.get('instagram'):
                confirm_text += f"📸 Instagram: {social_links['instagram']}\n"
            
            confirm_text += "\nPlease confirm if this is the creator you're looking for."
            
            keyboard = [
                [InlineKeyboardButton("✅ Yes, Continue", callback_data=f"confirm_search|{matched_name}")],
                [InlineKeyboardButton("❌ No, Try Again", callback_data="search_creator")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store content for later use
            session.pending_content = content_directory
            
            try:
                await send_message_with_retry(
                    search_message.edit_text,
                    confirm_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except (TimedOut, NetworkError):
                pass
        else:
            # Display content directory immediately
            await display_content_directory(update, bot_instance, content_directory, content_directory['creator'])
            try:
                await search_message.delete()
            except (TimedOut, NetworkError, BadRequest):
                pass  # Non-critical if deletion fails
        
    except Exception as e:
        logger.error(f"Error searching for creator {creator_name}: {e}")
        try:
            await send_message_with_retry(
                search_message.edit_text,
                "❌ An error occurred while searching. Please try again later."
            )
        except (TimedOut, NetworkError):
            pass


async def display_content_directory(update: Update, bot_instance, content_directory: dict, creator_name: str) -> None:
    """Display the content directory with navigation."""
    user_id = update.effective_user.id
    session = bot_instance.user_sessions[user_id]
    session.current_directory = content_directory
    session.current_creator = creator_name
    
    # Create directory display
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    # Add Pictures button if there are preview images
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    # Add Videos button if there are video links
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await send_message_with_retry(
            update.message.reply_text,
            directory_text,
            reply_markup=reply_markup
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to display content directory: {e}")
