"""
Channel Middleware - Decorator to check channel membership before allowing bot usage
"""

import logging
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

try:
    # When running from project root
    from telegram_bot.managers.channel_manager import get_channel_manager
except ImportError:
    # When running from telegram_bot directory
    from managers.channel_manager import get_channel_manager

logger = logging.getLogger(__name__)


def require_channel_membership(func):
    """
    Decorator to check if user is member of required channels before executing command.
    
    Usage:
        @require_channel_membership
        async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # This will only execute if user is member of all required channels
            pass
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            user_id = update.effective_user.id
            channel_manager = get_channel_manager()
            
            # Check membership
            is_member, missing_channels = await channel_manager.check_user_membership(user_id, context)
            
            if not is_member:
                # User is not member of all required channels
                message = channel_manager.get_membership_message(missing_channels)
                
                # Create join buttons
                keyboard = []
                for channel in missing_channels[:5]:  # Limit to 5 buttons
                    channel_name = channel.get('channel_name', 'Join Channel')
                    channel_link = channel.get('channel_link', '#')
                    keyboard.append([InlineKeyboardButton(f"📢 Join {channel_name}", url=channel_link)])
                
                # Add check membership button
                keyboard.append([InlineKeyboardButton("✅ Check Membership", callback_data="check_membership")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if update.message:
                    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                elif update.callback_query:
                    await update.callback_query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                
                return  # Don't execute the original function
            
            # User is member of all required channels, execute original function
            return await func(update, context, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in channel membership check: {e}")
            # On error, allow the function to execute (fail open)
            return await func(update, context, *args, **kwargs)
    
    return wrapper


async def handle_check_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the check membership callback."""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        channel_manager = get_channel_manager()
        
        # Re-check membership
        is_member, missing_channels = await channel_manager.check_user_membership(user_id, context)
        
        if is_member:
            # User is now member of all channels
            welcome_message = channel_manager.get_welcome_message()
            
            # Create main menu keyboard
            keyboard = [
                [InlineKeyboardButton("🔍 Search Creator", callback_data="search_creator")],
                [InlineKeyboardButton("🎲 Random Creator", callback_data="random_creator")],
                [InlineKeyboardButton("🏊‍♀️ Community Pools", callback_data="pools_menu")],
                [InlineKeyboardButton("📝 Request Creator", callback_data="request_creator")],
                [InlineKeyboardButton("❓ Help", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    f"✅ **Welcome!**\n\n{welcome_message}\n\nYou can now use all bot features!",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    await query.answer("✅ You're already verified!")
                else:
                    raise
        else:
            # User still hasn't joined all channels
            message = channel_manager.get_membership_message(missing_channels)
            
            # Create join buttons
            keyboard = []
            for channel in missing_channels[:5]:
                channel_name = channel.get('channel_name', 'Join Channel')
                channel_link = channel.get('channel_link', '#')
                keyboard.append([InlineKeyboardButton(f"📢 Join {channel_name}", url=channel_link)])
            
            keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data="check_membership")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    await query.answer("Please join the required channels first")
                else:
                    raise
            
    except Exception as e:
        logger.error(f"Error handling check membership callback: {e}")
        try:
            await query.edit_message_text("❌ Error checking membership. Please try again.")
        except Exception:
            await query.answer("❌ Error checking membership")


def create_membership_check_keyboard(missing_channels):
    """Create keyboard for membership check."""
    keyboard = []
    
    # Add join buttons for each missing channel
    for channel in missing_channels[:5]:  # Limit to 5 buttons
        channel_name = channel.get('channel_name', 'Join Channel')
        channel_link = channel.get('channel_link', '#')
        keyboard.append([InlineKeyboardButton(f"📢 Join {channel_name}", url=channel_link)])
    
    # Add check membership button
    keyboard.append([InlineKeyboardButton("✅ Check Membership", callback_data="check_membership")])
    
    return InlineKeyboardMarkup(keyboard)