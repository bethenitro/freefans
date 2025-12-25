"""
Menu Handlers - Handles reply keyboard button presses and request system
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utilities import send_message_with_retry
from managers.request_manager import get_request_manager

logger = logging.getLogger(__name__)


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> bool:
    """
    Handle menu button presses from reply keyboard.
    Returns True if the message was a menu button, False otherwise.
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Initialize session if it doesn't exist
    if user_id not in bot_instance.user_sessions:
        from core.user_session import UserSession
        bot_instance.user_sessions[user_id] = UserSession(user_id)
    
    session = bot_instance.user_sessions[user_id]
    
    # Handle menu buttons
    if message_text == "🔍 Search Creator":
        await handle_search_button(update, context, session)
        return True
    
    elif message_text == "🎲 Random Creator":
        await handle_random_creator_button(update, context, session, bot_instance)
        return True
    
    elif message_text == "📝 Request Creator":
        await handle_request_creator_button(update, context, session)
        return True
    
    elif message_text == "🎯 Request Content":
        await handle_request_content_button(update, context, session)
        return True
    
    elif message_text == "❓ Help":
        await handle_help_button(update, context)
        return True
    
    return False


async def handle_search_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session):
    """Handle Search Creator button press"""
    session.awaiting_request = 'search'
    session.request_data = {}
    
    await update.message.reply_text(
        "🔍 Search for Creator\n\n"
        "Please enter the creator's name:\n\n"
        "📝 Send /cancel to cancel"
    )


async def handle_random_creator_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session, bot_instance):
    """Handle Random Creator button press"""
    try:
        # Show loading message
        loading_msg = await update.message.reply_text(
            "🎲 Finding a random creator with lots of content...\n\n"
            "⏳ Please wait..."
        )
        
        # Get random creator from content manager
        content_manager = bot_instance.content_manager
        random_creator = await content_manager.get_random_creator_with_content(min_items=25)
        
        if random_creator:
            creator_name = random_creator['name']
            item_count = random_creator['item_count']
            
            # Set up session for this creator
            session.pending_creator_name = creator_name
            session.pending_creator_options = None
            
            # Delete loading message
            try:
                await loading_msg.delete()
            except:
                pass
            
            # Show creator info and start content search
            await update.message.reply_text(
                f"🎲 Random Creator Found!\n\n"
                f"👤 Creator: {creator_name}\n"
                f"📊 Content Items: {item_count}\n\n"
                f"🔍 Searching for content..."
            )
            
            # Trigger content search automatically
            filters = {'content_type': 'all', 'date_range': 'all', 'quality': 'any'}
            content_result = await content_manager.search_creator_content(creator_name, filters)
            
            if content_result:
                # Import here to avoid circular imports
                from bot.callback_handlers import display_content_directory
                await display_content_directory(update, context, content_result, bot_instance)
            else:
                from bot.command_handlers import create_main_menu_keyboard
                await update.message.reply_text(
                    f"❌ Sorry, couldn't load content for {creator_name} right now.\n\n"
                    f"Try again or use 🔍 Search Creator to find someone specific.",
                    reply_markup=create_main_menu_keyboard()
                )
        else:
            # Delete loading message
            try:
                await loading_msg.delete()
            except:
                pass
            
            from bot.command_handlers import create_main_menu_keyboard
            await update.message.reply_text(
                "😔 No creators found with enough content (25+ items).\n\n"
                "Try using 🔍 Search Creator to find someone specific!",
                reply_markup=create_main_menu_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Error in random creator handler: {e}")
        
        # Delete loading message if it exists
        try:
            await loading_msg.delete()
        except:
            pass
        
        from bot.command_handlers import create_main_menu_keyboard
        await update.message.reply_text(
            "❌ Something went wrong while finding a random creator.\n\n"
            "Please try again or use 🔍 Search Creator.",
            reply_markup=create_main_menu_keyboard()
        )


async def handle_request_creator_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session):
    """Handle Request Creator button press"""
    session.awaiting_request = 'creator_platform'
    session.request_data = {'type': 'creator'}
    
    await update.message.reply_text(
        "📝 Request New Creator\n\n"
        "Step 1/2: What social media platform?\n\n"
        "Examples:\n"
        "• OnlyFans\n"
        "• Instagram\n"
        "• Twitter/X\n"
        "• TikTok\n"
        "• Fansly\n\n"
        "📝 Send /cancel to cancel"
    )


async def handle_request_content_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session):
    """Handle Request Content button press"""
    session.awaiting_request = 'content_platform'
    session.request_data = {'type': 'content'}
    
    await update.message.reply_text(
        "🎯 Request Specific Content\n\n"
        "Step 1/3: What social media platform is the creator on?\n\n"
        "Examples:\n"
        "• OnlyFans\n"
        "• Instagram\n"
        "• Twitter/X\n"
        "• TikTok\n"
        "• Fansly\n\n"
        "📝 Send /cancel to cancel"
    )


async def handle_help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Help button press"""
    from bot.command_handlers import create_main_menu_keyboard, HELP_TEXT
    reply_markup = create_main_menu_keyboard()
    await send_message_with_retry(
        update.message.reply_text,
        HELP_TEXT,
        reply_markup=reply_markup
    )


async def handle_request_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance) -> bool:
    """
    Handle multi-step request flow.
    Returns True if message was part of request flow, False otherwise.
    """
    user_id = update.effective_user.id
    
    if user_id not in bot_instance.user_sessions:
        return False
    
    session = bot_instance.user_sessions[user_id]
    
    if not session.awaiting_request:
        return False
    
    message_text = update.message.text.strip()
    
    # Handle search request - don't clear state, let bot.py handle it
    if session.awaiting_request == 'search':
        # Let the search handler in bot.py process this
        return False
    
    # Handle creator request - Step 2: Username
    elif session.awaiting_request == 'creator_platform':
        session.request_data['platform'] = message_text
        session.awaiting_request = 'creator_username'
        
        await update.message.reply_text(
            f"📝 Request New Creator\n\n"
            f"Platform: {message_text}\n\n"
            f"Step 2/2: What is the creator's username?\n\n"
            f"📝 Send /cancel to cancel"
        )
        return True
    
    elif session.awaiting_request == 'creator_username':
        session.request_data['username'] = message_text
        session.awaiting_request = None
        
        # Save the request to CSV
        platform = session.request_data.get('platform', 'Unknown')
        username = session.request_data.get('username', 'Unknown')
        
        request_manager = get_request_manager()
        request_id = request_manager.save_creator_request(user_id, platform, username)
        
        logger.info(f"Creator request {request_id} from user {user_id}: {platform} - {username}")
        
        from bot.command_handlers import create_main_menu_keyboard
        reply_markup = create_main_menu_keyboard()
        await update.message.reply_text(
            f"✅ Request Submitted!\n\n"
            f"📋 Request ID: {request_id}\n"
            f"Platform: {platform}\n"
            f"Username: {username}\n\n"
            f"� Your request has been saved and will be reviewed by our team.\n"
            f"⏰ New creators are typically added within 24-48 hours.\n\n"
            f"💡 You'll be notified when this creator is available!\n\n"
            f"Use the menu buttons to continue exploring.",
            reply_markup=reply_markup
        )
        
        session.request_data = {}
        return True
    
    # Handle content request - Step 2: Username
    elif session.awaiting_request == 'content_platform':
        session.request_data['platform'] = message_text
        session.awaiting_request = 'content_username'
        
        await update.message.reply_text(
            f"🎯 Request Specific Content\n\n"
            f"Platform: {message_text}\n\n"
            f"Step 2/3: What is the creator's username?\n\n"
            f"📝 Send /cancel to cancel"
        )
        return True
    
    elif session.awaiting_request == 'content_username':
        session.request_data['username'] = message_text
        session.awaiting_request = 'content_details'
        
        platform = session.request_data.get('platform', 'Unknown')
        await update.message.reply_text(
            f"🎯 Request Specific Content\n\n"
            f"Platform: {platform}\n"
            f"Username: {message_text}\n\n"
            f"Step 3/3: What specific content are you looking for?\n\n"
            f"Be as detailed as possible:\n"
            f"• Photo set name/date\n"
            f"• Video title/description\n"
            f"• Post date\n"
            f"• Any other identifying details\n\n"
            f"📝 Send /cancel to cancel"
        )
        return True
    
    elif session.awaiting_request == 'content_details':
        session.request_data['details'] = message_text
        session.awaiting_request = None
        
        # Save the request to CSV
        platform = session.request_data.get('platform', 'Unknown')
        username = session.request_data.get('username', 'Unknown')
        details = session.request_data.get('details', 'Unknown')
        
        request_manager = get_request_manager()
        request_id = request_manager.save_content_request(user_id, platform, username, details)
        
        logger.info(f"Content request {request_id} from user {user_id}: {platform} - {username}")
        
        from bot.command_handlers import create_main_menu_keyboard
        reply_markup = create_main_menu_keyboard()
        await update.message.reply_text(
            f"✅ Content Request Submitted!\n\n"
            f"📋 Request ID: {request_id}\n"
            f"Platform: {platform}\n"
            f"Username: {username}\n"
            f"Details: {details[:100]}{'...' if len(details) > 100 else ''}\n\n"
            f"� Your request has been saved and will be reviewed by our team.\n"
            f"⏰ Specific content requests are typically fulfilled within 2-3 days.\n\n"
            f"💡 Check back soon!\n\n"
            f"Use the menu buttons to continue exploring.",
            reply_markup=reply_markup
        )
        
        session.request_data = {}
        return True
    
    return False
