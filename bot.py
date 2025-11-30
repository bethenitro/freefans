"""
FreeFans Telegram Bot - Main Bot File
A bot for accessing creator content with filtering capabilities
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError, BadRequest, RetryAfter
from decouple import config
import asyncio
from content_manager import ContentManager
from user_session import UserSession

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FreeFansBot:
    def __init__(self):
        self.content_manager = ContentManager()
        self.user_sessions = {}
    
    async def send_message_with_retry(self, send_func, *args, max_retries=3, **kwargs):
        """Send a message with retry logic for network errors."""
        for attempt in range(max_retries):
            try:
                return await send_func(*args, **kwargs)
            except TimedOut:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Request timed out, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request timed out after {max_retries} attempts")
                    raise
            except NetworkError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Network error: {e}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Network error after {max_retries} attempts: {e}")
                    raise
            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Rate limited, waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
                # Don't count rate limit against retry attempts
                continue
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        self.user_sessions[user_id] = UserSession(user_id)
        
        welcome_text = """
🎉 Welcome to FreeFans Bot! 🎉

I can help you discover content from your favorite creators.

🔍 How to use:
• Send me a creator's name to search for content
• Use filters to narrow down your search
• Browse through organized content directories
• Get direct links to content you want

Type a creator's name to get started!
        """
        
        # Create inline keyboard with quick actions
        keyboard = [
            [InlineKeyboardButton("🔍 Search Creator", callback_data="search_creator")],
            [InlineKeyboardButton("⚙️ Set Filters", callback_data="set_filters")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.send_message_with_retry(
                update.message.reply_text,
                welcome_text,
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

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        help_text = """
📖 FreeFans Bot Help

🔍 Searching for Content:
• Simply type a creator's name
• The bot will search and return organized content

🏷️ Content Filters:
• Content Type: Photos, Videos, All
• Date Range: Recent, This Week, This Month, All Time
• Quality: HD, Standard, Any

📁 Content Directory Structure:
• Content is organized by upload date
• Each item shows preview info
• Click to get direct download link

💡 Commands:
/start - Start the bot
/help - Show this help message
/filters - Set content filters
/clear - Clear search history

Need help? Contact support!
        """
        try:
            await self.send_message_with_retry(update.message.reply_text, help_text)
        except (TimedOut, NetworkError) as e:
            logger.error(f"Failed to send help message: {e}")


    async def handle_creator_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle creator name input and search for content."""
        user_id = update.effective_user.id
        creator_name = update.message.text.strip()
        
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession(user_id)
        
        session = self.user_sessions[user_id]
        
        # Show typing indicator
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        except (TimedOut, NetworkError):
            pass  # Non-critical, continue anyway
        
        # Search for creator content
        try:
            search_message = await self.send_message_with_retry(
                update.message.reply_text,
                f"🔍 Searching for content from '{creator_name}'...\n"
                "This may take a few moments."
            )
        except (TimedOut, NetworkError) as e:
            logger.error(f"Failed to send search message: {e}")
            return
        
        try:
            # Get content directory
            content_directory = await self.content_manager.search_creator_content(creator_name, session.filters)
            
            if not content_directory:
                try:
                    await self.send_message_with_retry(
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
                    await self.send_message_with_retry(
                        search_message.edit_text,
                        confirm_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except (TimedOut, NetworkError):
                    pass
            else:
                # Display content directory immediately
                await self.display_content_directory(update, content_directory, content_directory['creator'])
                try:
                    await search_message.delete()
                except (TimedOut, NetworkError, BadRequest):
                    pass  # Non-critical if deletion fails
            
        except Exception as e:
            logger.error(f"Error searching for creator {creator_name}: {e}")
            try:
                await self.send_message_with_retry(
                    search_message.edit_text,
                    "❌ An error occurred while searching. Please try again later."
                )
            except (TimedOut, NetworkError):
                pass

    async def display_content_directory(self, update: Update, content_directory: dict, creator_name: str) -> None:
        """Display the content directory with navigation."""
        user_id = update.effective_user.id
        session = self.user_sessions[user_id]
        session.current_directory = content_directory
        session.current_creator = creator_name
        
        # Create directory display
        total_items = len(content_directory.get('items', []))
        total_pictures = len(content_directory.get('preview_images', []))
        
        directory_text = f"""
📁 Content Directory for: {creator_name}
📊 Total Items: {total_items}
🖼️ Preview Pictures: {total_pictures}
📅 Last Updated: {content_directory.get('last_updated', 'Unknown')}

🏷️ Active Filters:
• Content Type: {session.filters.get('content_type', 'All')}
• Date Range: {session.filters.get('date_range', 'All Time')}
• Quality: {session.filters.get('quality', 'Any')}

Browse content below:
        """
        
        # Create pagination keyboard
        keyboard = self.create_content_keyboard(content_directory['items'], page=0)
        
        # Add Pictures button if there are preview images
        if total_pictures > 0:
            keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
        
        keyboard.append([InlineKeyboardButton("⚙️ Change Filters", callback_data="set_filters")])
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.send_message_with_retry(
                update.message.reply_text,
                directory_text,
                reply_markup=reply_markup
            )
        except (TimedOut, NetworkError) as e:
            logger.error(f"Failed to display content directory: {e}")
    
    async def display_content_directory_from_callback(self, query, content_directory: dict, creator_name: str) -> None:
        """Display the content directory with navigation from a callback query."""
        user_id = query.from_user.id
        session = self.user_sessions[user_id]
        session.current_directory = content_directory
        session.current_creator = creator_name
        
        # Create directory display
        total_items = len(content_directory.get('items', []))
        total_pictures = len(content_directory.get('preview_images', []))
        
        directory_text = f"""
📁 Content Directory for: {creator_name}
📊 Total Items: {total_items}
🖼️ Preview Pictures: {total_pictures}
📅 Last Updated: {content_directory.get('last_updated', 'Unknown')}

🏷️ Active Filters:
• Content Type: {session.filters.get('content_type', 'All')}
• Date Range: {session.filters.get('date_range', 'All Time')}
• Quality: {session.filters.get('quality', 'Any')}

Browse content below:
        """
        
        # Create pagination keyboard
        keyboard = self.create_content_keyboard(content_directory['items'], page=0)
        
        # Add Pictures button if there are preview images
        if total_pictures > 0:
            keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
        
        keyboard.append([InlineKeyboardButton("⚙️ Change Filters", callback_data="set_filters")])
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Send as new message to the chat
            await self.send_message_with_retry(
                query.message.reply_text,
                directory_text,
                reply_markup=reply_markup
            )
        except (TimedOut, NetworkError) as e:
            logger.error(f"Failed to display content directory from callback: {e}")

    def create_content_keyboard(self, items: list, page: int = 0, items_per_page: int = 5) -> list:
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

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession(user_id)
        
        session = self.user_sessions[user_id]
        
        if data == "search_creator":
            await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")
        
        elif data.startswith("confirm_search|"):
            # Handle confirmation of fuzzy match
            creator_name = data.split("|")[1]
            if session.pending_content:
                await self.display_content_directory_from_callback(
                    query, session.pending_content, creator_name
                )
                try:
                    await query.delete_message()
                except (TimedOut, NetworkError, BadRequest):
                    pass  # Non-critical if deletion fails
                session.pending_content = None
        
        elif data == "set_filters":
            await self.show_filters_menu(query, session)
        
        elif data == "help":
            await self.help_command(update, context)
        
        elif data.startswith("content_"):
            content_idx = int(data.split("_")[1])
            await self.show_content_details(query, session, content_idx)
        
        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            await self.update_content_page(query, session, page)
        
        elif data.startswith("filter_"):
            await self.handle_filter_selection(query, session, data)
        
        elif data.startswith("set_filter_"):
            await self.apply_filter(query, session, data)
        
        elif data.startswith("download_"):
            content_idx = int(data.split("_")[1])
            await self.handle_download_request(query, session, content_idx)
        
        elif data.startswith("preview_"):
            content_idx = int(data.split("_")[1])
            await self.handle_preview_request(query, session, content_idx)
        
        elif data == "back_to_list":
            await self.back_to_content_list(query, session)
        
        elif data == "back_to_search":
            await query.edit_message_text("🔍 Please send me the name of the creator you want to search for:")
        
        elif data == "view_pictures":
            await self.show_pictures_list(query, session)
        
        elif data.startswith("picture_page_"):
            page = int(data.split("_")[2])
            await self.show_pictures_list(query, session, page)
        
        elif data.startswith("picture_skip_"):
            current_page = int(data.split("_")[2])
            await self.show_page_skip_menu(query, session, current_page)
        
        elif data.startswith("picture_goto_"):
            page = int(data.split("_")[2])
            await self.show_pictures_list(query, session, page)
        
        elif data.startswith("picture_"):
            # This must come after other picture_ patterns
            picture_idx = int(data.split("_")[1])
            await self.show_picture_details(query, session, picture_idx)
        
        elif data.startswith("picture_link_"):
            picture_idx = int(data.split("_")[2])
            await self.show_picture_link(query, session, picture_idx)

    async def show_filters_menu(self, query, session: UserSession) -> None:
        """Show the filters configuration menu."""
        filter_text = f"""
⚙️ Content Filters

Current Settings:
• Content Type: {session.filters.get('content_type', 'All')}
• Date Range: {session.filters.get('date_range', 'All Time')}
• Quality: {session.filters.get('quality', 'Any')}

Select a filter to modify:
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 Content Type", callback_data="filter_content_type")],
            [InlineKeyboardButton("📅 Date Range", callback_data="filter_date_range")],
            [InlineKeyboardButton("🎬 Quality", callback_data="filter_quality")],
            [InlineKeyboardButton("🔄 Reset All", callback_data="filter_reset")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_search")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(filter_text, reply_markup=reply_markup)

    async def handle_filter_selection(self, query, session: UserSession, data: str) -> None:
        """Handle filter option selection."""
        filter_type = data.replace("filter_", "")
        
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
        
        elif filter_type == "reset":
            session.reset_filters()
            await query.edit_message_text("✅ Filters have been reset to default values.")
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)

    async def show_content_details(self, query, session: UserSession, content_idx: int) -> None:
        """Show detailed information about a specific content item."""
        if not session.current_directory or content_idx >= len(session.current_directory['items']):
            await query.edit_message_text("❌ Content not found.")
            return
        
        item = session.current_directory['items'][content_idx]
        
        # Use title directly (which already has description or meaningful name)
        title = item.get('title', 'Untitled')
        
        details_text = f"""
📄 Content Details

📝 {title}

📁 Type: {item.get('type', 'Unknown')}
🌐 Domain: {item.get('domain', 'Unknown')}
🔗 URL: {item.get('url', 'N/A')[:100]}
        """
        
        keyboard = [
            [InlineKeyboardButton("🔗 Get Download Link", callback_data=f"download_{content_idx}")],
            [InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{content_idx}")],
            [InlineKeyboardButton("⬅️ Back to List", callback_data="back_to_list")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(details_text, reply_markup=reply_markup)

    async def apply_filter(self, query, session: UserSession, data: str) -> None:
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

    async def handle_download_request(self, query, session: UserSession, content_idx: int) -> None:
        """Handle download link request for content."""
        if not session.current_directory or content_idx >= len(session.current_directory['items']):
            await query.edit_message_text("❌ Content not found.")
            return
        
        item = session.current_directory['items'][content_idx]
        
        # Show loading message
        await query.edit_message_text("🔗 Generating secure download link...\nPlease wait...")
        
        try:
            # Generate download link (placeholder implementation)
            download_link = await self.content_manager.get_content_download_link(
                session.current_creator, content_idx
            )
            
            if download_link:
                session.increment_downloads()
                
                # Use title directly
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

    async def handle_preview_request(self, query, session: UserSession, content_idx: int) -> None:
        """Handle preview request for content."""
        if not session.current_directory or content_idx >= len(session.current_directory['items']):
            await query.edit_message_text("❌ Content not found.")
            return
        
        item = session.current_directory['items'][content_idx]
        
        # Show loading message
        await query.edit_message_text("👁️ Generating preview...\nPlease wait...")
        
        try:
            # Generate preview (placeholder implementation)
            preview_info = await self.content_manager.get_content_preview(
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

    async def back_to_content_list(self, query, session: UserSession) -> None:
        """Return to the content list view."""
        if not session.current_directory:
            await query.edit_message_text("❌ No content directory available.")
            return
        
        # Recreate content directory display
        creator_name = session.current_creator
        content_directory = session.current_directory
        total_items = len(content_directory.get('items', []))
        total_pictures = len(content_directory.get('preview_images', []))
        
        directory_text = f"""
📁 Content Directory for: {creator_name}
📊 Total Items: {total_items}
�️ Preview Pictures: {total_pictures}
�📅 Last Updated: {content_directory.get('last_updated', 'Unknown')}

🏷️ Active Filters:
• Content Type: {session.filters.get('content_type', 'All')}
• Date Range: {session.filters.get('date_range', 'All Time')}
• Quality: {session.filters.get('quality', 'Any')}

Browse content below:
        """
        
        # Create pagination keyboard
        keyboard = self.create_content_keyboard(content_directory['items'], page=session.current_page)
        
        # Add Pictures button if there are preview images
        if total_pictures > 0:
            keyboard.append([InlineKeyboardButton(f"🖼️ View Pictures ({total_pictures})", callback_data="view_pictures")])
        
        keyboard.append([InlineKeyboardButton("⚙️ Change Filters", callback_data="set_filters")])
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_creator")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(directory_text, reply_markup=reply_markup)
    
    async def show_pictures_list(self, query, session: UserSession, page: int = 0) -> None:
        """Show preview pictures as clickable links with thumbnail previews."""
        if not session.current_directory:
            await query.edit_message_text("No content directory available.")
            return
        
        preview_images = session.current_directory.get('preview_images', [])
        if not preview_images:
            await query.edit_message_text("No preview pictures available.")
            return
        
        items_per_page = 10  # Show 10 images at a time
        total_pages = (len(preview_images) + items_per_page - 1) // items_per_page
        
        # Validate page number
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = preview_images[start_idx:end_idx]
        
        # First, edit the message to show we're loading
        await query.edit_message_text(f"Loading pictures {start_idx + 1}-{min(end_idx, len(preview_images))}...")
        
        # Send each image as a text message with link preview (Telegram generates thumbnail)
        for idx, item in enumerate(page_items, start=start_idx):
            image_url = item.get('url', '')
            domain = item.get('domain', 'Unknown')
            
            # Create a message with the image URL
            # Telegram will automatically generate a preview thumbnail for image URLs
            message_text = f"""
🖼️ **Picture #{idx + 1}**
📦 Domain: {domain}

🔗 Click link below to view full image:
{image_url}

💡 Tip: Telegram shows a preview thumbnail. Click to open the full image.
            """
            
            try:
                await self.send_message_with_retry(
                    query.message.reply_text,
                    message_text,
                    parse_mode='Markdown',
                    disable_web_page_preview=False  # Enable link preview to show thumbnail
                )
            except Exception as e:
                logger.error(f"Failed to send image link {idx + 1}: {e}")
                # Fallback without markdown
                try:
                    await query.message.reply_text(
                        f"Picture #{idx + 1}\nDomain: {domain}\nLink: {image_url}"
                    )
                except Exception:
                    pass
        
        # Send navigation message
        nav_text = f"""
📷 Showing pictures {start_idx + 1}-{min(end_idx, len(preview_images))} of {len(preview_images)}
📄 Page {page + 1} of {total_pages}

💡 Tip: Each image shows a preview thumbnail. Click the link to view full size.

Use the buttons below to navigate:
        """
        
        keyboard = []
        nav_buttons = []
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous 10", callback_data=f"picture_page_{page - 1}"))
        if end_idx < len(preview_images):
            nav_buttons.append(InlineKeyboardButton("Next 10 ➡️", callback_data=f"picture_page_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Add skip to page button if there are more than 10 pages
        if total_pages > 10:
            keyboard.append([InlineKeyboardButton(f"⏩ Skip to Page...", callback_data=f"picture_skip_{page}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_list")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(nav_text, reply_markup=reply_markup)
    
    async def show_picture_details(self, query, session: UserSession, picture_idx: int) -> None:
        """Show details of a specific picture."""
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
    
    async def show_picture_link(self, query, session: UserSession, picture_idx: int) -> None:
        """Show the direct link to a picture."""
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

    async def show_page_skip_menu(self, query, session: UserSession, current_page: int) -> None:
        """Show smart menu to skip to a specific page in one step."""
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
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"picture_page_{current_page}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(skip_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def update_content_page(self, query, session: UserSession, page: int) -> None:
        """Update the content list to show a different page."""
        if not session.current_directory:
            await query.edit_message_text("❌ No content directory available.")
            return
        
        session.current_page = page
        await self.back_to_content_list(query, session)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors caused by Updates."""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        # Extract update information
        error_message = "❌ An unexpected error occurred. Please try again later."
        
        try:
            if isinstance(context.error, TimedOut):
                error_message = "⏱️ Request timed out. Please check your connection and try again."
                logger.error("Telegram API timeout occurred")
            elif isinstance(context.error, NetworkError):
                error_message = "🌐 Network error. Please check your internet connection and try again."
                logger.error(f"Network error: {context.error}")
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                error_message = f"⏸️ Too many requests. Please wait {retry_after} seconds before trying again."
                logger.error(f"Rate limited. Retry after {retry_after}s")
            elif isinstance(context.error, BadRequest):
                error_message = "❌ Invalid request. Please try a different action."
                logger.error(f"Bad request: {context.error}")
            elif isinstance(context.error, RuntimeError) and "no bot associated" in str(context.error):
                error_message = "⚠️ Internal error occurred. Please try your action again."
                logger.error(f"Bot association error: {context.error}")
            else:
                logger.error(f"Unhandled error type: {type(context.error).__name__}: {context.error}")
            
            # Try to notify the user
            if update and hasattr(update, 'effective_message') and update.effective_message:
                try:
                    await asyncio.sleep(1)  # Brief delay before retry
                    await update.effective_message.reply_text(error_message)
                except Exception as e:
                    logger.error(f"Failed to send error message to user: {e}")
            elif update and hasattr(update, 'callback_query') and update.callback_query:
                try:
                    await asyncio.sleep(1)
                    await update.callback_query.answer(error_message, show_alert=True)
                except Exception as e:
                    logger.error(f"Failed to send error answer to callback query: {e}")
                    
        except Exception as e:
            logger.error(f"Error in error handler: {e}")


def main():
    """Start the bot."""
    # Get token from environment variable
    try:
        TOKEN = config('TELEGRAM_BOT_TOKEN')
    except:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file")
        print("Please add your Telegram bot token to the .env file:")
        print("TELEGRAM_BOT_TOKEN=your_bot_token_here")
        return
    
    # Create application with custom settings for better timeout handling
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)  # 30 seconds for connection
        .read_timeout(30.0)     # 30 seconds for reading response
        .write_timeout(30.0)    # 30 seconds for writing request
        .pool_timeout(30.0)     # 30 seconds for pool
        .build()
    )
    
    # Initialize bot
    bot = FreeFansBot()
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CallbackQueryHandler(bot.handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_creator_search))
    
    # Register error handler
    application.add_error_handler(bot.error_handler)
    
    # Run the bot
    print("🤖 FreeFans Bot is starting...")
    print("✅ Error handlers registered")
    print("✅ Timeout settings configured")
    print("🔄 Starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()