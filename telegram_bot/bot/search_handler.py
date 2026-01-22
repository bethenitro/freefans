"""
Search Handler - Handles creator search functionality
"""

import logging
from typing import List, Dict
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
        from core.user_session import UserSession
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
            f"🔍 Searching for {creator_name}...\n\n"
            f"Finding the hottest content for you 🔥"
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to send search message: {e}")
        return
    
    try:
        # Check for existing pools for this creator first
        from managers.pool_manager import get_pool_manager
        pool_manager = get_pool_manager()
        existing_pools = pool_manager.get_active_pools(limit=5, creator_filter=creator_name)
        
        # Check if we need to show multiple options or proceed directly
        search_options = await bot_instance.content_manager.search_creator_options(creator_name)
        
        # If no content found but there are active pools, show pools
        if not search_options and existing_pools:
            await show_existing_pools_for_creator(search_message, creator_name, existing_pools)
            return
        
        # If both content and pools exist, show content first with pool option
        if search_options and existing_pools:
            # Store pools in session for later access
            session.existing_pools = existing_pools
        
        if not search_options:
            # No content and no pools
            try:
                message_text = f"😔 No content found for '{creator_name}'\n\n"
                message_text += f"Try this:\n"
                message_text += f"• Double-check the spelling\n"
                message_text += f"• Try a different name or alias\n"
                message_text += f"• Search for another creator\n\n"
                
                keyboard = []
                
                # Check if there are any pools for similar names
                similar_pools = pool_manager.get_active_pools(limit=3)
                if similar_pools:
                    message_text += f"💡 Or check out these active community pools:\n\n"
                    for i, pool in enumerate(similar_pools[:3], 1):
                        completion = pool['completion_percentage']
                        price = pool['current_price_per_user']
                        
                        message_text += f"**{i}. {pool['creator_name']} - {pool['content_title'][:30]}{'...' if len(pool['content_title']) > 30 else ''}**\n"
                        message_text += f"💰 {price} ⭐ • 📊 {completion:.1f}%\n\n"
                        
                        pool_text = f"🏊‍♀️ {pool['creator_name']} Pool ({price} ⭐)"
                        keyboard.append([InlineKeyboardButton(pool_text, callback_data=f"view_pool_{pool['pool_id']}")])
                    
                    keyboard.append([InlineKeyboardButton("🏊‍♀️ Browse All Pools", callback_data="pools_menu")])
                else:
                    message_text += f"💡 **Can't find '{creator_name}'? Request them!**\n\n"
                
                # Always add request option
                keyboard.append([InlineKeyboardButton(f"📝 Request '{creator_name}'", callback_data=f"request_creator_{creator_name}")])
                keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await send_message_with_retry(
                    search_message.edit_text,
                    message_text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            except (TimedOut, NetworkError):
                pass
            return
        
        # Show options for user to choose
        if search_options.get('needs_selection'):
            options = search_options['options']
            is_simpcity = search_options.get('simpcity_search', False)
            
            # Store all options in session for pagination
            session.pending_creator_options = options
            session.pending_creator_name = creator_name
            session.creator_selection_page = 0  # Start at page 0
            session.is_simpcity_search = is_simpcity  # Store search type
            
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


async def show_existing_pools_for_creator(message, creator_name: str, pools: List[Dict]):
    """Show existing pools for a creator when no content is found."""
    try:
        text = f"🏊‍♀️ **Community Pools for {creator_name}**\n\n"
        text += f"No direct content found, but there are active community pools!\n\n"
        text += f"💡 **Join a pool to get content when it's unlocked:**\n\n"
        
        keyboard = []
        
        for i, pool in enumerate(pools[:5], 1):
            completion = pool['completion_percentage']
            price = pool['current_price_per_user']
            
            pool_text = f"**{i}. {pool['content_title'][:40]}{'...' if len(pool['content_title']) > 40 else ''}**\n"
            pool_text += f"💰 Current Price: {price} ⭐\n"
            pool_text += f"📊 Progress: {completion:.1f}%\n"
            
            if i < len(pools):
                pool_text += "\n"
            
            text += pool_text
            
            # Add button for each pool
            button_text = f"🏊‍♀️ Join Pool {i} ({price} ⭐)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_pool_{pool['pool_id']}")])
        
        # Add navigation buttons
        keyboard.append([InlineKeyboardButton("🔍 Search Different Creator", callback_data="search_creator")])
        keyboard.append([InlineKeyboardButton("🏊‍♀️ Browse All Pools", callback_data="pools_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_message_with_retry(
            message.edit_text,
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error showing existing pools: {e}")
        await message.edit_text("❌ Error loading pools. Please try again.")


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
    is_simpcity = session.get('is_simpcity_search', False)
    
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
    if is_simpcity:
        select_text = f"🔥 Extended Search Results 🔥\n\n"
        select_text += f"Found {len(options)} matches for '{creator_name}'\n\n"
    else:
        select_text = f"✨ Found {len(options)} creators ✨\n\n"
        select_text += f"Searching for: '{creator_name}'\n\n"
    
    if total_pages > 1:
        select_text += f"📄 Page {page + 1} of {total_pages}\n\n"
    
    select_text += "Select the creator you want 👇\n"
    
    keyboard = []
    for i, option in enumerate(page_options):
        actual_idx = start_idx + i
        
        if is_simpcity:
            # Format SimpCity results with more details
            name = option['name']
            
            # Clean up platform names from the title
            from scrapers.simpcity_search import extract_creator_name_from_title
            clean_name = extract_creator_name_from_title(name)
            
            # Truncate name if too long
            if len(clean_name) > 60:
                clean_name = clean_name[:57] + "..."
            
            button_text = f"{clean_name}"
            callback_data = f"select_simpcity|{actual_idx}"
        else:
            # Format CSV results
            name = option['name']
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
    
    # Add "Extended Search" button for CSV results (not for SimpCity results)
    if not is_simpcity:
        keyboard.append([InlineKeyboardButton("🔍 Not found? Search More", callback_data="search_on_simpcity")])
    
    # Add existing pools button if there are pools for this creator
    if hasattr(session, 'existing_pools') and session.existing_pools:
        pool_count = len(session.existing_pools)
        keyboard.append([InlineKeyboardButton(f"🏊‍♀️ View {pool_count} Active Pool{'s' if pool_count > 1 else ''}", callback_data="show_creator_pools")])
    
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
