"""
Admin Pool Handlers - Admin commands for managing community pools
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

try:
    # When running from project root (coordinator bot)
    from telegram_bot.managers.pool_manager import get_pool_manager
    from telegram_bot.managers.payment_manager import get_payment_manager
    from telegram_bot.managers.permissions_manager import get_permissions_manager
except ImportError:
    # When running from telegram_bot directory
    from managers.pool_manager import get_pool_manager
    from managers.payment_manager import get_payment_manager
    from managers.permissions_manager import get_permissions_manager

logger = logging.getLogger(__name__)


class AdminPoolHandlers:
    """Handles admin commands for pool management."""
    
    def __init__(self):
        """Initialize admin pool handlers."""
        self.pool_manager = get_pool_manager()
        self.payment_manager = get_payment_manager()
        self.permissions_manager = get_permissions_manager()
    
    async def handle_create_pool_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /createpool command - admin only."""
        user_id = update.effective_user.id
        
        # Check admin permissions
        if not self.permissions_manager.is_admin(user_id):
            await update.message.reply_text("❌ This command is for admins only.")
            return
        
        # Parse command arguments
        if not context.args or len(context.args) < 3:
            help_text = """
🏊‍♀️ **Create Pool Command**

**Option 1 - From Request:**
`/createpool request <request_id> <total_cost>`

**Option 2 - Manual:**
`/createpool manual <creator> <title> <type> <total_cost> [description]`

**Parameters:**
• `request_id` - Request ID from /requests command
• `creator` - Creator name (e.g., "bella_thorne")
• `title` - Content title (e.g., "Premium Video Set")
• `type` - Content type: photo_set, video, live_stream
• `total_cost` - Total cost in Stars (10-1000)
• `description` - Optional description

**Examples:**
`/createpool request CR-20240115120000-123456789 100`
`/createpool manual bella_thorne "Premium Photos" photo_set 50 "Exclusive beach photoshoot"`

💡 **Dynamic Pricing:** Users pay less as more people join!
"""
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        try:
            mode = context.args[0].lower()
            
            if mode == 'request':
                # Create pool from existing request
                if len(context.args) < 3:
                    await update.message.reply_text("❌ Usage: `/createpool request <request_id> <total_cost>`", parse_mode='Markdown')
                    return
                
                request_id = context.args[1]
                total_cost = int(context.args[2])
                
                # Validate total cost FIRST
                if total_cost < 10 or total_cost > 1000:
                    await update.message.reply_text("❌ Total cost must be between 10 and 1000 Stars.")
                    return
                
                pool_id = self.pool_manager.create_pool_from_request(
                    request_id=request_id,
                    total_cost=total_cost,
                    created_by=user_id
                )
                
                if pool_id:
                    pool = self.pool_manager.get_pool(pool_id)
                    text = f"✅ **Pool Created from Request!**\n\n"
                    text += f"🆔 **Pool ID:** `{pool_id}`\n"
                    text += f"📋 **Request ID:** `{request_id}`\n"
                    text += f"👤 **Creator:** {pool['creator_name']}\n"
                    text += f"📝 **Title:** {pool['content_title']}\n"
                    text += f"💰 **Total Cost:** {total_cost} ⭐\n"
                    text += f"💫 **Starting Price:** {pool['current_price_per_user']} ⭐ per person\n\n"
                    text += f"💡 Price decreases as more people join (max {pool['max_contributors']} contributors)!"
                    
                    text += f"\n⏰ **Expires:** {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}\n\n"
                    text += f"Users can now join this pool using `/pools`!"
                    
                    # Add quick action buttons
                    keyboard = [
                        [InlineKeyboardButton("🔍 View Pool", callback_data=f"view_pool_{pool_id}")],
                        [InlineKeyboardButton("📊 Pool Stats", callback_data="admin_pool_stats")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text("❌ Failed to create pool from request. Check request ID.")
                return
            
            elif mode == 'manual':
                # Create pool manually
                if len(context.args) < 5:
                    await update.message.reply_text("❌ Usage: `/createpool manual <creator> <title> <type> <total_cost> [description]`", parse_mode='Markdown')
                    return
                
                creator_name = context.args[1]
                content_title = context.args[2]
                content_type = context.args[3]
                total_cost = int(context.args[4])
                content_description = ' '.join(context.args[5:]) if len(context.args) > 5 else ""
                
                # Validate content type
                valid_types = ['photo_set', 'video', 'live_stream']
                if content_type not in valid_types:
                    await update.message.reply_text(f"❌ Invalid content type. Use: {', '.join(valid_types)}")
                    return
                
                # Validate total cost FIRST
                if total_cost < 10 or total_cost > 1000:
                    await update.message.reply_text("❌ Total cost must be between 10 and 1000 Stars.")
                    return
                
                # Create the pool
                pool_id = self.pool_manager.create_pool(
                    creator_name=creator_name,
                    content_title=content_title,
                    content_description=content_description,
                    content_type=content_type,
                    total_cost=total_cost,
                    created_by=user_id
                )
                
                if pool_id:
                    pool = self.pool_manager.get_pool(pool_id)
                    text = f"✅ **Pool Created Successfully!**\n\n"
                    text += f"🆔 **Pool ID:** `{pool_id}`\n"
                    text += f"👤 **Creator:** {creator_name}\n"
                    text += f"📝 **Title:** {content_title}\n"
                    text += f"🎯 **Type:** {content_type.replace('_', ' ').title()}\n"
                    text += f"💰 **Total Cost:** {total_cost} ⭐\n"
                    text += f"💫 **Starting Price:** {pool['current_price_per_user']} ⭐ per person\n"
                    
                    if content_description:
                        text += f"📄 **Description:** {content_description}\n"
                    
                    text += f"\n⏰ **Expires:** {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}\n\n"
                    text += f"Users can now join this pool using `/pools`!"
                    
                    # Add quick action buttons
                    keyboard = [
                        [InlineKeyboardButton("🔍 View Pool", callback_data=f"view_pool_{pool_id}")],
                        [InlineKeyboardButton("📊 Pool Stats", callback_data="admin_pool_stats")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text("❌ Failed to create pool. Please check the parameters.")
                return
            
            else:
                await update.message.reply_text("❌ Invalid mode. Use 'request' or 'manual'.")
                return
                
        except ValueError:
            await update.message.reply_text("❌ Invalid total cost. Please enter a number.")
        except Exception as e:
            logger.error(f"Error creating pool: {e}")
            await update.message.reply_text("❌ Error creating pool. Please try again.")
    
    async def handle_pool_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /poolstats command - admin only."""
        user_id = update.effective_user.id
        
        # Check admin permissions
        if not self.permissions_manager.is_admin(user_id):
            await update.message.reply_text("❌ This command is for admins only.")
            return
        
        try:
            # Get pool statistics
            from shared.config.database import get_db_session_sync
            from shared.data.crud import get_pool_stats
            
            db = get_db_session_sync()
            try:
                stats = get_pool_stats(db)
                
                text = f"📊 **Pool System Statistics**\n\n"
                text += f"🏊‍♀️ **Pools:**\n"
                text += f"• Total: {stats['total_pools']}\n"
                text += f"• Active: {stats['active_pools']}\n"
                text += f"• Completed: {stats['completed_pools']}\n\n"
                
                text += f"👥 **Users & Contributions:**\n"
                text += f"• Total Users: {stats['total_users']}\n"
                text += f"• Total Contributions: {stats['total_contributions']}\n\n"
                
                text += f"⭐ **Stars:**\n"
                text += f"• In User Balances: {stats['total_stars_in_system']} ⭐\n"
                text += f"• Contributed to Pools: {stats['total_stars_contributed']} ⭐\n"
                
                # Calculate success rate
                if stats['total_pools'] > 0:
                    success_rate = (stats['completed_pools'] / stats['total_pools']) * 100
                    text += f"\n📈 **Success Rate:** {success_rate:.1f}%"
                else:
                    text += f"\n💡 **Getting Started:**\n"
                    text += f"• Use `/poolrequests` to view pending requests\n"
                    text += f"• Create pools with `/createpool request <id> <cost>`\n"
                    text += f"• Users can make requests via bot menu buttons"
                
                # Add management buttons
                keyboard = [
                    [InlineKeyboardButton("🏊‍♀️ View Active Pools", callback_data="admin_view_pools")],
                    [InlineKeyboardButton("🔄 Cleanup Expired", callback_data="admin_cleanup_pools")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting pool stats: {e}")
            await update.message.reply_text("❌ Error getting pool statistics.")
    
    async def handle_requests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /requests command - show pending requests that can become pools."""
        user_id = update.effective_user.id
        
        # Check admin permissions
        if not self.permissions_manager.is_admin(user_id):
            await update.message.reply_text("❌ This command is for admins only.")
            return
        
        try:
            # Get pending requests
            requests = self.pool_manager.get_pending_requests()
            
            if not requests:
                text = """
📋 **Pending Requests**

No pending requests found.

💡 **How to get requests:**
• Users can make requests using `📝 Request Creator` or `🎯 Request Content` buttons
• Requests appear here when users submit them
• You can then create pools from these requests

**Commands:**
• `/poolstats` - View pool system statistics
• `/createpool manual <creator> <title> <type> <cost>` - Create manual pool
"""
                await update.message.reply_text(text, parse_mode='Markdown')
                return
            
            text = f"📋 **Pending Requests** ({len(requests)})\n\n"
            text += "💡 Use `/createpool request <request_id> <total_cost>` to create pools\n\n"
            
            for i, req in enumerate(requests[:10], 1):  # Show max 10 requests
                req_type_emoji = "👤" if req['type'] == 'creator' else "🎯"
                text += f"{req_type_emoji} **{i}. {req['username']}** ({req['platform']})\n"
                text += f"📋 ID: `{req['request_id']}`\n"
                text += f"📝 {req['details'][:80]}{'...' if len(req['details']) > 80 else ''}\n"
                text += f"📅 {req['timestamp'][:10]}\n\n"
            
            if len(requests) > 10:
                text += f"... and {len(requests) - 10} more requests\n\n"
            
            text += "**Quick Actions:**\n"
            text += "• `/createpool request <ID> <cost>` - Create pool from request\n"
            text += "• `/poolstats` - View pool statistics"
            
            await update.message.reply_text(text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error getting requests: {e}")
            await update.message.reply_text("❌ Error loading requests.")
    
    async def handle_complete_pool_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /completepool command - admin only."""
        user_id = update.effective_user.id
        
        # Check admin permissions
        if not self.permissions_manager.is_admin(user_id):
            await update.message.reply_text("❌ This command is for admins only.")
            return
        
        if not context.args or len(context.args) < 2:
            help_text = """
✅ **Complete Pool Command**

Usage: `/completepool <pool_id> <content_url>`

**Parameters:**
• `pool_id` - Pool ID to complete
• `content_url` - URL to the unlocked content

**Example:**
`/completepool POOL-20240115120000-ABC123 https://example.com/content/123`
"""
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        try:
            pool_id = context.args[0]
            content_url = ' '.join(context.args[1:])
            
            # Get pool details first
            pool = self.pool_manager.get_pool(pool_id)
            if not pool:
                await update.message.reply_text("❌ Pool not found.")
                return
            
            if pool['status'] != 'active':
                await update.message.reply_text(f"❌ Pool is {pool['status']}, cannot complete.")
                return
            
            # Complete the pool
            success = self.pool_manager.complete_pool(pool_id, content_url)
            
            if success:
                # Send content to all contributors automatically
                await self._deliver_content_to_contributors(pool_id, content_url, context)
                
                text = f"✅ **Pool Completed Successfully!**\n\n"
                text += f"🆔 **Pool ID:** `{pool_id}`\n"
                text += f"👤 **Creator:** {pool['creator_name']}\n"
                text += f"📝 **Title:** {pool['content_title']}\n"
                text += f"💰 **Final Amount:** {pool['current_amount']}/{pool['total_cost']} ⭐\n"
                text += f"👥 **Contributors:** {pool['contributors_count']}\n"
                text += f"🔗 **Content URL:** {content_url}\n\n"
                text += f"🎉 Content automatically delivered to all contributors!"
                
                await update.message.reply_text(text, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to complete pool.")
                
        except Exception as e:
            logger.error(f"Error completing pool: {e}")
            await update.message.reply_text("❌ Error completing pool. Please try again.")
    
    async def handle_cancel_pool_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancelpool command - admin only."""
        user_id = update.effective_user.id
        
        # Check admin permissions
        if not self.permissions_manager.is_admin(user_id):
            await update.message.reply_text("❌ This command is for admins only.")
            return
        
        if not context.args:
            help_text = """
❌ **Cancel Pool Command**

Usage: `/cancelpool <pool_id> [reason]`

**Parameters:**
• `pool_id` - Pool ID to cancel
• `reason` - Optional reason for cancellation

**Example:**
`/cancelpool POOL-20240115120000-ABC123 Content no longer available`

⚠️ **Warning:** This will refund all contributors!
"""
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        try:
            pool_id = context.args[0]
            reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            
            # Get pool details first
            pool = self.pool_manager.get_pool(pool_id)
            if not pool:
                await update.message.reply_text("❌ Pool not found.")
                return
            
            if pool['status'] != 'active':
                await update.message.reply_text(f"❌ Pool is {pool['status']}, cannot cancel.")
                return
            
            # Cancel the pool
            success = self.pool_manager.cancel_pool(pool_id, reason)
            
            if success:
                text = f"❌ **Pool Cancelled**\n\n"
                text += f"🆔 **Pool ID:** `{pool_id}`\n"
                text += f"👤 **Creator:** {pool['creator_name']}\n"
                text += f"📝 **Title:** {pool['content_title']}\n"
                text += f"💰 **Amount:** {pool['current_amount']}/{pool['total_cost']} ⭐\n"
                text += f"👥 **Contributors:** {pool['contributors_count']}\n"
                text += f"📝 **Reason:** {reason}\n\n"
                text += f"💸 All contributors will be refunded automatically."
                
                await update.message.reply_text(text, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to cancel pool.")
                
        except Exception as e:
            logger.error(f"Error cancelling pool: {e}")
            await update.message.reply_text("❌ Error cancelling pool. Please try again.")
    
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin pool callbacks."""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            user_id = update.effective_user.id
            
            # Check admin permissions
            if not self.permissions_manager.is_admin(user_id):
                await query.edit_message_text("❌ Admin access required.")
                return
            
            if data == "admin_pool_stats":
                await self._handle_admin_pool_stats_callback(query)
            elif data == "admin_view_pools":
                await self._handle_admin_view_pools_callback(query)
            elif data == "admin_cleanup_pools":
                await self._handle_admin_cleanup_pools_callback(query)
            
        except Exception as e:
            logger.error(f"Error in admin pool callback: {e}")
            await query.edit_message_text("❌ Error processing request.")
    
    async def _handle_admin_pool_stats_callback(self, query):
        """Handle admin pool stats callback."""
        try:
            from shared.config.database import get_db_session_sync
            from shared.data.crud import get_pool_stats
            
            db = get_db_session_sync()
            try:
                stats = get_pool_stats(db)
                
                text = f"📊 **Pool System Statistics**\n\n"
                text += f"🏊‍♀️ **Pools:** {stats['active_pools']} active, {stats['completed_pools']} completed\n"
                text += f"👥 **Users:** {stats['total_users']} registered\n"
                text += f"💰 **Contributions:** {stats['total_contributions']} total\n"
                text += f"⭐ **Stars:** {stats['total_stars_contributed']} contributed\n"
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data="admin_pool_stats")],
                    [InlineKeyboardButton("🏊‍♀️ View Pools", callback_data="admin_view_pools")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in admin pool stats callback: {e}")
            await query.edit_message_text("❌ Error loading statistics.")
    
    async def _handle_admin_view_pools_callback(self, query):
        """Handle admin view pools callback."""
        try:
            pools = self.pool_manager.get_active_pools(limit=5)
            
            if not pools:
                text = "🏊‍♀️ **Active Pools**\n\nNo active pools found."
                keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="admin_view_pools")]]
            else:
                text = f"🏊‍♀️ **Active Pools** ({len(pools)})\n\n"
                
                keyboard = []
                for i, pool in enumerate(pools, 1):
                    progress = pool['completion_percentage']
                    text += f"**{i}. {pool['creator_name']}**\n"
                    text += f"📝 {pool['content_title']}\n"
                    text += f"💰 {pool['current_amount']}/{pool['total_cost']} ⭐ ({progress:.1f}%)\n"
                    text += f"👥 {pool['contributors_count']} contributors\n\n"
                    
                    keyboard.append([InlineKeyboardButton(
                        f"🔍 Pool {i}", 
                        callback_data=f"view_pool_{pool['pool_id']}"
                    )])
                
                keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_view_pools")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in admin view pools callback: {e}")
            await query.edit_message_text("❌ Error loading pools.")
    
    async def _handle_admin_cleanup_pools_callback(self, query):
        """Handle admin cleanup pools callback."""
        try:
            cleaned_count = self.pool_manager.cleanup_expired_pools()
            
            text = f"🔄 **Pool Cleanup Complete**\n\n"
            text += f"Cleaned up {cleaned_count} expired pools.\n"
            
            if cleaned_count > 0:
                text += f"All contributors have been automatically refunded."
            else:
                text += f"No expired pools found."
            
            keyboard = [
                [InlineKeyboardButton("📊 View Stats", callback_data="admin_pool_stats")],
                [InlineKeyboardButton("🏊‍♀️ View Pools", callback_data="admin_view_pools")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in admin cleanup callback: {e}")
            await query.edit_message_text("❌ Error during cleanup.")
    
    async def _deliver_content_to_contributors(self, pool_id: str, content_url: str, context: ContextTypes.DEFAULT_TYPE):
        """Automatically deliver content to all pool contributors."""
        try:
            # Get all contributors for this pool
            contributors = self.pool_manager.get_pool_contributors(pool_id)
            
            if not contributors:
                logger.warning(f"No contributors found for pool {pool_id}")
                return
            
            # Get pool details for the message
            pool = self.pool_manager.get_pool(pool_id)
            if not pool:
                logger.error(f"Pool {pool_id} not found when delivering content")
                return
            
            # Prepare the delivery message
            message_text = f"🎉 **Pool Content Delivered!**\n\n"
            message_text += f"👤 **Creator:** {pool['creator_name']}\n"
            message_text += f"📝 **Title:** {pool['content_title']}\n"
            message_text += f"💰 **Your Contribution:** {contributors[0].get('amount', 'N/A')} ⭐\n\n"
            message_text += f"🔗 **Access Your Content:**\n{content_url}\n\n"
            message_text += f"Thank you for participating in the community pool! 💖"
            
            # Send to each contributor
            delivered_count = 0
            failed_count = 0
            
            for contributor in contributors:
                try:
                    user_id = contributor.get('user_id')
                    if not user_id:
                        continue
                    
                    # Personalize the message with their contribution amount
                    personal_message = message_text.replace(
                        f"💰 **Your Contribution:** {contributors[0].get('amount', 'N/A')} ⭐",
                        f"💰 **Your Contribution:** {contributor.get('amount', 'N/A')} ⭐"
                    )
                    
                    # Send the content to the contributor
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=personal_message,
                        parse_mode='Markdown'
                    )
                    
                    delivered_count += 1
                    logger.info(f"Delivered content to contributor {user_id} for pool {pool_id}")
                    
                    # Small delay to avoid rate limiting
                    import asyncio
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to deliver content to contributor {user_id}: {e}")
            
            logger.info(f"Content delivery complete for pool {pool_id}: {delivered_count} delivered, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error delivering content to contributors for pool {pool_id}: {e}")


# Global instance
_admin_pool_handlers = None

def get_admin_pool_handlers() -> AdminPoolHandlers:
    """Get the global admin pool handlers instance."""
    global _admin_pool_handlers
    if _admin_pool_handlers is None:
        _admin_pool_handlers = AdminPoolHandlers()
    return _admin_pool_handlers