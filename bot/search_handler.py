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
    
    # Search for creator options first
    try:
        search_message = await send_message_with_retry(
            update.message.reply_text,
            f"🔍 Searching for '{creator_name}'...\n"
            "This may take a few moments."
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send search message: {e}")
        return
    
    try:
        # Check if we need to show multiple options or proceed directly
        search_options = await bot_instance.content_manager.search_creator_options(creator_name)
        
        if not search_options:
            try:
                await send_message_with_retry(
                    search_message.edit_text,
                    f"❌ No content found for '{creator_name}'.\n\n"
                    "Try checking the spelling or searching for a different creator."
                )
            except (TimedOut, NetworkError):
                pass
            return
        
        # Show options for user to choose
        if search_options.get('needs_selection'):
            options = search_options['options']
            
            # Store all options in session for pagination
            session.pending_creator_options = options
            session.pending_creator_name = creator_name
            session.creator_selection_page = 0  # Start at page 0
            
            # Display first page
            await display_creator_selection_page(search_message, session, 0)
            return
        
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
    has_more_pages = content_directory.get('has_more_pages', False)
    
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    # Add Pictures button if there are preview images
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    # Add Videos button if there are video links
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    # Add "Load More" button if there are more pages available
    if has_more_pages:
        keyboard.append([InlineKeyboardButton("⬇️ Load More Pages (3 more)", callback_data="load_more_pages")])
    
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


async def display_creator_selection_page(message, session, page: int = 0):
    """Display a page of creator options with pagination."""
    options = session.pending_creator_options
    creator_name = session.pending_creator_name
    
    if not options:
        await message.edit_text("❌ No creator options available. Please search again.")
        return
    
    # Pagination settings
    items_per_page = 5
    total_pages = (len(options) + items_per_page - 1) // items_per_page
    
    # Ensure page is within bounds
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    # Get items for current page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(options))
    page_options = options[start_idx:end_idx]
    
    # Build the selection message
    select_text = f"🔍 Found {len(options)} matches for '{creator_name}':\n\n"
    select_text += "Please select the correct creator:\n\n"
    
    if total_pages > 1:
        select_text += f"📄 Page {page + 1}/{total_pages}\n\n"
    
    keyboard = []
    for i, option in enumerate(page_options):
        actual_idx = start_idx + i
        name = option['name']
        
        # Show name without similarity percentage
        button_text = f"{name}"
        callback_data = f"select_creator|{actual_idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add navigation buttons if there are multiple pages
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"creator_page|{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"creator_page|{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="search_creator")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await send_message_with_retry(
            message.edit_text,
            select_text,
            reply_markup=reply_markup
        )
    except (TimedOut, NetworkError):
        pass
