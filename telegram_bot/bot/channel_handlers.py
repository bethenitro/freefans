"""
Channel Handlers - Admin commands for managing required channel memberships
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

try:
    # When running from project root
    from telegram_bot.managers.channel_manager import get_channel_manager
    from telegram_bot.managers.permissions_manager import get_permissions_manager
except ImportError:
    # When running from telegram_bot directory
    from managers.channel_manager import get_channel_manager
    from managers.permissions_manager import get_permissions_manager

logger = logging.getLogger(__name__)


async def add_required_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a required channel (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if not context.args or len(context.args) < 2:
        help_text = """
📢 **Add Required Channel**

Usage: `/addrequiredchannel <channel_id> <channel_name> [channel_link]`

**Parameters:**
• `channel_id` - Channel ID or username (e.g., @mychannel or -1001234567890)
• `channel_name` - Display name for the channel
• `channel_link` - Optional invite link (auto-generated if not provided)

**Examples:**
```
/addrequiredchannel @mychannel "My Awesome Channel"
/addrequiredchannel -1001234567890 "Private Channel" https://t.me/+AbCdEfGhIjK
```

**Note:** The bot must be an admin in the channel to check memberships!
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        channel_id = context.args[0]
        channel_name = context.args[1]
        channel_link = context.args[2] if len(context.args) > 2 else None
        
        channel_manager = get_channel_manager()
        
        # Validate channel ID format
        if not (channel_id.startswith('@') or channel_id.startswith('-100')):
            await update.message.reply_text(
                "❌ Invalid channel ID format. Use @username or -1001234567890 format."
            )
            return
        
        # Try to get channel info to validate
        try:
            chat = await context.bot.get_chat(channel_id)
            actual_name = chat.title or chat.first_name or channel_name
            
            # Use actual channel name if available
            if chat.title:
                channel_name = chat.title
                
        except Exception as e:
            logger.warning(f"Could not get channel info for {channel_id}: {e}")
            await update.message.reply_text(
                f"⚠️ Warning: Could not verify channel {channel_id}. "
                f"Make sure the bot is added as an admin to the channel.\n\n"
                f"Proceeding with manual setup..."
            )
        
        # Add the channel
        success = channel_manager.add_required_channel(channel_id, channel_name, channel_link)
        
        if success:
            text = f"✅ **Required Channel Added!**\n\n"
            text += f"📢 **Channel:** {channel_name}\n"
            text += f"🆔 **ID:** `{channel_id}`\n"
            
            if channel_link:
                text += f"🔗 **Link:** {channel_link}\n"
            
            text += f"\n💡 Users must now join this channel to use the bot!"
            
            # Add management buttons
            keyboard = [
                [InlineKeyboardButton("📋 View All Channels", callback_data="view_required_channels")],
                [InlineKeyboardButton("⚙️ Channel Settings", callback_data="channel_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Channel already exists in required list.")
            
    except Exception as e:
        logger.error(f"Error adding required channel: {e}")
        await update.message.reply_text("❌ Error adding channel. Please try again.")


async def remove_required_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a required channel (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if not context.args or len(context.args) < 1:
        help_text = """
🗑️ **Remove Required Channel**

Usage: `/removerequiredchannel <channel_id>`

**Parameters:**
• `channel_id` - Channel ID or username to remove

**Examples:**
```
/removerequiredchannel @mychannel
/removerequiredchannel -1001234567890
```
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        channel_id = context.args[0]
        channel_manager = get_channel_manager()
        
        success = channel_manager.remove_required_channel(channel_id)
        
        if success:
            await update.message.reply_text(
                f"✅ **Channel Removed!**\n\n"
                f"🗑️ Removed: `{channel_id}`\n\n"
                f"Users no longer need to join this channel to use the bot.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Channel `{channel_id}` not found in required list.", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error removing required channel: {e}")
        await update.message.reply_text("❌ Error removing channel. Please try again.")


async def list_required_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all required channels (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    try:
        channel_manager = get_channel_manager()
        channels = channel_manager.get_required_channels()
        
        if not channels:
            text = """
📢 **Required Channels**

No required channels configured.

💡 **Getting Started:**
• Use `/addrequiredchannel` to add channels
• Users will need to join all required channels to use the bot
• Admins can bypass this requirement (configurable)

**Commands:**
• `/addrequiredchannel <id> <name>` - Add channel
• `/channelsettings` - Configure settings
"""
            await update.message.reply_text(text, parse_mode='Markdown')
            return
        
        text = f"📢 **Required Channels** ({len(channels)})\n\n"
        text += "Users must join ALL these channels to use the bot:\n\n"
        
        for i, channel in enumerate(channels, 1):
            channel_name = channel.get('channel_name', 'Unknown')
            channel_id = channel.get('channel_id', 'Unknown')
            channel_link = channel.get('channel_link', '')
            
            text += f"**{i}. {channel_name}**\n"
            text += f"🆔 `{channel_id}`\n"
            
            if channel_link:
                text += f"🔗 [Join Channel]({channel_link})\n"
            
            text += "\n"
        
        # Add management buttons
        keyboard = [
            [InlineKeyboardButton("⚙️ Channel Settings", callback_data="channel_settings")],
            [InlineKeyboardButton("🔄 Refresh List", callback_data="view_required_channels")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error listing required channels: {e}")
        await update.message.reply_text("❌ Error loading channels list.")


async def channel_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure channel settings (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    try:
        channel_manager = get_channel_manager()
        config = channel_manager._get_full_config()
        
        text = f"⚙️ **Channel Settings**\n\n"
        
        bypass_admins = config.get('bypass_for_admins', True)
        bypass_workers = config.get('bypass_for_workers', False)
        
        text += f"👑 **Admin Bypass:** {'✅ Enabled' if bypass_admins else '❌ Disabled'}\n"
        text += f"👷 **Worker Bypass:** {'✅ Enabled' if bypass_workers else '❌ Disabled'}\n\n"
        
        text += f"📝 **Welcome Message:**\n"
        text += f"_{config.get('welcome_message', 'Default message')}_\n\n"
        
        text += f"📋 **Membership Check Message:**\n"
        text += f"_{config.get('membership_check_message', 'Default message')}_\n\n"
        
        text += f"💡 Use the buttons below to modify settings."
        
        # Create settings keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    f"👑 Admin Bypass: {'ON' if bypass_admins else 'OFF'}", 
                    callback_data=f"toggle_admin_bypass_{not bypass_admins}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"👷 Worker Bypass: {'ON' if bypass_workers else 'OFF'}", 
                    callback_data=f"toggle_worker_bypass_{not bypass_workers}"
                )
            ],
            [InlineKeyboardButton("📝 Edit Messages", callback_data="edit_channel_messages")],
            [InlineKeyboardButton("📋 View Channels", callback_data="view_required_channels")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error showing channel settings: {e}")
        await update.message.reply_text("❌ Error loading settings.")


async def handle_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel management callbacks."""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        permissions = get_permissions_manager()
        if not permissions.is_admin(user_id):
            await query.edit_message_text("❌ Admin access required.")
            return
        
        channel_manager = get_channel_manager()
        
        if data == "view_required_channels":
            await _handle_view_channels_callback(query, channel_manager)
        elif data == "channel_settings":
            await _handle_settings_callback(query, channel_manager)
        elif data.startswith("toggle_admin_bypass_"):
            new_value = data.split("_")[-1] == "True"
            await _handle_toggle_admin_bypass(query, channel_manager, new_value)
        elif data.startswith("toggle_worker_bypass_"):
            new_value = data.split("_")[-1] == "True"
            await _handle_toggle_worker_bypass(query, channel_manager, new_value)
        elif data == "edit_channel_messages":
            await _handle_edit_messages_callback(query)
        
    except Exception as e:
        logger.error(f"Error in channel callback: {e}")
        try:
            if "message is not modified" in str(e).lower():
                await query.answer("✅ No changes needed")
            else:
                await query.edit_message_text("❌ Error processing request.")
        except Exception:
            # If we can't edit the message, just answer the callback
            await query.answer("❌ Error processing request")


async def _handle_view_channels_callback(query, channel_manager):
    """Handle view channels callback."""
    try:
        channels = channel_manager.get_required_channels()
        
        if not channels:
            text = "📢 **Required Channels**\n\nNo channels configured."
            keyboard = [[InlineKeyboardButton("⚙️ Settings", callback_data="channel_settings")]]
        else:
            text = f"📢 **Required Channels** ({len(channels)})\n\n"
            
            for i, channel in enumerate(channels, 1):
                channel_name = channel.get('channel_name', 'Unknown')
                channel_id = channel.get('channel_id', 'Unknown')
                text += f"**{i}. {channel_name}**\n"
                text += f"🆔 `{channel_id}`\n\n"
            
            keyboard = [
                [InlineKeyboardButton("⚙️ Settings", callback_data="channel_settings")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="view_required_channels")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            # Message content is the same, just answer the callback
            await query.answer("✅ Already up to date")
        else:
            logger.error(f"Error in view channels callback: {e}")
            await query.answer("❌ Error loading channels")


async def _handle_settings_callback(query, channel_manager):
    """Handle settings callback."""
    try:
        config = channel_manager._get_full_config()
        
        text = f"⚙️ **Channel Settings**\n\n"
        
        bypass_admins = config.get('bypass_for_admins', True)
        bypass_workers = config.get('bypass_for_workers', False)
        
        text += f"👑 **Admin Bypass:** {'✅ Enabled' if bypass_admins else '❌ Disabled'}\n"
        text += f"👷 **Worker Bypass:** {'✅ Enabled' if bypass_workers else '❌ Disabled'}\n\n"
        
        text += f"💡 Use buttons to toggle settings."
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"👑 Admin Bypass: {'ON' if bypass_admins else 'OFF'}", 
                    callback_data=f"toggle_admin_bypass_{not bypass_admins}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"👷 Worker Bypass: {'ON' if bypass_workers else 'OFF'}", 
                    callback_data=f"toggle_worker_bypass_{not bypass_workers}"
                )
            ],
            [InlineKeyboardButton("📋 View Channels", callback_data="view_required_channels")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            # Message content is the same, just answer the callback
            await query.answer("✅ Settings updated")
        else:
            logger.error(f"Error in settings callback: {e}")
            await query.answer("❌ Error loading settings")


async def _handle_toggle_admin_bypass(query, channel_manager, new_value):
    """Handle toggle admin bypass."""
    try:
        success = channel_manager.update_settings(bypass_for_admins=new_value)
        
        if success:
            # Return to settings menu with updated values
            await _handle_settings_callback(query, channel_manager)
        else:
            await query.edit_message_text("❌ Failed to update setting.")
    except Exception as e:
        if "message is not modified" in str(e).lower():
            await query.answer("✅ Setting already updated")
        else:
            logger.error(f"Error toggling admin bypass: {e}")
            await query.answer("❌ Error updating setting")


async def _handle_toggle_worker_bypass(query, channel_manager, new_value):
    """Handle toggle worker bypass."""
    try:
        success = channel_manager.update_settings(bypass_for_workers=new_value)
        
        if success:
            # Return to settings menu with updated values
            await _handle_settings_callback(query, channel_manager)
        else:
            await query.edit_message_text("❌ Failed to update setting.")
    except Exception as e:
        if "message is not modified" in str(e).lower():
            await query.answer("✅ Setting already updated")
        else:
            logger.error(f"Error toggling worker bypass: {e}")
            await query.answer("❌ Error updating setting")


async def _handle_edit_messages_callback(query):
    """Handle edit messages callback."""
    text = """
📝 **Edit Channel Messages**

To customize messages, use these commands:

**Set Welcome Message:**
`/setwelcomemessage Your custom welcome message here`

**Set Membership Check Message:**
`/setmembershipmessage Your custom membership message here`

**Current Messages:**
• Welcome: Shown to new users
• Membership Check: Shown when user hasn't joined required channels

💡 Messages support Markdown formatting!
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="channel_settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)


async def set_welcome_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom welcome message (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/setwelcomemessage Your custom welcome message here`",
            parse_mode='Markdown'
        )
        return
    
    try:
        message = ' '.join(context.args)
        channel_manager = get_channel_manager()
        
        success = channel_manager.update_settings(welcome_message=message)
        
        if success:
            await update.message.reply_text(
                f"✅ **Welcome Message Updated!**\n\n"
                f"**New Message:**\n{message}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to update welcome message.")
            
    except Exception as e:
        logger.error(f"Error setting welcome message: {e}")
        await update.message.reply_text("❌ Error updating message.")


async def set_membership_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom membership check message (admin only)."""
    user_id = update.effective_user.id
    permissions = get_permissions_manager()
    
    if not permissions.is_admin(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/setmembershipmessage Your custom membership message here`",
            parse_mode='Markdown'
        )
        return
    
    try:
        message = ' '.join(context.args)
        channel_manager = get_channel_manager()
        
        success = channel_manager.update_settings(membership_check_message=message)
        
        if success:
            await update.message.reply_text(
                f"✅ **Membership Message Updated!**\n\n"
                f"**New Message:**\n{message}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to update membership message.")
            
    except Exception as e:
        logger.error(f"Error setting membership message: {e}")
        await update.message.reply_text("❌ Error updating message.")