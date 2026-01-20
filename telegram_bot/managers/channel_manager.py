"""
Channel Manager - Manages required channel memberships for bot access
"""

import logging
import json
from typing import List, Dict, Optional, Tuple
from telegram import Update, Bot, ChatMember
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest, Forbidden

try:
    # When running from project root
    from telegram_bot.managers.permissions_manager import get_permissions_manager
except ImportError:
    # When running from telegram_bot directory
    from managers.permissions_manager import get_permissions_manager

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages required channel memberships for bot access."""
    
    def __init__(self):
        """Initialize channel manager."""
        self.config_file = "config/required_channels.json"
        self.required_channels = self._load_channels()
        self.permissions_manager = get_permissions_manager()
    
    def _load_channels(self) -> List[Dict]:
        """Load required channels from config file."""
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                return data.get('channels', [])
        except (FileNotFoundError, json.JSONDecodeError):
            # Create default config if file doesn't exist
            default_config = {
                "channels": [],
                "bypass_for_admins": True,
                "bypass_for_workers": False,
                "welcome_message": "Welcome! To use this bot, please join our required channels first.",
                "membership_check_message": "Please join the following channels to use the bot:"
            }
            self._save_channels(default_config)
            return []
    
    def _save_channels(self, config: Dict):
        """Save channels config to file."""
        try:
            import os
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving channels config: {e}")
    
    def _get_full_config(self) -> Dict:
        """Get full configuration including settings."""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "channels": [],
                "bypass_for_admins": True,
                "bypass_for_workers": False,
                "welcome_message": "Welcome! To use this bot, please join our required channels first.",
                "membership_check_message": "Please join the following channels to use the bot:"
            }
    
    async def check_user_membership(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[bool, List[Dict]]:
        """
        Check if user is member of all required channels.
        
        Returns:
            Tuple of (is_member_of_all, list_of_missing_channels)
        """
        # Check if user should bypass channel requirements
        if self._should_bypass_user(user_id):
            return True, []
        
        if not self.required_channels:
            return True, []  # No channels required
        
        missing_channels = []
        bot_admin_issues = []
        
        for channel in self.required_channels:
            channel_id = channel.get('channel_id')
            channel_name = channel.get('channel_name', 'Unknown Channel')
            
            if not channel_id:
                logger.warning(f"Channel configuration missing channel_id: {channel}")
                continue
            
            try:
                # Check membership
                member = await context.bot.get_chat_member(channel_id, user_id)
                
                # Check if user is actually a member (not left, kicked, or restricted)
                if member.status in ['left', 'kicked']:
                    missing_channels.append(channel)
                elif member.status == 'restricted' and not member.can_send_messages:
                    missing_channels.append(channel)
                
            except BadRequest as e:
                error_msg = str(e).lower()
                if "chat not found" in error_msg:
                    logger.error(f"❌ Channel {channel_id} ({channel_name}) not found - invalid channel")
                    # Don't block user for invalid channels, but log the issue
                    continue
                elif "chat_admin_required" in error_msg:
                    logger.error(f"❌ Bot is not admin in channel {channel_id} ({channel_name})")
                    bot_admin_issues.append(channel)
                    # For now, assume user is not a member if we can't check
                    missing_channels.append(channel)
                elif "user not found" in error_msg:
                    logger.warning(f"User {user_id} not found when checking channel {channel_id}")
                    # User doesn't exist, treat as not a member
                    missing_channels.append(channel)
                else:
                    logger.warning(f"BadRequest checking membership for {channel_id}: {e}")
                    # On unknown BadRequest, assume not a member
                    missing_channels.append(channel)
                    
            except Forbidden as e:
                logger.error(f"❌ Bot forbidden from accessing channel {channel_id} ({channel_name}): {e}")
                bot_admin_issues.append(channel)
                # Bot was removed or blocked, assume user not a member
                missing_channels.append(channel)
                
            except TelegramError as e:
                logger.warning(f"Telegram error checking membership for {channel_id} ({channel_name}): {e}")
                # On other Telegram errors, assume not a member for safety
                missing_channels.append(channel)
                
            except Exception as e:
                logger.error(f"Unexpected error checking membership for {channel_id} ({channel_name}): {e}")
                # On unexpected errors, assume not a member for safety
                missing_channels.append(channel)
        
        # If there are bot admin issues, log them for admin attention
        if bot_admin_issues:
            admin_channels = [f"{ch.get('channel_name', 'Unknown')} ({ch.get('channel_id', 'Unknown')})" for ch in bot_admin_issues]
            logger.error(f"🚨 ADMIN ACTION REQUIRED: Bot needs admin access to: {', '.join(admin_channels)}")
        
        return len(missing_channels) == 0, missing_channels
    
    def _should_bypass_user(self, user_id: int) -> bool:
        """Check if user should bypass channel requirements."""
        config = self._get_full_config()
        
        # Always bypass for main admin
        if self.permissions_manager.is_main_admin(user_id):
            return True
        
        # Check admin bypass setting
        if config.get('bypass_for_admins', True) and self.permissions_manager.is_admin(user_id):
            return True
        
        # Check worker bypass setting
        if config.get('bypass_for_workers', False) and self.permissions_manager.is_worker(user_id):
            return True
        
        return False
    
    def add_required_channel(self, channel_id: str, channel_name: str, channel_link: str = None) -> bool:
        """Add a required channel."""
        try:
            config = self._get_full_config()
            
            # Check if channel already exists
            for channel in config['channels']:
                if channel.get('channel_id') == channel_id:
                    return False  # Already exists
            
            # Add new channel
            new_channel = {
                'channel_id': channel_id,
                'channel_name': channel_name,
                'channel_link': channel_link or f"https://t.me/{channel_id.replace('@', '')}"
            }
            
            config['channels'].append(new_channel)
            self._save_channels(config)
            self.required_channels = config['channels']
            
            logger.info(f"Added required channel: {channel_name} ({channel_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding required channel: {e}")
            return False
    
    def remove_required_channel(self, channel_id: str) -> bool:
        """Remove a required channel."""
        try:
            config = self._get_full_config()
            
            # Find and remove channel
            original_count = len(config['channels'])
            config['channels'] = [ch for ch in config['channels'] if ch.get('channel_id') != channel_id]
            
            if len(config['channels']) < original_count:
                self._save_channels(config)
                self.required_channels = config['channels']
                logger.info(f"Removed required channel: {channel_id}")
                return True
            
            return False  # Channel not found
            
        except Exception as e:
            logger.error(f"Error removing required channel: {e}")
            return False
    
    def get_required_channels(self) -> List[Dict]:
        """Get list of required channels."""
        return self.required_channels.copy()
    
    def update_settings(self, bypass_for_admins: bool = None, bypass_for_workers: bool = None,
                       welcome_message: str = None, membership_check_message: str = None) -> bool:
        """Update channel manager settings."""
        try:
            config = self._get_full_config()
            
            if bypass_for_admins is not None:
                config['bypass_for_admins'] = bypass_for_admins
            
            if bypass_for_workers is not None:
                config['bypass_for_workers'] = bypass_for_workers
            
            if welcome_message is not None:
                config['welcome_message'] = welcome_message
            
            if membership_check_message is not None:
                config['membership_check_message'] = membership_check_message
            
            self._save_channels(config)
            logger.info("Updated channel manager settings")
            return True
            
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False
    
    def get_membership_message(self, missing_channels: List[Dict]) -> str:
        """Generate membership requirement message."""
        config = self._get_full_config()
        
        message = config.get('membership_check_message', 'Please join the following channels to use the bot:')
        message += "\n\n"
        
        for i, channel in enumerate(missing_channels, 1):
            channel_name = channel.get('channel_name', 'Unknown Channel')
            channel_link = channel.get('channel_link', '#')
            message += f"{i}. [{channel_name}]({channel_link})\n"
        
        message += "\n💡 After joining all channels, send /start again to use the bot!"
        
        return message
    
    def get_welcome_message(self) -> str:
        """Get welcome message for new users."""
        config = self._get_full_config()
        return config.get('welcome_message', 'Welcome! To use this bot, please join our required channels first.')


# Global instance
_channel_manager = None

def get_channel_manager() -> ChannelManager:
    """Get the global channel manager instance."""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager