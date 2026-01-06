"""
Callback Handlers - Handles all callback queries from inline keyboards
"""

import logging
import re
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest
from bot.utilities import send_message_with_retry
from bot.ui_components import (
    create_filters_menu_keyboard, create_filter_selection_keyboard,
    format_filter_settings_text, format_content_details_text,
    create_content_details_keyboard, format_directory_text,
    create_content_keyboard, create_picture_navigation_keyboard,
    create_video_navigation_keyboard, create_content_directory_keyboard
)

# Add landing_server to path for landing service access
from services.landing_service import landing_service

logger = logging.getLogger(__name__)

# Picture/Video page message cache (still needed for UI state)
_media_page_cache = {}
_media_page_cache_ttl = timedelta(minutes=30)  # Cache formatted messages for 30 minutes
_media_page_cache_max_size = 100

def _clean_media_page_cache():
    """Remove expired entries from media page cache."""
    global _media_page_cache
    now = datetime.now()
    expired_keys = [
        key for key, value in _media_page_cache.items()
        if now - value['timestamp'] > _media_page_cache_ttl
    ]
    for key in expired_keys:
        del _media_page_cache[key]
    
    if len(_media_page_cache) > _media_page_cache_max_size:
        sorted_items = sorted(_media_page_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_items[:len(_media_page_cache) - _media_page_cache_max_size]:
            del _media_page_cache[key]

def _clear_all_media_page_cache():
    """Clear all media page cache entries."""
    global _media_page_cache
    _media_page_cache.clear()
    logger.info("✅ Cleared all media page cache entries")

def _get_cached_media_page(media_type: str, creator_url: str, page: int) -> Optional[list]:
    """Get cached formatted media page messages."""
    _clean_media_page_cache()
    cache_key = f"{media_type}:{creator_url}:{page}"
    
    if cache_key in _media_page_cache:
        logger.debug(f"✓ Media page cache hit for {media_type} page {page}")
        return _media_page_cache[cache_key]['data']
    return None

def _cache_media_page(media_type: str, creator_url: str, page: int, messages: list):
    """Cache formatted media page messages."""
    cache_key = f"{media_type}:{creator_url}:{page}"
    _media_page_cache[cache_key] = {
        'data': messages,
        'timestamp': datetime.now()
    }
    logger.debug(f"✓ Cached {media_type} page {page} (cache size: {len(_media_page_cache)})")

def escape_markdown(text: str) -> str:
    """Escape special characters for Markdown v2."""
    # Characters that need to be escaped in Markdown
    special_chars = ['_', '', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    
    # Answer callback query immediately to prevent timeout
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning(f"Callback query expired, continuing anyway: {e}")
        else:
            raise
    
    user_id = update.effective_user.id
    data = query.data
    
    if user_id not in bot_instance.user_sessions:
        from core.user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    session = bot_instance.user_sessions[user_id]
    
    # Route to appropriate handler
    if data == "search_creator":
        await handle_search_creator(query, session)
    elif data == "search_on_simpcity":
        await handle_search_on_simpcity(query, session, bot_instance)
    elif data.startswith("creator_page|"):
        await handle_creator_page_change(query, session, data)
    elif data.startswith("select_creator|"):
        await handle_select_creator(query, session, data, bot_instance)
    elif data.startswith("select_simpcity|"):
        await handle_select_simpcity(query, session, data, bot_instance)
    elif data.startswith("confirm_search|"):
        await handle_confirm_search(query, session, data, bot_instance)
    elif data == "load_more_pages":
        await handle_load_more_pages(query, session, bot_instance)
    elif data == "help":
        from bot.command_handlers import HELP_TEXT
        await query.message.reply_text(HELP_TEXT)
    elif data.startswith("content_"):
        await handle_content_details(query, session, data)
    elif data.startswith("page_"):
        await handle_page_change(query, session, data, bot_instance)
    elif data.startswith("download_"):
        await handle_download_request(query, session, data, bot_instance)
    elif data.startswith("preview_"):
        await handle_preview_request(query, session, data, bot_instance)
    elif data == "back_to_list":
        await handle_back_to_list(query, session)
    elif data == "back_to_search":
        session.awaiting_request = 'search'
        await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")
    elif data == "view_pictures":
        await handle_view_pictures(query, session)
    elif data == "view_videos":
        await handle_view_videos(query, session)
    elif data.startswith("picture_page_"):
        await handle_picture_page(query, session, data)
    elif data.startswith("video_page_"):
        await handle_video_page(query, session, data)
    elif data.startswith("video_skip_"):
        await handle_video_skip_menu(query, session, data)
    elif data.startswith("video_cancel_"):
        await handle_video_cancel(query, session, data)
    elif data.startswith("video_goto_"):
        await handle_video_goto(query, session, data)
    elif data.startswith("picture_skip_"):
        await handle_picture_skip_menu(query, session, data)
    elif data.startswith("picture_cancel_"):
        await handle_picture_cancel(query, session, data)
    elif data.startswith("picture_goto_"):
        await handle_picture_goto(query, session, data)
    elif data.startswith("picture_link_"):
        await handle_picture_link(query, session, data)
    elif data.startswith("picture_"):
        await handle_picture_details(query, session, data)
    elif data == "view_of_feed":
        await handle_view_of_feed(query, session, bot_instance)
    elif data.startswith("of_feed_page_"):
        await handle_of_feed_page(query, session, data, bot_instance)
    elif data.startswith("of_feed_skip_"):
        await handle_of_feed_skip_menu(query, session, data)
    elif data.startswith("of_feed_goto_"):
        await handle_of_feed_goto(query, session, data, bot_instance)
    elif data.startswith("of_feed_cancel_"):
        await handle_of_feed_cancel(query, session, data)

async def handle_search_creator(query, session) -> None:
    """Handle search creator callback."""
    # Set the session state to expect a search input
    session.awaiting_request = 'search'
    await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")

async def handle_search_on_simpcity(query, session, bot_instance) -> None:
    """Handle extended search request when CSV results don't match."""
    if not session.pending_creator_name:
        await query.edit_message_text("⚠️ Please start a new search.")
        return
    
    creator_name = session.pending_creator_name
    
    # Show loading message
    await query.edit_message_text(
        f"🔍 Performing extended search for '{creator_name}'...\n"
        "This may take a few moments."
    )
    
    # Import asyncio
    import asyncio
    
    try:
        # Search SimpCity (but don't tell the user)
        simpcity_results = await bot_instance.content_manager.scraper.search_simpcity(creator_name)
        
        if not simpcity_results:
            await query.edit_message_text(
                f"❌ No additional results found for '{creator_name}'.\n\n"
                "The creator may not be available, or try:\n"
                "• Check the spelling\n"
                "• Try a different name/alias\n"
                "• Search for a different creator"
            )
            return
        
        # Format and display results (without mentioning SimpCity)
        logger.info(f"Found {len(simpcity_results)} extended search results for {creator_name}")
        
        # Store results in session
        session.pending_creator_options = [
            {
                'name': result['title'],
                'url': result['url'],
                'replies': result['replies'],
                'date': result['date'],
                'snippet': result['snippet'],
                'thumbnail': result['thumbnail'],
                'source': 'simpcity'
            }
            for result in simpcity_results
        ]
        session.is_simpcity_search = True
        session.creator_selection_page = 0
        
        # Display first page
        from bot.search_handler import display_creator_selection_page
        await display_creator_selection_page(query.message, session, 0)
        
    except Exception as e:
        logger.error(f"Error in extended search: {e}")
        await query.edit_message_text(
            "⚠️ Server issue - please try again later."
        )

async def handle_creator_page_change(query, session, data: str) -> None:
    """Handle pagination for creator selection."""
    try:
        page = int(data.split("|")[1])
        session.creator_selection_page = page
        
        # Use the display function from search_handler
        from bot.search_handler import display_creator_selection_page
        await display_creator_selection_page(query.message, session, page)
        
    except (IndexError, ValueError) as e:
        logger.error(f"Error handling creator page change: {e}")
        await query.answer("⚠️ Server issue - please try again", show_alert=True)

async def handle_select_creator(query, session, data: str, bot_instance) -> None:
    """Handle user selection of a creator from multiple options."""
    if not session.pending_creator_options:
        await query.edit_message_text("⚠️ Server issue - please search again.")
        return
    
    # Extract the selected index
    try:
        selected_idx = int(data.split("|")[1])
        selected_option = session.pending_creator_options[selected_idx]
    except (IndexError, ValueError):
        await query.edit_message_text("⚠️ Server issue - please try again.")
        return
    
    creator_name = selected_option['name']
    creator_url = selected_option['url']
    
    # Show initial loading message
    await query.edit_message_text(
        f"✅ Selected: {creator_name}\n"
        f"🔄 Loading content..."
    )
    
    # Import asyncio for progress messages
    import asyncio
    
    # Progress messages to show while loading
    filler_messages = [
        f"✅ Selected: {creator_name}\n🔄 Connecting to database...",
        f"✅ Selected: {creator_name}\n🔄 Retrieving content...",
        f"✅ Selected: {creator_name}\n🔄 Processing media...",
        f"✅ Selected: {creator_name}\n🔄 Almost ready..."
    ]
    
    # Create a task for fetching content
    fetch_task = asyncio.create_task(
        bot_instance.content_manager.search_creator_content(
            creator_name,
            session.filters,
            direct_url=creator_url,
            cache_only=True  # Check cache first, only scrape if not cached
        )
    )
    
    # Show filler messages while fetching
    message_index = 0
    while not fetch_task.done():
        try:
            # Update message every 2 seconds
            await asyncio.sleep(2)
            if not fetch_task.done() and message_index < len(filler_messages):
                await query.edit_message_text(filler_messages[message_index])
                message_index += 1
        except Exception:
            pass  # Ignore errors during filler message updates
    
    # Get the result
    try:
        content_directory = await fetch_task
        
        if not content_directory:
            await query.edit_message_text(
                f"❌ Failed to load content for '{creator_name}'.\n\n"
                "⚠️ Server issue - please try again later."
            )
            return
        
        # Check if creator has no content (0 items)
        total_pictures = len(content_directory.get('preview_images', []))
        total_videos = len(content_directory.get('video_links', []))
        total_items = len(content_directory.get('items', []))
        
        if total_pictures == 0 and total_videos == 0 and total_items == 0:
            await query.edit_message_text(
                f"📭 No content currently available for '{creator_name}'.\n\n"
                f"This creator's thread may be empty or all content has been filtered out.\n\n"
                f"💡 Try:\n"
                f"• Adjusting your filters\n"
                f"• Searching for another creator\n"
                f"• Submitting request for creator."
            )
            return
            
        # Update session
        session.current_directory = content_directory
        session.current_creator = creator_name
        
        # Display content directory (always show Load More if not all pages fetched)
        total_pages = content_directory.get('total_pages', 1)
        end_page = content_directory.get('end_page', 1)
        has_more_pages = end_page < total_pages  # Show if not all pages fetched
        social_links = content_directory.get('social_links', {})
        has_onlyfans = social_links.get('onlyfans') is not None
        directory_text = format_directory_text(creator_name, content_directory, session.filters)
        
        # Create modern keyboard using helper function
        reply_markup = create_content_directory_keyboard(
            total_pictures, total_videos, has_onlyfans, has_more_pages
        )
        
        await send_message_with_retry(
            query.message.reply_text,
            directory_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        # Delete the selection message
        try:
            await query.delete_message()
        except (TimedOut, NetworkError, BadRequest):
            pass
        
        # Clear pending options
        session.pending_creator_options = None
        session.pending_creator_name = None
        
    except Exception as e:
        logger.error(f"Error loading selected creator: {e}")
        await query.edit_message_text(
            f"❌ An error occurred while loading content for '{creator_name}'.\n\n"
            "Please try again later."
        )

async def handle_select_simpcity(query, session, data: str, bot_instance) -> None:
    """Handle user selection of a creator from extended search results."""
    if not session.pending_creator_options:
        await query.edit_message_text("⚠️ Please search again.")
        return
    
    # Extract the selected index
    try:
        selected_idx = int(data.split("|")[1])
        selected_option = session.pending_creator_options[selected_idx]
    except (IndexError, ValueError):
        await query.edit_message_text("⚠️ Please try again.")
        return
    
    # Extract creator name from title (clean it up)
    from scrapers.simpcity_search import extract_creator_name_from_title
    creator_title = selected_option['name']
    creator_name = extract_creator_name_from_title(creator_title)
    creator_url = selected_option['url']
    
    # Show simple loading message
    await query.edit_message_text(
        f"⏳ Loading {creator_name}'s content...\n\n"
        f"Getting everything ready for you 🔥"
    )
    
    # Add creator to CSV (silently)
    try:
        added = bot_instance.content_manager.scraper.add_creator_to_csv(creator_name, creator_url)
        if added:
            logger.info(f"Added creator to CSV: {creator_name}")
        else:
            logger.info(f"Creator already exists in CSV: {creator_name}")
    except Exception as e:
        logger.error(f"Failed to add creator to CSV: {e}")
    
    # Import asyncio for progress messages
    import asyncio
    
    # Progress messages
    filler_messages = [
        f"⏳ Fetching content for {creator_name}...",
        f"⏳ Processing data...",
        f"⏳ Extracting media...",
        f"⏳ Almost ready..."
    ]
    
    # Create a task for fetching content
    fetch_task = asyncio.create_task(
        bot_instance.content_manager.search_creator_content(
            creator_name,
            session.filters,
            direct_url=creator_url,
            cache_only=True  # Check cache first, only scrape if not cached
        )
    )
    
    # Show filler messages while fetching
    message_index = 0
    while not fetch_task.done():
        try:
            await asyncio.sleep(2)
            if not fetch_task.done() and message_index < len(filler_messages):
                await query.edit_message_text(filler_messages[message_index])
                message_index += 1
        except Exception:
            pass
    
    # Get the result
    try:
        content_directory = await fetch_task
        
        if not content_directory:
            await query.edit_message_text(
                f"❌ Failed to load content for '{creator_name}'.\n\n"
                "The thread may be empty or unavailable. Please try another option."
            )
            return
        
        # Check if creator has no content (0 items)
        total_pictures = len(content_directory.get('preview_images', []))
        total_videos = len(content_directory.get('video_links', []))
        total_items = len(content_directory.get('items', []))
        
        if total_pictures == 0 and total_videos == 0 and total_items == 0:
            await query.edit_message_text(
                f"📭 No content currently available for '{creator_name}'.\n\n"
                f"This creator's thread may be empty or all content has been filtered out.\n\n"
                f"💡 Try:\n"
                f"• Adjusting your filters\n"
                f"• Searching for another creator\n"
                f"• Submitting request for creator"
            )
            return
        
        # Update session
        session.current_directory = content_directory
        session.current_creator = creator_name
        
        # Display content directory
        total_pages = content_directory.get('total_pages', 1)
        end_page = content_directory.get('end_page', 1)
        has_more_pages = end_page < total_pages
        social_links = content_directory.get('social_links', {})
        has_onlyfans = social_links.get('onlyfans') is not None
        directory_text = format_directory_text(creator_name, content_directory, session.filters)
        
        # Create modern keyboard using helper function
        reply_markup = create_content_directory_keyboard(
            total_pictures, total_videos, has_onlyfans, has_more_pages
        )
        
        await send_message_with_retry(
            query.message.reply_text,
            directory_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        # Delete the selection message
        try:
            await query.delete_message()
        except (TimedOut, NetworkError, BadRequest):
            pass
        
        # Clear pending options
        session.pending_creator_options = None
        session.pending_creator_name = None
        session.is_simpcity_search = False
        
    except Exception as e:
        logger.error(f"Error loading SimpCity creator: {e}")
        await query.edit_message_text(
            f"❌ An error occurred while loading content.\n\n"
            "Please try again later."
        )

async def handle_confirm_search(query, session, data: str, bot_instance) -> None:
    """Handle confirmation of fuzzy match."""
    creator_name = data.split("|")[1]
    if session.pending_content:
        from bot.search_handler import display_content_directory
        # Need to create a mock update for display_content_directory
        # Instead, we'll inline the logic here
        await display_content_directory_from_callback(
            query, session, session.pending_content, creator_name
        )
        try:
            await query.delete_message()
        except (TimedOut, NetworkError, BadRequest):
            pass
        session.pending_content = None

async def display_content_directory_from_callback(query, session, content_directory: dict, creator_name: str) -> None:
    """Display the content directory from a callback query."""
    session.current_directory = content_directory
    session.current_creator = creator_name
    
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    has_more_pages = content_directory.get('has_more_pages', False)
    social_links = content_directory.get('social_links', {})
    has_onlyfans = social_links.get('onlyfans') is not None
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    # Add Onlyfans Feed button if OnlyFans link is available
    if has_onlyfans:
        keyboard.append([InlineKeyboardButton("📱 Onlyfans Feed", callback_data="view_of_feed")])
    
    # Add "Load More" button if there are more pages available
    if has_more_pages:
        keyboard.append([InlineKeyboardButton("⬇️ Load More Pages (3 more)", callback_data="load_more_pages")])
    
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await send_message_with_retry(
            query.message.reply_text,
            directory_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to display content directory from callback: {e}")

async def handle_load_more_pages(query, session, bot_instance) -> None:
    """Handle loading more content for the current creator."""
    if not session.current_directory or not session.current_creator:
        await query.edit_message_text("⚠️ No content available.")
        return
    
    creator_name = session.current_creator
    current_content = session.current_directory
    
    # Log current state for debugging
    logger.info(f"Load More clicked for: {creator_name}")
    logger.info(f"Current end_page: {current_content.get('end_page', 'unknown')}")
    logger.info(f"Current total_pages: {current_content.get('total_pages', 'unknown')}")
    logger.info(f"Current has_more_pages: {current_content.get('has_more_pages', 'unknown')}")
    
    # Check if there is actually more content to load
    if not current_content.get('has_more_pages', False):
        logger.info(f"No more pages available for {creator_name}")
        await query.answer("✅ All available content has been loaded!", show_alert=True)
        return
    
    # Answer callback query immediately to prevent timeout
    try:
        await query.answer()
    except Exception:
        pass  # Ignore if query already expired
    
    # Show loading message
    await query.edit_message_text(
        f"⏳ Loading more content for '{creator_name}'...\n"
        f"Please wait..."
    )
    
    try:
        # Load more content
        updated_content = await bot_instance.content_manager.fetch_more_pages(
            creator_name,
            session.filters,
            current_content,
            pages_to_fetch=3
        )
        
        if updated_content:
            # Update session with new content
            session.current_directory = updated_content
            
            # Display updated directory
            total_pictures = len(updated_content.get('preview_images', []))
            total_videos = len(updated_content.get('video_links', []))
            has_more_pages = updated_content.get('has_more_pages', False)
            social_links = updated_content.get('social_links', {})
            has_onlyfans = social_links.get('onlyfans') is not None
            directory_text = format_directory_text(creator_name, updated_content, session.filters)
            
            # Create keyboard
            keyboard = []
            
            if total_pictures > 0:
                keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
            
            if total_videos > 0:
                keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
            
            # Add Onlyfans Feed button if OnlyFans link is available
            if has_onlyfans:
                keyboard.append([InlineKeyboardButton("📱 Onlyfans Feed", callback_data="view_of_feed")])
            
            # Add "Load More" button if there is still more content
            if has_more_pages:
                keyboard.append([InlineKeyboardButton("⬇️ Load More Content", callback_data="load_more_pages")])
            
            keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(directory_text, reply_markup=reply_markup, disable_web_page_preview=True)
            
            # Success message shown in the updated content
        else:
            await query.edit_message_text("⚠️ Server issue - please try again.")
            
    except Exception as e:
        logger.error(f"Error loading more content: {e}")
        await query.edit_message_text("⚠️ Server issue - please try again.")

async def handle_set_filters(query, session) -> None:
    """Show the filters configuration menu."""
    filter_text = format_filter_settings_text(session.filters)
    reply_markup = create_filters_menu_keyboard()
    await query.edit_message_text(filter_text, reply_markup=reply_markup)

async def handle_content_details(query, session, data: str) -> None:
    """Show detailed information about a specific content item."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("⚠️ Content not found.")
        return
    
    item = session.current_directory['items'][content_idx]
    details_text = format_content_details_text(item, content_idx)
    reply_markup = create_content_details_keyboard(content_idx)
    
    await query.edit_message_text(details_text, reply_markup=reply_markup)

async def handle_page_change(query, session, data: str, bot_instance) -> None:
    """Update the content list to show a different page."""
    page = int(data.split("_")[1])
    session.current_page = page
    await handle_back_to_list(query, session)

async def handle_filter_menu(query, session, data: str) -> None:
    """Handle filter option selection."""
    filter_type = data.replace("filter_", "")
    
    if filter_type == "reset":
        session.reset_filters()
        await query.edit_message_text("✅ Filters have been reset to default values.")
        return
    
    reply_markup, text = create_filter_selection_keyboard(filter_type)
    if text:
        await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_apply_filter(query, session, data: str) -> None:
    """Apply a specific filter setting."""
    parts = data.split("_")
    if len(parts) >= 4:
        filter_type = parts[2] + "_" + parts[3] if len(parts) == 5 else parts[2]
        value = parts[4] if len(parts) == 5 else parts[3]
        
        session.set_filter(filter_type, value)
        
        await query.edit_message_text(
            f"✅ Filter updated!\n\n{filter_type.replace('_', ' ').title()}: {value.title()}\n\n"
            "Filter has been applied. Your next search will use these settings."
        )

async def handle_download_request(query, session, data: str, bot_instance) -> None:
    """Handle download link request for content with hidden links."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("⚠️ Content not found.")
        return
    
    item = session.current_directory['items'][content_idx]
    
    await query.edit_message_text("🔗 Generating secure download link...\nPlease wait...")
    
    try:
        download_link = await bot_instance.content_manager.get_content_download_link(
            session.current_creator, content_idx
        )
        
        if download_link:
            session.increment_downloads()
            title = item.get('title', 'Untitled')
            
            link_text = f"""🔗 Download Link Generated

📄 Content: {title}
🎬 Type: {item.get('type', 'Unknown')}

[👀 Download Content]({download_link})

⚠️ Important:
• Right-click → Save As to download
• Some links may require opening in browser

💡 Tip: Use the link above to access the content.
            """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Generate New Link", callback_data=f"download_{content_idx}")],
                [InlineKeyboardButton("⬅️ Back to Details", callback_data=f"content_{content_idx}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(link_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("⚠️ Server issue - please try again.")
            
    except Exception as e:
        logger.error(f"Error generating download link: {e}")
        await query.edit_message_text("⚠️ Server issue - please try again.")

async def handle_preview_request(query, session, data: str, bot_instance) -> None:
    """Handle preview request for content."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("⚠️ Content not found.")
        return
    
    item = session.current_directory['items'][content_idx]
    await query.edit_message_text("👁️ Generating preview...\nPlease wait...")
    
    try:
        preview_info = await bot_instance.content_manager.get_content_preview(
            session.current_creator, content_idx
        )
        
        if preview_info:
            preview_text = f"""
👁️ Content Preview

📄 {item.get('title', 'Untitled')}
🎬 {item.get('type', 'Unknown')} | {item.get('size', 'Unknown')}

🖼️ Preview URL:
{preview_info.get('preview_url', 'Not available')}

📷 Thumbnail:
{preview_info.get('thumbnail_url', 'Not available')}

💡 Note: These are placeholder preview URLs. In the final version, you'll see actual previews.
            """
            
            keyboard = [
                [InlineKeyboardButton("🔗 Get Download Link", callback_data=f"download_{content_idx}")],
                [InlineKeyboardButton("⬅️ Back to Details", callback_data=f"content_{content_idx}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(preview_text, reply_markup=reply_markup)
        else:
            await query.edit_message_text("⚠️ Preview not available.")
            
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        await query.edit_message_text("⚠️ Server issue - please try again.")

async def handle_back_to_list(query, session) -> None:
    """Return to the content list view."""
    if not session.current_directory:
        await query.edit_message_text("⚠️ Server issue - please try again.")
        return
    
    creator_name = session.current_creator
    content_directory = session.current_directory
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    has_more_pages = content_directory.get('has_more_pages', False)
    social_links = content_directory.get('social_links', {})
    has_onlyfans = social_links.get('onlyfans') is not None
    
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    # Add Onlyfans Feed button if OnlyFans link is available
    if has_onlyfans:
        keyboard.append([InlineKeyboardButton("📱 Onlyfans Feed", callback_data="view_of_feed")])
    
    # Add "Load More" button if there are more pages available
    if has_more_pages:
        keyboard.append([InlineKeyboardButton("⬇️ Load More Pages (3 more)", callback_data="load_more_pages")])
    
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(directory_text, reply_markup=reply_markup, disable_web_page_preview=True)

async def handle_view_pictures(query, session, page: int = 0) -> None:
    """Show preview pictures list."""
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if not preview_images:
        await query.edit_message_text("No preview pictures available.")
        return
    
    items_per_page = 10
    total_pages = (len(preview_images) + items_per_page - 1) // items_per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = preview_images[start_idx:end_idx]
    
    # Check cache for this specific page
    creator_url = session.current_directory.get('url', '')
    if not creator_url:
        # Fallback: use creator name if URL is missing
        creator_url = session.current_creator or 'unknown'
        logger.debug(f"Using creator name as cache key fallback: {creator_url}")
    else:
        logger.debug(f"Using URL as cache key: {creator_url}")
    cached_messages = _get_cached_media_page('pictures', creator_url, page)
    
    if cached_messages:
        logger.info(f"✓ Using cached picture messages for page {page}")
        # Send cached messages immediately one by one (they're already processed)
        for msg in cached_messages:
            try:
                await send_message_with_retry(
                    query.message.reply_text,
                    msg['text'],
                    parse_mode=msg.get('parse_mode', 'Markdown'),
                    disable_web_page_preview=msg.get('disable_web_page_preview', False)
                )
                # Very small delay for cached messages
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send cached picture message: {e}")
    else:
        await query.edit_message_text(f"Loading pictures {start_idx + 1}-{min(end_idx, len(preview_images))}...")
        
        creator_name = session.current_creator or 'Unknown Creator'
        
        # Track timing for performance monitoring
        import time
        start_time = time.time()
        
        # Prepare batch request for all pictures
        batch_items = []
        for idx, item in enumerate(page_items):
            batch_items.append({
                'creator_name': creator_name,
                'content_title': f'Picture #{start_idx + idx + 1}',
                'content_type': '🖼️ Picture',
                'original_url': item.get('url', ''),
                'preview_url': item.get('url', ''),
                'thumbnail_url': item.get('url', ''),
                'expires_hours': 24
            })
        
        # Send batch request to FastAPI
        logger.info(f"📤 Sending batch request to FastAPI for {len(batch_items)} pictures")
        batch_start = time.time()
        
        try:
            landing_urls = await landing_service.generate_batch_landing_urls_async(batch_items)
            batch_time = time.time() - batch_start
            logger.info(f"✅ Received {len(landing_urls)} landing URLs in {batch_time:.2f}s")
        except Exception as e:
            batch_time = time.time() - batch_start
            logger.error(f"❌ Batch request failed after {batch_time:.2f}s: {e}")
            # Show user-friendly error message
            await query.edit_message_text(
                "❌ Failed to load pictures. Please try again later.\n\n"
                "The server may be temporarily unavailable."
            )
            return
        
        # Send all pictures to user
        messages_to_cache = []
        
        async def send_picture_message(idx: int, landing_url: str) -> dict:
            """Send a single picture message to user"""
            message_text = f"""🖼️ Picture #{start_idx + idx + 1}

[👀 View Image]({landing_url})
"""
            
            message_data = {
                'text': message_text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            }
            
            # Send message immediately
            try:
                await send_message_with_retry(
                    query.message.reply_text,
                    message_data['text'],
                    parse_mode=message_data.get('parse_mode', 'Markdown'),
                    disable_web_page_preview=message_data['disable_web_page_preview']
                )
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.15)
            except Exception as e:
                logger.error(f"Failed to send picture message: {e}")
            
            return message_data
        
        # Send all pictures concurrently
        logger.info(f"🚀 Sending {len(landing_urls)} picture messages to user")
        send_start = time.time()
        tasks = [send_picture_message(idx, landing_urls[idx]) for idx in range(len(landing_urls))]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        send_time = time.time() - send_start
        
        # Filter out None and exceptions
        for result in results:
            if result and not isinstance(result, Exception):
                messages_to_cache.append(result)
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Completed {len(messages_to_cache)}/{len(page_items)} pictures in {total_time:.2f}s")
        logger.info(f"⏱️ Completed {len(messages_to_cache)}/{len(page_items)} pictures in {total_time:.2f}s")
        
        # Cache the messages for this page (in background)
        _cache_media_page('pictures', creator_url, page, messages_to_cache)
    
    # Send navigation message
    nav_text = f"""

  🖼️ Photo Gallery �️  

📊 Showing: {start_idx + 1}-{min(end_idx, len(preview_images))} of {len(preview_images)}
📄 Page: {page + 1} / {total_pages}

💡 Tap links to view full-size images
    """
    
    reply_markup = create_picture_navigation_keyboard(page, total_pages, end_idx, len(preview_images))
    await query.message.reply_text(nav_text, reply_markup=reply_markup)

async def handle_picture_page(query, session, data: str) -> None:
    """Handle picture page navigation."""
    page = int(data.split("_")[2])
    await handle_view_pictures(query, session, page)

async def handle_picture_skip_menu(query, session, data: str) -> None:
    """Show smart menu to skip to a specific page in one step."""
    current_page = int(data.split("_")[2])
    
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if not preview_images:
        await query.edit_message_text("No preview pictures available.")
        return
    
    items_per_page = 10
    total_pages = (len(preview_images) + items_per_page - 1) // items_per_page
    
    skip_text = f"""
⏩ Quick Jump ⏩

Total: {len(preview_images)} pictures
Pages: {total_pages} (10 per page)
Current: Page {current_page + 1}

Select the page you want to jump to 👇
    """
    
    keyboard = []
    
    # Smart pagination based on total pages
    if total_pages <= 25:
        # If 25 or fewer pages, show all (5 per row)
        for i in range(0, total_pages, 5):
            row = []
            for j in range(i, min(i + 5, total_pages)):
                # Highlight current page
                if j == current_page:
                    row.append(InlineKeyboardButton(f"• {j + 1} •", callback_data=f"picture_goto_{j}"))
                else:
                    row.append(InlineKeyboardButton(f"{j + 1}", callback_data=f"picture_goto_{j}"))
            keyboard.append(row)
    
    elif total_pages <= 50:
        # For 26-50 pages: Show first 10, middle section with intervals, last 10
        row = []
        
        # First 10 pages (compacted)
        for i in range(0, min(10, total_pages)):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"picture_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"picture_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Middle pages with intervals of 5
        if total_pages > 20:
            for i in range(10, total_pages - 10, 5):
                if i == current_page:
                    row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"picture_goto_{i}"))
                else:
                    row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"picture_goto_{i}"))
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Last 10 pages
        for i in range(max(10, total_pages - 10), total_pages):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"picture_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"picture_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    else:
        # For 50+ pages: Show key pages with smart intervals
        pages_to_show = []
        
        # Always show first 5
        pages_to_show.extend(range(0, min(5, total_pages)))
        
        # Show pages around current page
        if current_page >= 5:
            start = max(5, current_page - 2)
            end = min(total_pages - 5, current_page + 3)
            pages_to_show.extend(range(start, end))
        
        # Show every 10th page in the middle
        for i in range(10, total_pages - 10, 10):
            if i not in pages_to_show:
                pages_to_show.append(i)
        
        # Always show last 5
        pages_to_show.extend(range(max(5, total_pages - 5), total_pages))
        
        # Remove duplicates and sort
        pages_to_show = sorted(set(pages_to_show))
        
        # Create buttons (4 per row for better fit)
        row = []
        for page_idx in pages_to_show:
            if page_idx == current_page:
                row.append(InlineKeyboardButton(f"• {page_idx + 1} •", callback_data=f"picture_goto_{page_idx}"))
            else:
                row.append(InlineKeyboardButton(f"{page_idx + 1}", callback_data=f"picture_goto_{page_idx}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"picture_cancel_{current_page}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(skip_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_picture_cancel(query, session, data: str) -> None:
    """Cancel picture skip and return to navigation without resending pictures."""
    current_page = int(data.split("_")[2])
    await show_pictures_navigation(query, session, current_page)

async def show_pictures_navigation(query, session, page: int) -> None:
    """Show only the navigation menu without re-sending pictures."""
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if not preview_images:
        await query.edit_message_text("No preview pictures available.")
        return
    
    items_per_page = 10
    total_pages = (len(preview_images) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(preview_images))
    
    # Just show navigation message
    nav_text = f"""

  🖼️ Photo Gallery 🖼️  

� Showing: {start_idx + 1}-{end_idx} of {len(preview_images)}
📄 Page: {page + 1} / {total_pages}

💡 Use navigation buttons below
    """
    
    reply_markup = create_picture_navigation_keyboard(page, total_pages, end_idx, len(preview_images))
    await query.edit_message_text(nav_text, reply_markup=reply_markup)

async def handle_picture_goto(query, session, data: str) -> None:
    """Go to specific picture page."""
    page = int(data.split("_")[2])
    await handle_view_pictures(query, session, page)

async def handle_picture_details(query, session, data: str) -> None:
    """Show picture details."""
    picture_idx = int(data.split("_")[1])
    
    if not session.current_directory:
        await query.edit_message_text("⚠️ Server issue - please try again.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if picture_idx >= len(preview_images):
        await query.edit_message_text("⚠️ Content not found.")
        return
    
    picture = preview_images[picture_idx]
    
    details_text = f"""
🖼️ Picture #{picture_idx + 1}

🔗 URL: {picture.get('url', 'N/A')[:150]}

Click the button below to get the direct link.
    """
    
    keyboard = [
        [InlineKeyboardButton("🔗 Get Image Link", callback_data=f"picture_link_{picture_idx}")],
        [InlineKeyboardButton("⬅️ Back to Pictures", callback_data="view_pictures")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(details_text, reply_markup=reply_markup)

async def handle_picture_link(query, session, data: str) -> None:
    """Show picture landing page link with hidden links."""
    picture_idx = int(data.split("_")[2])
    
    if not session.current_directory:
        await query.edit_message_text("⚠️ Server issue - please try again.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if picture_idx >= len(preview_images):
        await query.edit_message_text("⚠️ Content not found.")
        return
    
    picture = preview_images[picture_idx]
    original_url = picture.get('url', '')
    creator_name = session.current_creator or 'Unknown Creator'
    
    # Generate landing page URL
    landing_url = await landing_service.generate_landing_url_async(
        creator_name=creator_name,
        content_title=picture.get('title', f'Picture #{picture_idx + 1}'),
        content_type=picture.get('type', '🖼️ Picture'),
        original_url=original_url,
        preview_url=original_url,  # Use the image itself as preview
        thumbnail_url=original_url
    )
    
    link_text = f"""🖼️ Picture #{picture_idx + 1}

[👀 View Image]({landing_url})
"""
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Picture", callback_data=f"picture_{picture_idx}")],
        [InlineKeyboardButton("📋 Back to Pictures List", callback_data="view_pictures")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(link_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_view_videos(query, session, page: int = 0) -> None:
    """Show video links list."""
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    video_links = session.current_directory.get('video_links', [])
    if not video_links:
        await query.edit_message_text("No video links available.")
        return
    
    items_per_page = 10
    total_pages = (len(video_links) + items_per_page - 1) // items_per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = video_links[start_idx:end_idx]
    
    # Check cache for this specific page
    creator_url = session.current_directory.get('url', '')
    if not creator_url:
        # Fallback: use creator name if URL is missing
        creator_url = session.current_creator or 'unknown'
        logger.debug(f"Using creator name as cache key fallback: {creator_url}")
    else:
        logger.debug(f"Using URL as cache key: {creator_url}")
    cached_messages = _get_cached_media_page('videos', creator_url, page)
    
    if cached_messages:
        logger.info(f"✓ Using cached video messages for page {page}")
        # Send cached messages immediately one by one (they're already processed)
        for msg in cached_messages:
            try:
                await send_message_with_retry(
                    query.message.reply_text,
                    msg['text'],
                    parse_mode=msg.get('parse_mode', 'Markdown'),
                    disable_web_page_preview=msg.get('disable_web_page_preview', False)
                )
                # Very small delay for cached messages
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send cached video message: {e}")
    else:
        await query.edit_message_text(f"Loading videos {start_idx + 1}-{min(end_idx, len(video_links))}...")
        
        creator_name = session.current_creator or 'Unknown Creator'
        
        # Track timing for performance monitoring
        import time
        start_time = time.time()
        
        # Prepare batch request for all videos
        batch_items = []
        for idx, item in enumerate(page_items):
            batch_items.append({
                'creator_name': creator_name,
                'content_title': item.get('title', f'Video #{start_idx + idx + 1}'),
                'content_type': item.get('type', '🎬 Video'),
                'original_url': item.get('url', ''),
                'preview_url': None,
                'thumbnail_url': None,
                'expires_hours': 24
            })
        
        # Send batch request to FastAPI
        logger.info(f"📤 Sending batch request to FastAPI for {len(batch_items)} videos")
        batch_start = time.time()
        
        try:
            landing_urls = await landing_service.generate_batch_landing_urls_async(batch_items)
            batch_time = time.time() - batch_start
            logger.info(f"✅ Received {len(landing_urls)} landing URLs in {batch_time:.2f}s")
            
            # Check if we have the right number of URLs
            if len(landing_urls) != len(page_items):
                logger.error(f"❌ URL count mismatch: got {len(landing_urls)} URLs for {len(page_items)} items")
                # Pad with original URLs if needed
                while len(landing_urls) < len(page_items):
                    landing_urls.append(page_items[len(landing_urls)].get('url', ''))
                
        except Exception as e:
            batch_time = time.time() - batch_start
            logger.error(f"❌ Batch request failed after {batch_time:.2f}s: {e}")
            # Show user-friendly error message
            await query.edit_message_text(
                "❌ Failed to load videos. Please try again later.\n\n"
                "The server may be temporarily unavailable."
            )
            return
        
        # Send all videos to user
        messages_to_cache = []
        
        async def send_video_message(idx: int, landing_url: str, item: dict) -> dict:
            """Send a single video message to user"""
            from managers.permissions_manager import get_permissions_manager
            
            original_url = item.get('url', '')
            title = item.get('title', f'Video #{start_idx + idx + 1}')
            
            # Check if landing URL is valid
            if not landing_url:
                logger.error(f"❌ Empty landing URL for video {idx + 1}: {title}")
                # Send server error message instead of fallback
                error_message = f"""🎬 {title}

❌ Server Error - Unable to generate link
Please try again later."""
                
                try:
                    await send_message_with_retry(
                        query.message.reply_text,
                        error_message
                    )
                    await asyncio.sleep(0.2)
                except Exception as e:
                    logger.error(f"Failed to send error message: {e}")
                
                return {'text': error_message, 'parse_mode': None, 'disable_web_page_preview': True}
            
            # Check if user is a worker to show original URL
            permissions = get_permissions_manager()
            user_id = query.from_user.id
            is_worker = permissions.is_worker(user_id)
            
            # Create message text with hidden links using Markdown
            if is_worker:
                # For workers, include creator name in the message
                message_text = f"""🎬 {title}
👤 Creator: {creator_name}

[👀 View Video]({landing_url})
[🔗 Original Link]({original_url})
"""
            else:
                message_text = f"""🎬 {title}

[👀 View Video]({landing_url})
"""
            
            message_data = {
                'text': message_text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False,
                'original_url': original_url
            }
            
            # Send message immediately
            try:
                await send_message_with_retry(
                    query.message.reply_text,
                    message_data['text'],
                    parse_mode=message_data.get('parse_mode', 'Markdown'),
                    disable_web_page_preview=message_data['disable_web_page_preview']
                )
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"Failed to send video message: {e}")
                logger.error(f"Message text was: {message_text}")
            
            return message_data
            
            return message_data
        
        # Send all videos concurrently
        logger.info(f"🚀 Sending {len(landing_urls)} video messages to user")
        send_start = time.time()
        tasks = [send_video_message(idx, landing_urls[idx], page_items[idx]) for idx in range(len(landing_urls))]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        send_time = time.time() - send_start
        
        # Filter out None and exceptions
        for result in results:
            if result and not isinstance(result, Exception):
                messages_to_cache.append(result)
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Completed {len(messages_to_cache)}/{len(page_items)} videos in {total_time:.2f}s")
        
        # Cache the messages for this page (in background)
        _cache_media_page('videos', creator_url, page, messages_to_cache)
    
    # Send navigation message
    nav_text = f"""
🎬 Video Library 🎬

Showing {start_idx + 1}-{min(end_idx, len(video_links))} of {len(video_links)} videos
Page {page + 1} of {total_pages}

Tap any link above to stream or download 🔥
    """
    
    reply_markup = create_video_navigation_keyboard(page, total_pages, end_idx, len(video_links))
    await query.message.reply_text(nav_text, reply_markup=reply_markup)

async def handle_video_page(query, session, data: str) -> None:
    """Handle video page navigation."""
    page = int(data.split("_")[2])
    await handle_view_videos(query, session, page)

async def handle_video_skip_menu(query, session, data: str) -> None:
    """Show smart menu to skip to a specific page in one step for videos."""
    current_page = int(data.split("_")[2])
    
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    video_links = session.current_directory.get('video_links', [])
    if not video_links:
        await query.edit_message_text("No video links available.")
        return
    
    items_per_page = 10
    total_pages = (len(video_links) + items_per_page - 1) // items_per_page
    
    skip_text = f"""
⏩ Quick Jump ⏩

Total: {len(video_links)} videos
Pages: {total_pages} (10 per page)
Current: Page {current_page + 1}

Select the page you want to jump to 👇
    """
    
    keyboard = []
    
    # Smart pagination based on total pages
    if total_pages <= 25:
        # If 25 or fewer pages, show all (5 per row)
        for i in range(0, total_pages, 5):
            row = []
            for j in range(i, min(i + 5, total_pages)):
                # Highlight current page
                if j == current_page:
                    row.append(InlineKeyboardButton(f"• {j + 1} •", callback_data=f"video_goto_{j}"))
                else:
                    row.append(InlineKeyboardButton(f"{j + 1}", callback_data=f"video_goto_{j}"))
            keyboard.append(row)
    
    elif total_pages <= 50:
        # For 26-50 pages: Show first 10, middle section with intervals, last 10
        row = []
        
        # First 10 pages (compacted)
        for i in range(0, min(10, total_pages)):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"video_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"video_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Middle pages with intervals of 5
        if total_pages > 20:
            for i in range(10, total_pages - 10, 5):
                if i == current_page:
                    row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"video_goto_{i}"))
                else:
                    row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"video_goto_{i}"))
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Last 10 pages
        for i in range(max(10, total_pages - 10), total_pages):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"video_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"video_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    else:
        # For 50+ pages: Show key pages with smart intervals
        pages_to_show = []
        
        # Always show first 5
        pages_to_show.extend(range(0, min(5, total_pages)))
        
        # Show pages around current page
        if current_page >= 5:
            start = max(5, current_page - 2)
            end = min(total_pages - 5, current_page + 3)
            pages_to_show.extend(range(start, end))
        
        # Show every 10th page in the middle
        for i in range(10, total_pages - 10, 10):
            if i not in pages_to_show:
                pages_to_show.append(i)
        
        # Always show last 5
        pages_to_show.extend(range(max(5, total_pages - 5), total_pages))
        
        # Remove duplicates and sort
        pages_to_show = sorted(set(pages_to_show))
        
        # Create buttons (4 per row for better fit)
        row = []
        for page_idx in pages_to_show:
            if page_idx == current_page:
                row.append(InlineKeyboardButton(f"• {page_idx + 1} •", callback_data=f"video_goto_{page_idx}"))
            else:
                row.append(InlineKeyboardButton(f"{page_idx + 1}", callback_data=f"video_goto_{page_idx}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"video_cancel_{current_page}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(skip_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_video_cancel(query, session, data: str) -> None:
    """Cancel video skip and return to navigation without resending videos."""
    current_page = int(data.split("_")[2])
    await show_videos_navigation(query, session, current_page)

async def show_videos_navigation(query, session, page: int) -> None:
    """Show only the navigation menu without re-sending videos."""
    if not session.current_directory:
        await query.edit_message_text("No content directory available.")
        return
    
    video_links = session.current_directory.get('video_links', [])
    if not video_links:
        await query.edit_message_text("No video links available.")
        return
    
    items_per_page = 10
    total_pages = (len(video_links) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(video_links))
    
    # Just show navigation message
    nav_text = f"""
🎬 Video Library 🎬

Showing {start_idx + 1}-{end_idx} of {len(video_links)} videos
Page {page + 1} of {total_pages}

Use the navigation buttons below 👇
    """
    
    reply_markup = create_video_navigation_keyboard(page, total_pages, end_idx, len(video_links))
    await query.edit_message_text(nav_text, reply_markup=reply_markup)

async def handle_video_goto(query, session, data: str) -> None:
    """Go to specific video page."""
    page = int(data.split("_")[2])
    await handle_view_videos(query, session, page)

async def handle_view_of_feed(query, session, bot_instance, page: int = 0) -> None:
    """Show OnlyFans feed posts from Coomer API."""
    if not session.current_directory:
        await query.edit_message_text("⚠️ Server issue - please try again.")
        return
    
    # Extract OnlyFans username from social links
    social_links = session.current_directory.get('social_links', {})
    onlyfans_link = social_links.get('onlyfans')
    
    if not onlyfans_link:
        await query.edit_message_text(
            "❌ No OnlyFans link found for this creator.\n\n"
            "The archived feed feature requires an OnlyFans profile link to be available."
        )
        return
    
    # Extract username from OnlyFans URL
    import re
    username_match = re.search(r'onlyfans\.com/([^/?]+)', onlyfans_link)
    if not username_match:
        await query.edit_message_text("⚠️ Invalid link - please check and try again.")
        return
    
    username = username_match.group(1)
    
    # Check cache first (using database)
    cached_posts = bot_instance.cache_manager.get_onlyfans_posts(username, max_age_hours=24)
    
    if cached_posts:
        logger.info(f"✓ OnlyFans feed cache hit for {username}")
        posts = cached_posts
        
        # Update message to show it's from cache
        await query.edit_message_text(f"✓ Loaded archived Onlyfans Feed for @{username} (cached)")
    else:
        # Show loading message
        await query.edit_message_text(f"⏳ Loading archived Onlyfans Feed for @{username}...")
        
        try:
            # Fetch posts from Coomer API
            import httpx
            import json
            import asyncio
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(1)
            
            api_url = f"https://coomer.st/api/v1/onlyfans/user/{username}/posts"
            
            # Add headers and cookies to mimic a browser request and bypass DDoS-Guard
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0',
                'Accept': 'text/css',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Referer': f'https://coomer.st/onlyfans/user/{username}',
                'Sec-GPC': '1',
                'Connection': 'keep-alive',
                'Cookie': '__ddg8_=oYZ5VQJk5kVaS0OW; __ddg10_=1764498146; __ddg9_=169.150.196.144; __ddg1_=MG8yyPWZPYJxBTqS1VhW; thumbSize=180',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'Priority': 'u=4',
                'TE': 'trailers',
            }
            
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # Try up to 2 times with different delays
                for attempt in range(2):
                    try:
                        logger.info(f"Fetching Onlyfans Feed for {username}, attempt {attempt + 1}")
                        response = await client.get(api_url, headers=headers)
                        logger.info(f"Response status: {response.status_code}")
                        break
                    except (httpx.ConnectError, httpx.ReadTimeout) as e:
                        if attempt < 1:
                            logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                            await asyncio.sleep(2)
                            continue
                        else:
                            raise
                
                if response.status_code == 404:
                    await query.edit_message_text(
                        f"❌ No archived feed found for @{username}.\n\n"
                        "This creator may not be available in the archive database."
                    )
                    return
                
                if response.status_code == 403:
                    # Try alternative approach: provide direct link with hidden link
                    await query.edit_message_text(
                        f"""⚠️ Access Currently Unavailable

The archive database is currently blocking automated requests for @{username}.

[👀 View Feed Manually](https://coomer.st/onlyfans/user/{username})

💡 Note: The link above provides access to all archived posts, photos, and videos from this creator's OnlyFans.""",
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    return
                
                if response.status_code != 200:
                    await query.edit_message_text(
                        f"❌ Failed to fetch Onlyfans Feed (Status: {response.status_code}).\n\n"
                        "Please try again later."
                    )
                    return
                
                posts = response.json()
                
                # Cache the posts in database
                bot_instance.cache_manager.save_onlyfans_posts(username, posts)
                logger.info(f"✓ Cached OnlyFans feed for {username} in database")
                
                # Also save to coomer.json for reference
                with open('coomer.json', 'w', encoding='utf-8') as f:
                    json.dump(posts, f, indent=2, ensure_ascii=False)
            
            if not posts or len(posts) == 0:
                await query.edit_message_text(
                    f"📭 No archived posts found for @{username}.\n\n"
                    "The feed may be empty or not yet archived."
                )
                return
        
        except httpx.TimeoutException:
            await query.edit_message_text("⚠️ Server issue - please try again.")
            return
        except Exception as e:
            logger.error(f"Error fetching archived feed: {e}")
            await query.edit_message_text("⚠️ Server issue - please try again.")
            return
    
    # Store posts in session for pagination
    session.of_feed_posts = posts
    session.of_feed_username = username
    
    # Display posts
    await display_of_feed_page(query, session, page)

async def display_of_feed_page(query, session, page: int) -> None:
    """Display a page of Onlyfans Feed posts with clickable links."""
    posts = session.of_feed_posts
    username = session.of_feed_username
    
    items_per_page = 5
    total_pages = (len(posts) + items_per_page - 1) // items_per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(posts))
    page_posts = posts[start_idx:end_idx]
    
    # First, send header message
    from datetime import datetime
    import httpx
    
    header_text = f"\n"
    header_text += f"  📱 OnlyFans Feed 📱  \n"
    header_text += f"\n\n"
    header_text += f"Creator: @{username}\n\n"
    header_text += f"📊 Showing: {start_idx + 1}-{end_idx} of {len(posts)}\n"
    header_text += f"📄 Page: {page + 1} / {total_pages}\n\n"
    header_text += "⏳ Loading media..."
    
    # Edit the message instead of deleting and sending new
    try:
        await query.edit_message_text(header_text, parse_mode='Markdown')
        message = query.message
    except Exception as e:
        logger.warning(f"Could not edit message, sending new one: {e}")
        try:
            await query.delete_message()
        except:
            pass
        message = await query.message.reply_text(header_text, parse_mode='Markdown')
    
    # Headers for fetching post details
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0',
        'Accept': 'text/css',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Sec-GPC': '1',
        'Connection': 'keep-alive',
        'Cookie': '__ddg1_=MG8yyPWZPYJxBTqS1VhW; thumbSize=180; __ddg8_=905mgO0m7doV7p57; __ddg10_=1764511244; __ddg9_=169.150.196.144',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }
    
    # Send each post with actual media
    async def fetch_post_details(idx, post):
        """Fetch and process a single post."""
        try:
            post_id = post.get('id', '')
            
            # Fetch detailed post data to get media URLs
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                post_detail_url = f"https://coomer.st/api/v1/onlyfans/user/{username}/post/{post_id}"
                headers_copy = headers.copy()
                headers_copy['Referer'] = f'https://coomer.st/onlyfans/user/{username}/post/{post_id}'
                
                response = await client.get(post_detail_url, headers=headers_copy)
                
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch post {post_id}: {response.status_code}")
                    return None
                
                post_detail = response.json()
                post_data = post_detail.get('post', {})
                
                # Parse date
                published = post_data.get('published', '')
                try:
                    post_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    date_str = post_date.strftime('%B %d, %Y')
                except:
                    date_str = 'Unknown date'
                
                # Get title or content
                title = post_data.get('title', '').strip()
                content = post_data.get('content', '').strip()
                
                # Escape markdown special characters
                def escape_text(text):
                    for char in ['_', '', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
                        text = text.replace(char, '')
                    return text
                
                caption = f"Post #{idx + 1} - {date_str}"
                if title:
                    caption += f"\n{escape_text(title)}"
                elif content:
                    if len(content) > 200:
                        content = content[:197] + '...'
                    caption += f"\n{escape_text(content)}"
                
                # Get main file
                file_info = post_data.get('file', {})
                
                # Get attachments
                attachments_list = post_detail.get('attachments', [])
                
                # Get videos
                videos_list = post_detail.get('videos', [])
                
                # Collect all media URLs
                media_items = []
                
                # Add main file if exists
                if file_info and file_info.get('path'):
                    file_url = f"https://img.coomer.st/thumbnail/data{file_info['path']}"
                    file_name = file_info.get('name', '')
                    
                    if any(file_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        media_items.append(('photo', file_url))
                    elif any(file_name.lower().endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm']):
                        file_url = f"https://coomer.st/data{file_info['path']}"
                        media_items.append(('video', file_url))
                
                # Add videos
                for video in videos_list:
                    if video.get('path'):
                        video_url = f"https://coomer.st/data{video['path']}"
                        media_items.append(('video', video_url))
                
                # Add attachments
                for attachment in attachments_list:
                    if attachment.get('path'):
                        attach_name = attachment.get('name', '')
                        
                        if any(attach_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                            attach_url = f"https://img.coomer.st/thumbnail/data{attachment['path']}"
                            media_items.append(('photo', attach_url))
                        elif any(attach_name.lower().endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm']):
                            attach_url = f"https://coomer.st/data{attachment['path']}"
                            media_items.append(('video', attach_url))
                
                result = (caption, media_items)
                
                return result
        
        except Exception as e:
            logger.error(f"Error processing Onlyfans Feed post {idx + 1}: {e}")
            return None
    
    # Fetch all post details concurrently (in batches to avoid overwhelming)
    batch_size = 5  # Increased from 3 to 5 for faster processing
    all_post_data = []
    
    for batch_start in range(0, len(page_posts), batch_size):
        batch_end = min(batch_start + batch_size, len(page_posts))
        batch_posts = page_posts[batch_start:batch_end]
        
        # Create tasks for this batch
        tasks = [
            fetch_post_details(start_idx + batch_start + i, post)
            for i, post in enumerate(batch_posts)
        ]
        
        # Fetch batch concurrently
        batch_results = await asyncio.gather(*tasks)
        all_post_data.extend(batch_results)
        
        # Reduced delay between batches from 0.5s to 0.2s
        if batch_end < len(page_posts):
            await asyncio.sleep(0.2)
    
    # Send media to Telegram - OPTIMIZED WITH BATCH LANDING PAGE GENERATION
    
    # Prepare batch items for all media
    batch_items = []
    media_metadata = []  # Store caption and type info for later formatting
    
    for post_idx, post_data in enumerate(all_post_data):
        if not post_data:
            continue
            
        caption, media_items = post_data
        
        if media_items:
            for media_idx, (media_type, media_url) in enumerate(media_items):
                # Extract post number from caption if available
                post_match = re.search(r'Post #(\d+)', caption) if caption else None
                post_num = post_match.group(1) if post_match else str(post_idx + 1)
                
                content_title = f"OnlyFans Post #{post_num}"
                content_type = "🖼️ Photo" if media_type == 'photo' else "🎬 Video"
                
                batch_items.append({
                    'creator_name': username,
                    'content_title': content_title,
                    'content_type': content_type,
                    'original_url': media_url,
                    'preview_url': media_url if media_type == 'photo' else None,
                    'thumbnail_url': media_url if media_type == 'photo' else None,
                    'expires_hours': 24
                })
                
                # Store metadata for message formatting (only include caption for first media)
                media_metadata.append({
                    'caption': caption if media_idx == 0 else None,
                    'media_type': media_type,
                    'media_url': media_url
                })
        else:
            # Text-only post metadata
            media_metadata.append({
                'caption': caption,
                'media_type': 'text',
                'media_url': None
            })
    
    # Generate all landing URLs in one batch request
    try:
        logger.info(f"📤 Sending batch request to FastAPI for {len(batch_items)} OnlyFans media items")
        landing_urls = await landing_service.generate_batch_landing_urls_async(batch_items)
        logger.info(f"✅ Received {len(landing_urls)} landing URLs for OnlyFans feed")
    except Exception as e:
        logger.error(f"❌ Batch request failed for OnlyFans feed: {e}")
        # Fallback: show error message
        await message.reply_text(
            "❌ Failed to generate landing pages for media.\n\n"
            "Please try again later."
        )
        return
    
    # Create message data from batch results
    message_data_list = []
    landing_url_idx = 0
    
    for metadata in media_metadata:
        if metadata['media_type'] == 'text':
            # Text-only post
            message_data_list.append({
                'text': f"{metadata['caption']}\n\n💬 Text-only post",
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            })
        else:
            # Media post with landing URL
            landing_url = landing_urls[landing_url_idx]
            landing_url_idx += 1
            
            media_label = "Image Post" if metadata['media_type'] == 'photo' else "Video Post"
            media_icon = "🖼️" if metadata['media_type'] == 'photo' else "🎬"
            
            if metadata['caption']:
                message_text = f"""{metadata['caption']}

{media_icon} {media_label}
[👀 View Content]({landing_url})
"""
            else:
                message_text = f"""{media_icon} {media_label}
[👀 View Content]({landing_url})
"""
            
            message_data_list.append({
                'text': message_text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            })
    
    # Create message tasks from generated data
    message_tasks = []
    for msg_data in message_data_list:
        if isinstance(msg_data, dict):
            message_tasks.append(
                message.reply_text(
                    msg_data['text'],
                    parse_mode=msg_data.get('parse_mode', 'Markdown'),
                    disable_web_page_preview=msg_data.get('disable_web_page_preview', False)
                )
            )
    
    # Send all messages concurrently in batches to avoid Telegram rate limits
    batch_size = 10
    for i in range(0, len(message_tasks), batch_size):
        batch = message_tasks[i:i+batch_size]
        try:
            await asyncio.gather(*batch, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error sending message batch: {e}")
        
        # Delay between batches to allow Telegram to fetch preview
        if i + batch_size < len(message_tasks):
            await asyncio.sleep(0.5)  # 500ms delay for preview loading
        else:
            await asyncio.sleep(0.3)  # 300ms delay after last batch
    
    # Send navigation message at the end
    nav_text = f"\n� Page {page + 1} of {total_pages}\n\nUse the buttons below to navigate:"
    
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"of_feed_page_{page - 1}"))
    
    # Add skip/jump button if more than 3 pages
    if total_pages > 3:
        nav_buttons.append(InlineKeyboardButton("⏩ Jump to Page", callback_data=f"of_feed_skip_{page}"))
    
    if end_idx < len(posts):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"of_feed_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(nav_text, reply_markup=reply_markup)

async def handle_of_feed_page(query, session, data: str, bot_instance) -> None:
    """Handle Onlyfans Feed page navigation."""
    page = int(data.split("_")[3])
    
    if not hasattr(session, 'of_feed_posts') or not session.of_feed_posts:
        await query.edit_message_text("⚠️ Please reload the feed.")
        return
    
    await display_of_feed_page(query, session, page)

async def handle_of_feed_skip_menu(query, session, data: str) -> None:
    """Show smart menu to skip to a specific page in Onlyfans Feed."""
    current_page = int(data.split("_")[3])
    
    if not hasattr(session, 'of_feed_posts') or not session.of_feed_posts:
        await query.edit_message_text("⚠️ Please reload the feed.")
        return
    
    posts = session.of_feed_posts
    username = session.of_feed_username
    items_per_page = 5
    total_pages = (len(posts) + items_per_page - 1) // items_per_page
    
    skip_text = f"""

  ⏩ Quick Jump ⏩  

📊 Total: {len(posts)} posts
📄 Pages: {total_pages} (5 per page)
📍 Current: Page {current_page + 1}

Select page to jump to
    """
    
    keyboard = []
    
    # Smart pagination based on total pages
    if total_pages <= 25:
        # If 25 or fewer pages, show all (5 per row)
        for i in range(0, total_pages, 5):
            row = []
            for j in range(i, min(i + 5, total_pages)):
                # Highlight current page
                if j == current_page:
                    row.append(InlineKeyboardButton(f"• {j + 1} •", callback_data=f"of_feed_goto_{j}"))
                else:
                    row.append(InlineKeyboardButton(f"{j + 1}", callback_data=f"of_feed_goto_{j}"))
            keyboard.append(row)
    
    elif total_pages <= 50:
        # For 26-50 pages: Show first 10, middle section with intervals, last 10
        row = []
        
        # First 10 pages (compacted)
        for i in range(0, min(10, total_pages)):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"of_feed_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"of_feed_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Middle pages with intervals of 5
        if total_pages > 20:
            for i in range(10, total_pages - 10, 5):
                if i == current_page:
                    row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"of_feed_goto_{i}"))
                else:
                    row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"of_feed_goto_{i}"))
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
        
        if row:
            keyboard.append(row)
            row = []
        
        # Last 10 pages
        for i in range(max(10, total_pages - 10), total_pages):
            if i == current_page:
                row.append(InlineKeyboardButton(f"• {i + 1} •", callback_data=f"of_feed_goto_{i}"))
            else:
                row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"of_feed_goto_{i}"))
            if len(row) == 5:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    else:
        # For 50+ pages: Show key pages with smart intervals
        pages_to_show = []
        
        # Always show first 5
        pages_to_show.extend(range(0, min(5, total_pages)))
        
        # Show pages around current page
        if current_page >= 5:
            start = max(5, current_page - 2)
            end = min(total_pages - 5, current_page + 3)
            pages_to_show.extend(range(start, end))
        
        # Show every 10th page in the middle
        for i in range(10, total_pages - 10, 10):
            if i not in pages_to_show:
                pages_to_show.append(i)
        
        # Always show last 5
        pages_to_show.extend(range(max(5, total_pages - 5), total_pages))
        
        # Remove duplicates and sort
        pages_to_show = sorted(set(pages_to_show))
        
        # Create buttons (4 per row for better fit)
        row = []
        for page_idx in pages_to_show:
            if page_idx == current_page:
                row.append(InlineKeyboardButton(f"• {page_idx + 1} •", callback_data=f"of_feed_goto_{page_idx}"))
            else:
                row.append(InlineKeyboardButton(f"{page_idx + 1}", callback_data=f"of_feed_goto_{page_idx}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"of_feed_cancel_{current_page}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(skip_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_of_feed_goto(query, session, data: str, bot_instance) -> None:
    """Go to specific Onlyfans Feed page."""
    page = int(data.split("_")[3])
    await display_of_feed_page(query, session, page)

async def handle_of_feed_cancel(query, session, data: str) -> None:
    """Cancel Onlyfans Feed skip and return to navigation."""
    current_page = int(data.split("_")[3])
    await show_of_feed_navigation(query, session, current_page)

async def show_of_feed_navigation(query, session, page: int) -> None:
    """Show only the navigation menu for Onlyfans Feed without re-sending posts."""
    if not hasattr(session, 'of_feed_posts') or not session.of_feed_posts:
        await query.edit_message_text("⚠️ Please reload the feed.")
        return
    
    posts = session.of_feed_posts
    items_per_page = 5
    total_pages = (len(posts) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(posts))
    
    # Just show navigation message
    nav_text = f"\n📄 Page {page + 1} of {total_pages}\n\nUse the buttons below to navigate:"
    
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"of_feed_page_{page - 1}"))
    
    if total_pages > 3:
        nav_buttons.append(InlineKeyboardButton("⏩ Jump to Page", callback_data=f"of_feed_skip_{page}"))
    
    if end_idx < len(posts):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"of_feed_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(nav_text, reply_markup=reply_markup)

