"""
UI Components - Keyboard creation and display formatting
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


def create_content_keyboard(items: list, page: int = 0, items_per_page: int = 5) -> list:
    """Create keyboard for content items with pagination."""
    keyboard = []
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = items[start_idx:end_idx]
    
    for idx, item in enumerate(page_items, start=start_idx):
        # Use title directly - it already contains description or meaningful name
        title = item.get('title', f'Item {idx + 1}')
        
        # Truncate title if too long for button
        if len(title) > 50:
            title = title[:47] + '...'
        
        button_text = f"{item.get('type', '📄')} {title}"
        callback_data = f"content_{idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add pagination controls
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page - 1}"))
    if end_idx < len(items):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return keyboard


def create_filters_menu_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for filters configuration menu."""
    keyboard = [
        [InlineKeyboardButton("📁 Content Type", callback_data="filter_content_type")],
        [InlineKeyboardButton("📅 Date Range", callback_data="filter_date_range")],
        [InlineKeyboardButton("🎬 Quality", callback_data="filter_quality")],
        [InlineKeyboardButton("🔄 Reset All", callback_data="filter_reset")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_search")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_filter_selection_keyboard(filter_type: str) -> tuple:
    """Create keyboard for specific filter selection."""
    if filter_type == "content_type":
        keyboard = [
            [InlineKeyboardButton("📷 Photos Only", callback_data="set_filter_content_type_photos")],
            [InlineKeyboardButton("🎬 Videos Only", callback_data="set_filter_content_type_videos")],
            [InlineKeyboardButton("📁 All Content", callback_data="set_filter_content_type_all")],
            [InlineKeyboardButton("⬅️ Back", callback_data="set_filters")]
        ]
        text = "📁 Select Content Type:"
    
    elif filter_type == "date_range":
        keyboard = [
            [InlineKeyboardButton("🆕 Recent (24h)", callback_data="set_filter_date_range_recent")],
            [InlineKeyboardButton("📅 This Week", callback_data="set_filter_date_range_week")],
            [InlineKeyboardButton("🗓️ This Month", callback_data="set_filter_date_range_month")],
            [InlineKeyboardButton("🕰️ All Time", callback_data="set_filter_date_range_all")],
            [InlineKeyboardButton("⬅️ Back", callback_data="set_filters")]
        ]
        text = "📅 Select Date Range:"
    
    elif filter_type == "quality":
        keyboard = [
            [InlineKeyboardButton("🎬 HD Quality", callback_data="set_filter_quality_hd")],
            [InlineKeyboardButton("📺 Standard", callback_data="set_filter_quality_standard")],
            [InlineKeyboardButton("🤷 Any Quality", callback_data="set_filter_quality_any")],
            [InlineKeyboardButton("⬅️ Back", callback_data="set_filters")]
        ]
        text = "🎬 Select Quality:"
    
    else:
        return None, None
    
    return InlineKeyboardMarkup(keyboard), text


def format_directory_text(creator_name: str, content_directory: dict, filters: dict) -> str:
    """Format content directory display text."""
    total_items = len(content_directory.get('items', []))
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    
    return f"""
📁 Content Directory for: {creator_name}
📊 Total Items: {total_items}
🖼️ Preview Pictures: {total_pictures}
🎬 Videos: {total_videos}
📅 Last Updated: {content_directory.get('last_updated', 'Unknown')}

Browse content below:
    """


def format_content_details_text(item: dict, content_idx: int) -> str:
    """Format content item details text."""
    title = item.get('title', 'Untitled')
    
    return f"""
📄 Content Details

📝 {title}

📁 Type: {item.get('type', 'Unknown')}
🌐 Domain: {item.get('domain', 'Unknown')}
🔗 URL: {item.get('url', 'N/A')[:100]}
    """


def format_filter_settings_text(filters: dict) -> str:
    """Format filters configuration text."""
    return f"""
⚙️ Content Filters

Current Settings:
• Content Type: {filters.get('content_type', 'All')}
• Date Range: {filters.get('date_range', 'All Time')}
• Quality: {filters.get('quality', 'Any')}

Select a filter to modify:
    """


def create_welcome_keyboard() -> InlineKeyboardMarkup:
    """Create welcome screen keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔍 Search Creator", callback_data="search_creator")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_content_details_keyboard(content_idx: int) -> InlineKeyboardMarkup:
    """Create keyboard for content details."""
    keyboard = [
        [InlineKeyboardButton("🔗 Get Download Link", callback_data=f"download_{content_idx}")],
        [InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{content_idx}")],
        [InlineKeyboardButton("⬅️ Back to List", callback_data="back_to_list")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_picture_navigation_keyboard(page: int, total_pages: int, end_idx: int, total_images: int) -> InlineKeyboardMarkup:
    """Create keyboard for picture navigation."""
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous 10", callback_data=f"picture_page_{page - 1}"))
    if end_idx < total_images:
        nav_buttons.append(InlineKeyboardButton("Next 10 ➡️", callback_data=f"picture_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Add skip to page button if there are more than 1 page
    if total_pages > 1:
        keyboard.append([InlineKeyboardButton(f"⏩ Skip to Page...", callback_data=f"picture_skip_{page}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_list")])
    
    return InlineKeyboardMarkup(keyboard)


def create_video_navigation_keyboard(page: int, total_pages: int, end_idx: int, total_videos: int) -> InlineKeyboardMarkup:
    """Create keyboard for video navigation."""
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous 10", callback_data=f"video_page_{page - 1}"))
    if end_idx < total_videos:
        nav_buttons.append(InlineKeyboardButton("Next 10 ➡️", callback_data=f"video_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Add skip to page button if there are more than 1 page
    if total_pages > 1:
        keyboard.append([InlineKeyboardButton(f"⏩ Skip to Page...", callback_data=f"video_skip_{page}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_list")])
    
    return InlineKeyboardMarkup(keyboard)
