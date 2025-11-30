"""
Callback Handlers - Handles all callback queries from inline keyboards
"""

import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest
from bot.utilities import send_message_with_retry
from bot.ui_components import (
    create_filters_menu_keyboard, create_filter_selection_keyboard,
    format_filter_settings_text, format_content_details_text,
    create_content_details_keyboard, format_directory_text,
    create_content_keyboard, create_picture_navigation_keyboard,
    create_video_navigation_keyboard
)

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Escape special characters for Markdown v2."""
    # Characters that need to be escaped in Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> None:
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if user_id not in bot_instance.user_sessions:
        from user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    session = bot_instance.user_sessions[user_id]
    
    # Route to appropriate handler
    if data == "search_creator":
        await handle_search_creator(query)
    elif data.startswith("confirm_search|"):
        await handle_confirm_search(query, session, data, bot_instance)
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


async def handle_search_creator(query) -> None:
    """Handle search creator callback."""
    await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")


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
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await send_message_with_retry(
            query.message.reply_text,
            directory_text,
            reply_markup=reply_markup
        )
    except (TimedOut, NetworkError) as e:
        logger.error(f"Failed to display content directory from callback: {e}")


async def handle_set_filters(query, session) -> None:
    """Show the filters configuration menu."""
    filter_text = format_filter_settings_text(session.filters)
    reply_markup = create_filters_menu_keyboard()
    await query.edit_message_text(filter_text, reply_markup=reply_markup)


async def handle_content_details(query, session, data: str) -> None:
    """Show detailed information about a specific content item."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("❌ Content not found.")
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
    """Handle download link request for content."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("❌ Content not found.")
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
            
            link_text = f"""
🔗 Download Link Generated

📄 Content: {title}
🎬 Type: {item.get('type', 'Unknown')}
🌐 Domain: {item.get('domain', 'Unknown')}

🔗 **Download URL:**
`{download_link}`

⚠️ **Important:**
• Right-click → Save As to download
• Some links may require opening in browser

💡 **Tip:** Copy the link above to access the content.
            """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Generate New Link", callback_data=f"download_{content_idx}")],
                [InlineKeyboardButton("⬅️ Back to Details", callback_data=f"content_{content_idx}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(link_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Failed to generate download link. Please try again later.")
            
    except Exception as e:
        logger.error(f"Error generating download link: {e}")
        await query.edit_message_text("❌ An error occurred while generating the download link.")


async def handle_preview_request(query, session, data: str, bot_instance) -> None:
    """Handle preview request for content."""
    content_idx = int(data.split("_")[1])
    
    if not session.current_directory or content_idx >= len(session.current_directory['items']):
        await query.edit_message_text("❌ Content not found.")
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

🖼️ **Preview URL:**
`{preview_info.get('preview_url', 'Not available')}`

📷 **Thumbnail:**
`{preview_info.get('thumbnail_url', 'Not available')}`

💡 **Note:** These are placeholder preview URLs. In the final version, you'll see actual previews.
            """
            
            keyboard = [
                [InlineKeyboardButton("🔗 Get Download Link", callback_data=f"download_{content_idx}")],
                [InlineKeyboardButton("⬅️ Back to Details", callback_data=f"content_{content_idx}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(preview_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Preview not available for this content.")
            
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        await query.edit_message_text("❌ An error occurred while generating the preview.")


async def handle_back_to_list(query, session) -> None:
    """Return to the content list view."""
    if not session.current_directory:
        await query.edit_message_text("❌ No content directory available.")
        return
    
    creator_name = session.current_creator
    content_directory = session.current_directory
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    
    directory_text = format_directory_text(creator_name, content_directory, session.filters)
    
    # Create keyboard with only Pictures and Videos buttons (no content items)
    keyboard = []
    
    if total_pictures > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
    
    if total_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 View Videos ({total_videos})", callback_data="view_videos")])
    
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(directory_text, reply_markup=reply_markup)


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
    
    await query.edit_message_text(f"Loading pictures {start_idx + 1}-{min(end_idx, len(preview_images))}...")
    
    # Send each image with link preview
    for idx, item in enumerate(page_items, start=start_idx):
        image_url = item.get('url', '')
        domain = item.get('domain', 'Unknown')
        
        message_text = f"""
🖼️ **Picture #{idx + 1}**
📦 Domain: {domain}

🔗 Click link below to view full image:
{image_url}

💡 Tip: Telegram shows a preview thumbnail. Click to open the full image.
        """
        
        try:
            await send_message_with_retry(
                query.message.reply_text,
                message_text,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
        except Exception as e:
            logger.error(f"Failed to send image link {idx + 1}: {e}")
    
    # Send navigation message
    nav_text = f"""
📷 Showing pictures {start_idx + 1}-{min(end_idx, len(preview_images))} of {len(preview_images)}
📄 Page {page + 1} of {total_pages}

💡 Tip: Each image shows a preview thumbnail. Click the link to view full size.

Use the buttons below to navigate:
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
⏩ **Jump to Page**

📊 Total: {len(preview_images)} pictures
📄 Pages: {total_pages} (10 pictures per page)
📍 Currently on: Page {current_page + 1}

Select a page to jump to:
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
📷 Showing pictures {start_idx + 1}-{end_idx} of {len(preview_images)}
📄 Page {page + 1} of {total_pages}

💡 Tip: Each image shows a preview thumbnail. Click the link to view full size.

Use the buttons below to navigate:
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
        await query.edit_message_text("❌ No content directory available.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if picture_idx >= len(preview_images):
        await query.edit_message_text("❌ Picture not found.")
        return
    
    picture = preview_images[picture_idx]
    
    details_text = f"""
🖼️ Picture #{picture_idx + 1}

🌐 Domain: {picture.get('domain', 'Unknown')}
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
    """Show picture direct link."""
    picture_idx = int(data.split("_")[2])
    
    if not session.current_directory:
        await query.edit_message_text("❌ No content directory available.")
        return
    
    preview_images = session.current_directory.get('preview_images', [])
    if picture_idx >= len(preview_images):
        await query.edit_message_text("❌ Picture not found.")
        return
    
    picture = preview_images[picture_idx]
    image_url = picture.get('url', '')
    
    link_text = f"""
🖼️ Picture #{picture_idx + 1}

🔗 **Image URL:**
`{image_url}`

💡 **Tip:** Copy the link above or right-click → Open in new tab to view the image.
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
    
    await query.edit_message_text(f"Loading videos {start_idx + 1}-{min(end_idx, len(video_links))}...")
    
    # Send each video link with title
    for idx, item in enumerate(page_items, start=start_idx):
        video_url = item.get('url', '')
        title = item.get('title', f'Video #{idx + 1}')
        domain = item.get('domain', 'Unknown')
        
        message_text = f"""🎬 {title}

📦 Domain: {domain}
🔗 Link: {video_url}

💡 Click the link above to view or download the video."""
        
        try:
            await send_message_with_retry(
                query.message.reply_text,
                message_text,
                disable_web_page_preview=False
            )
        except Exception as e:
            logger.error(f"Failed to send video link {idx + 1}: {e}")
    
    # Send navigation message
    nav_text = f"""
🎬 Showing videos {start_idx + 1}-{min(end_idx, len(video_links))} of {len(video_links)}
📄 Page {page + 1} of {total_pages}

Use the buttons below to navigate:
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
⏩ **Jump to Page**

📊 Total: {len(video_links)} videos
📄 Pages: {total_pages} (10 videos per page)
📍 Currently on: Page {current_page + 1}

Select a page to jump to:
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
🎬 Showing videos {start_idx + 1}-{end_idx} of {len(video_links)}
📄 Page {page + 1} of {total_pages}

Use the buttons below to navigate:
    """
    
    reply_markup = create_video_navigation_keyboard(page, total_pages, end_idx, len(video_links))
    await query.edit_message_text(nav_text, reply_markup=reply_markup)


async def handle_video_goto(query, session, data: str) -> None:
    """Go to specific video page."""
    page = int(data.split("_")[2])
    await handle_view_videos(query, session, page)
