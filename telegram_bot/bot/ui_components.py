"""
UI Components - Keyboard creation and display formatting
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict

def create_content_directory_keyboard(total_pictures: int, total_videos: int, 
                                      has_onlyfans: bool, has_more_pages: bool) -> InlineKeyboardMarkup:
    """Create modern grid-based keyboard for content directory."""
    keyboard = []
    
    # Media buttons in grid layout (2 per row)
    media_row = []
    if total_pictures > 0:
        media_row.append(InlineKeyboardButton(f"🖼️ Photos ({total_pictures})", callback_data="view_pictures"))
    
    if total_videos > 0:
        media_row.append(InlineKeyboardButton(f"🎬 Videos ({total_videos})", callback_data="view_videos"))
    
    if media_row:
        # Split into rows of 2
        if len(media_row) == 2:
            keyboard.append(media_row)
        else:
            keyboard.append([media_row[0]])
    
    # OnlyFans Feed button (full width)
    if has_onlyfans:
        keyboard.append([InlineKeyboardButton("📱 OnlyFans Feed", callback_data="view_of_feed")])
    
    # Load More button (full width)
    if has_more_pages:
        keyboard.append([InlineKeyboardButton("⬇️ Load More", callback_data="load_more_pages")])
    
    # New Search button (full width)
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
    
    return InlineKeyboardMarkup(keyboard)

def create_content_keyboard(items: list, page: int = 0, items_per_page: int = 5) -> list:
    """Create modern keyboard for content items with grid layout and pagination."""
    keyboard = []
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = items[start_idx:end_idx]
    
    for idx, item in enumerate(page_items, start=start_idx):
        title = item.get('title', f'Item {idx + 1}')
        
        # Clean title to prevent entity parsing errors
        clean_title = _clean_text_for_telegram(title)
        
        # Truncate title if too long for button
        if len(clean_title) > 45:
            clean_title = clean_title[:42] + '...'
        
        button_text = f"{item.get('type', '📄')} {clean_title}"
        callback_data = f"content_{idx}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Modern pagination controls with page indicator
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"page_{page - 1}"))
    
    # Page indicator
    nav_buttons.append(InlineKeyboardButton(f"• {page + 1}/{total_pages} •", callback_data="current_page"))
    
    if end_idx < len(items):
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return keyboard

def create_filters_menu_keyboard() -> InlineKeyboardMarkup:
    """Create modern grid-based keyboard for filters configuration."""
    keyboard = [
        [
            InlineKeyboardButton("📁 Type", callback_data="filter_content_type"),
            InlineKeyboardButton("📅 Date", callback_data="filter_date_range")
        ],
        [
            InlineKeyboardButton("🎬 Quality", callback_data="filter_quality"),
            InlineKeyboardButton("🔄 Reset", callback_data="filter_reset")
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="back_to_search")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_filter_selection_keyboard(filter_type: str) -> tuple:
    """Create modern keyboard for specific filter selection with grid layout."""
    if filter_type == "content_type":
        keyboard = [
            [
                InlineKeyboardButton("📷 Photos", callback_data="set_filter_content_type_photos"),
                InlineKeyboardButton("🎬 Videos", callback_data="set_filter_content_type_videos")
            ],
            [InlineKeyboardButton("📁 All Content", callback_data="set_filter_content_type_all")],
            [InlineKeyboardButton("◀️ Back", callback_data="set_filters")]
        ]
        text = "📁 Select Content Type"
    
    elif filter_type == "date_range":
        keyboard = [
            [
                InlineKeyboardButton("🆕 24h", callback_data="set_filter_date_range_recent"),
                InlineKeyboardButton("📅 Week", callback_data="set_filter_date_range_week")
            ],
            [
                InlineKeyboardButton("🗓️ Month", callback_data="set_filter_date_range_month"),
                InlineKeyboardButton("🕰️ All", callback_data="set_filter_date_range_all")
            ],
            [InlineKeyboardButton("◀️ Back", callback_data="set_filters")]
        ]
        text = "📅 Select Date Range"
    
    elif filter_type == "quality":
        keyboard = [
            [
                InlineKeyboardButton("✨ HD", callback_data="set_filter_quality_hd"),
                InlineKeyboardButton("📺 SD", callback_data="set_filter_quality_standard")
            ],
            [InlineKeyboardButton("🎯 Any", callback_data="set_filter_quality_any")],
            [InlineKeyboardButton("◀️ Back", callback_data="set_filters")]
        ]
        text = "🎬 Select Quality"
    
    else:
        return None, None
    
    return InlineKeyboardMarkup(keyboard), text

def format_directory_text(creator_name: str, content_directory: dict, filters: dict) -> str:
    """Format content directory display text."""
    total_items = len(content_directory.get('items', []))
    total_pictures = len(content_directory.get('preview_images', []))
    total_videos = len(content_directory.get('video_links', []))
    pages_scraped = content_directory.get('pages_scraped', 0)
    total_pages = content_directory.get('total_pages', 0)
    has_more = content_directory.get('has_more_pages', False)
    social_links = content_directory.get('social_links', {})
    
    # Clean creator name to prevent entity parsing errors
    clean_creator_name = _clean_text_for_telegram(creator_name)
    
    # Build social links section
    social_info = ""
    if social_links.get('onlyfans') or social_links.get('instagram'):
        social_info = "\n\n\n📱 Social Links\n"
        if social_links.get('onlyfans'):
            of_link = social_links['onlyfans']
            social_info += f"  🔗 OnlyFans: {of_link}\n"
        if social_links.get('instagram'):
            ig_link = social_links['instagram']
            social_info += f"  📸 Instagram: {ig_link}\n"
    
    # Content availability badge
    more_badge = ""
    if has_more:
        more_badge = "\n✨ More content available"
    
    return f"""

  📂 Content Library  📂  

👤 Creator: {clean_creator_name}{social_info}


  🖼️ Photos: {total_pictures}
  🎬 Videos: {total_videos}

Select an option below to explore
    """


def _clean_text_for_telegram(text: str) -> str:
    """Clean text to prevent Telegram entity parsing errors."""
    if not text:
        return text
    
    import re
    
    # Remove any HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove any control characters that might cause issues
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    return text.strip()

def format_content_details_text(item: dict, content_idx: int) -> str:
    """Format content item details text."""
    title = item.get('title', 'Untitled')
    
    # Clean title to prevent entity parsing errors
    clean_title = _clean_text_for_telegram(title)
    
    # Clean URL to prevent issues
    url = item.get('url', 'N/A')
    clean_url = _clean_text_for_telegram(url[:80]) if url != 'N/A' else 'N/A'
    
    return f"""
🔥 Content Preview 🔥

{clean_title}

📁 Type: {item.get('type', 'Unknown')}
🔗 Source: {clean_url}...

Ready to view or download? Choose below 👇
    """

def format_filter_settings_text(filters: dict) -> str:
    """Format filters configuration text."""
    return f"""
⚙️ Your Preferences ⚙️

Current Settings:

📁 Content Type: {filters.get('content_type', 'All')}
📅 Date Range: {filters.get('date_range', 'All Time')}
🎬 Quality: {filters.get('quality', 'Any')}

Tap any option below to change your filters 👇
    """

def create_welcome_keyboard() -> InlineKeyboardMarkup:
    """Create modern welcome screen keyboard with single search button."""
    keyboard = [
        [InlineKeyboardButton("🔍 Search", callback_data="search_creator")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_content_details_keyboard(content_idx: int) -> InlineKeyboardMarkup:
    """Create modern keyboard for content details with grid layout."""
    keyboard = [
        [
            InlineKeyboardButton("🔗 Download", callback_data=f"download_{content_idx}"),
            InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{content_idx}")
        ],
        [InlineKeyboardButton("◀️ Back to List", callback_data="back_to_list")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_picture_navigation_keyboard(page: int, total_pages: int, end_idx: int, total_images: int) -> InlineKeyboardMarkup:
    """Create modern keyboard for picture navigation with compact layout."""
    keyboard = []
    nav_buttons = []
    
    # Navigation row
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"picture_page_{page - 1}"))
    
    # Page indicator in the middle
    nav_buttons.append(InlineKeyboardButton(f"📷 {page + 1}/{total_pages}", callback_data="current_page"))
    
    if end_idx < total_images:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"picture_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Action buttons row
    action_row = []
    if total_pages > 1:
        action_row.append(InlineKeyboardButton("⏭️ Jump", callback_data=f"picture_skip_{page}"))
    action_row.append(InlineKeyboardButton("◀️ Back", callback_data="back_to_list"))
    
    keyboard.append(action_row)
    
    return InlineKeyboardMarkup(keyboard)

def create_video_navigation_keyboard(page: int, total_pages: int, end_idx: int, total_videos: int) -> InlineKeyboardMarkup:
    """Create modern keyboard for video navigation with compact layout."""
    keyboard = []
    nav_buttons = []
    
    # Navigation row
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"video_page_{page - 1}"))
    
    # Page indicator in the middle
    nav_buttons.append(InlineKeyboardButton(f"🎬 {page + 1}/{total_pages}", callback_data="current_page"))
    
    if end_idx < total_videos:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"video_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Action buttons row
    action_row = []
    if total_pages > 1:
        action_row.append(InlineKeyboardButton("⏭️ Jump", callback_data=f"video_skip_{page}"))
    action_row.append(InlineKeyboardButton("◀️ Back", callback_data="back_to_list"))
    
    keyboard.append(action_row)
    
    return InlineKeyboardMarkup(keyboard)
