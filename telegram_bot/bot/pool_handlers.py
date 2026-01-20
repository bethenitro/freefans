"""
Pool Handlers - Handles community pooling commands and callbacks
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from telegram.error import BadRequest

try:
    # When running from project root (coordinator bot)
    from telegram_bot.managers.pool_manager import get_pool_manager
    from telegram_bot.managers.payment_manager import get_payment_manager
    from telegram_bot.bot.utilities import send_message_with_retry
except ImportError:
    # When running from telegram_bot directory
    from managers.pool_manager import get_pool_manager
    from managers.payment_manager import get_payment_manager
    from bot.utilities import send_message_with_retry

logger = logging.getLogger(__name__)


class PoolHandlers:
    """Handles community pooling system commands and callbacks."""
    
    def __init__(self):
        """Initialize pool handlers."""
        self.pool_manager = get_pool_manager()
        self.payment_manager = get_payment_manager()
    
    async def handle_pools_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pools command - show active pools."""
        try:
            user_id = update.effective_user.id
            
            # Get active pools
            pools = self.pool_manager.get_active_pools(limit=10)
            
            if not pools:
                text = """
🏊‍♀️ **Community Pools**

No active pools right now! 

💰 Use `/balance` to check your Stars balance
"""
                await update.message.reply_text(text, parse_mode='Markdown')
                return
            
            # Create pools list
            text = "🏊‍♀️ **Active Community Pools**\n\n"
            text += "💡 Join a pool to unlock exclusive content!\n\n"
            
            keyboard = []
            for i, pool in enumerate(pools[:5], 1):  # Show max 5 pools
                progress = pool['completion_percentage']
                progress_bar = self._create_progress_bar(progress)
                
                text += f"**{i}. {pool['creator_name']}**\n"
                text += f"📝 {pool['content_title']}\n"
                text += f"💰 {pool['current_amount']}/{pool['total_cost']} ⭐ ({progress:.1f}%)\n"
                text += f"👥 {pool['contributors_count']} contributors\n"
                text += f"{progress_bar}\n"
                
                # Calculate days remaining
                days_left = (pool['expires_at'] - datetime.now()).days
                if days_left > 0:
                    text += f"⏰ {days_left} days left\n\n"
                else:
                    text += f"⏰ Expires soon!\n\n"
                
                # Add view button
                keyboard.append([InlineKeyboardButton(
                    f"🔍 View Pool {i}", 
                    callback_data=f"view_pool_{pool['pool_id']}"
                )])
            
            # Add navigation buttons
            if len(pools) > 5:
                keyboard.append([InlineKeyboardButton("📄 View More", callback_data="pools_page_2")])
            
            keyboard.append([
                InlineKeyboardButton("💰 My Balance", callback_data="my_balance"),
                InlineKeyboardButton("📊 My Pools", callback_data="my_contributions")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in pools command: {e}")
            await update.message.reply_text("❌ Error loading pools. Please try again.")
    
    async def handle_pool_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pool-related callback queries."""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            user_id = update.effective_user.id
            
            if data.startswith('view_pool_'):
                await self._handle_view_pool(query, data.replace('view_pool_', ''))
            
            elif data.startswith('join_pool_'):
                await self._handle_join_pool(query, context, data.replace('join_pool_', ''))
            
            elif data.startswith('contribute_'):
                # Legacy support for old contribution system
                parts = data.split('_')
                if len(parts) >= 3:
                    pool_id = '_'.join(parts[1:-1])
                    amount = int(parts[-1])
                    await self._handle_contribute_to_pool(query, context, pool_id, amount)
            
            elif data.startswith('custom_contribute_'):
                pool_id = data.replace('custom_contribute_', '')
                await self._handle_custom_contribution(query, pool_id)
            
            elif data == 'my_balance':
                await self._handle_my_balance(query)
            
            elif data == 'my_contributions':
                await self._handle_my_contributions(query)
            
            elif data.startswith('buy_stars_'):
                package = data.replace('buy_stars_', '')
                await self._handle_buy_stars(query, context, package)
            
            elif data == 'back_to_pools':
                await self._handle_back_to_pools(query)
            
        except Exception as e:
            logger.error(f"Error in pool callback: {e}")
            await query.edit_message_text("❌ Error processing request. Please try again.")
    
    async def _handle_view_pool(self, query, pool_id: str):
        """Handle viewing a specific pool."""
        pool = self.pool_manager.get_pool(pool_id)
        if not pool:
            await query.edit_message_text("❌ Pool not found.")
            return
        
        progress = pool['completion_percentage']
        progress_bar = self._create_progress_bar(progress)
        
        text = f"🏊‍♀️ **Pool Details**\n\n"
        text += f"👤 **Creator:** {pool['creator_name']}\n"
        text += f"📝 **Content:** {pool['content_title']}\n"
        
        if pool['content_description']:
            text += f"📄 **Description:** {pool['content_description']}\n"
        
        text += f"🎯 **Type:** {pool['content_type'].replace('_', ' ').title()}\n\n"
        
        text += f"💰 **Progress:** {pool['current_amount']}/{pool['total_cost']} ⭐ ({progress:.1f}%)\n"
        text += f"{progress_bar}\n"
        text += f"👥 **Contributors:** {pool['contributors_count']}/{pool['max_contributors']}\n\n"
        
        # Show current price and how it changes
        current_price = pool['current_price_per_user']
        remaining_cost = pool['total_cost'] - pool['current_amount']
        
        text += f"💫 **Current Price:** {current_price} ⭐ per person\n"
        
        if remaining_cost > 0:
            text += f"💰 **Remaining Cost:** {remaining_cost} ⭐\n\n"
            
            # Show how price decreases with more contributors
            text += f"📊 **Price gets cheaper as more join:**\n"
            for additional in [1, 5, 10]:
                if pool['contributors_count'] + additional <= pool['max_contributors']:
                    future_price = self.pool_manager.calculate_dynamic_price(
                        pool['total_cost'], 
                        pool['contributors_count'] + additional, 
                        pool['max_contributors']
                    )
                    text += f"• +{additional} more contributors: {future_price} ⭐ each\n"
        
        # Show expiration
        days_left = (pool['expires_at'] - datetime.now()).days
        if days_left > 0:
            text += f"\n⏰ **Expires in:** {days_left} days"
        else:
            text += f"\n⏰ **Expires:** Soon!"
        
        # Create keyboard
        keyboard = []
        
        if pool['status'] == 'active' and remaining_cost > 0 and pool['contributors_count'] < pool['max_contributors']:
            keyboard.append([InlineKeyboardButton(f"💰 Join Pool ({current_price} ⭐)", callback_data=f"join_pool_{pool_id}")])
        elif pool['status'] == 'completed':
            keyboard.append([InlineKeyboardButton("🎉 View Content", callback_data=f"view_content_{pool_id}")])
        elif pool['contributors_count'] >= pool['max_contributors']:
            keyboard.append([InlineKeyboardButton("❌ Pool Full", callback_data="pool_full")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Pools", callback_data="back_to_pools")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_contribute_to_pool(self, query, context, pool_id: str, amount: int):
        """Handle contribution to a pool."""
        user_id = query.from_user.id
        
        # Get pool details
        pool = self.pool_manager.get_pool(pool_id)
        if not pool or pool['status'] != 'active':
            await query.edit_message_text("❌ Pool is not available for contributions.")
            return
        
        # Create invoice for payment
        title, prices, description = self.payment_manager.create_pool_contribution_invoice(
            pool_id, amount, pool['creator_name'], pool['content_title']
        )
        
        # Create invoice payload
        payload = f"pool_contribution_{pool_id}_{amount}"
        
        try:
            # Send invoice
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Empty for Telegram Stars
                currency="XTR",  # Telegram Stars currency
                prices=prices,
                start_parameter=f"pool_{pool_id}"
            )
            
            await query.edit_message_text(
                f"💳 **Payment Invoice Sent**\n\n"
                f"Please complete the payment to contribute {amount} ⭐ to the pool.\n\n"
                f"After payment, you'll be part of the community unlocking:\n"
                f"**{pool['content_title']}** by **{pool['creator_name']}**"
            )
            
        except Exception as e:
            logger.error(f"Error sending invoice: {e}")
            await query.edit_message_text("❌ Error creating payment. Please try again.")
    
    async def _handle_custom_contribution(self, query, pool_id: str):
        """Handle custom contribution amount."""
        text = f"💫 **Custom Contribution**\n\n"
        text += f"Please send the amount of Stars you want to contribute (1-100).\n\n"
        text += f"Type a number and send it as a message."
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"view_pool_{pool_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        
        # Store pool_id in user context for custom amount handling
        context = query.bot_data.get('user_contexts', {})
        context[query.from_user.id] = {'awaiting_custom_amount': pool_id}
        query.bot_data['user_contexts'] = context
    
    async def _handle_my_balance(self, query):
        """Handle viewing user balance."""
        user_id = query.from_user.id
        username = query.from_user.username
        
        profile = self.payment_manager.get_user_profile(user_id, username)
        
        text = f"💰 **Your Balance**\n\n"
        text += f"⭐ **Current Balance:** {profile['balance']} Stars\n"
        text += f"💸 **Total Spent:** {profile['total_spent']} Stars\n"
        text += f"🤝 **Total Contributed:** {profile['total_contributed']} Stars\n"
        text += f"🏊‍♀️ **Pools Joined:** {profile['pools_joined']}\n\n"
        
        text += f"🎯 **Subscription:** {profile['subscription_tier'].title()}\n"
        
        if profile['subscription_expires']:
            text += f"📅 **Expires:** {profile['subscription_expires'].strftime('%Y-%m-%d')}\n"
        
        # Show recent transactions
        transactions = self.payment_manager.get_user_transactions(user_id, limit=3)
        if transactions:
            text += f"\n📊 **Recent Transactions:**\n"
            for txn in transactions:
                date = txn['created_at'].strftime('%m/%d')
                text += f"• {date}: {txn['description']} ({txn['amount']} ⭐)\n"
        else:
            text += f"\n💡 **Getting Started:**\n"
            text += f"• Buy Stars to contribute to pools\n"
            text += f"• Join community pools to unlock content\n"
            text += f"• Check `/pools` for active pools"
        
        keyboard = [
            [InlineKeyboardButton("💳 Buy Stars", callback_data="buy_stars_menu")],
            [InlineKeyboardButton("🔙 Back to Pools", callback_data="back_to_pools")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_my_contributions(self, query):
        """Handle viewing user contributions."""
        user_id = query.from_user.id
        
        contributions = self.pool_manager.get_user_contributions(user_id, limit=5)
        
        text = f"📊 **Your Pool Contributions**\n\n"
        
        if not contributions:
            text += "You haven't contributed to any pools yet.\n\n"
            text += "💡 Join a pool to unlock exclusive content with the community!"
        else:
            for i, contrib in enumerate(contributions, 1):
                status_emoji = {
                    'completed': '✅',
                    'pending': '⏳',
                    'refunded': '💸'
                }.get(contrib['status'], '❓')
                
                text += f"**{i}. {contrib['creator_name']}**\n"
                text += f"📝 {contrib['content_title']}\n"
                text += f"💰 Contributed: {contrib['amount']} ⭐ {status_emoji}\n"
                text += f"📊 Pool: {contrib['pool_completion']:.1f}% complete\n"
                text += f"📅 {contrib['created_at'].strftime('%Y-%m-%d')}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Pools", callback_data="back_to_pools")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_buy_stars(self, query, context, package: str):
        """Handle buying stars."""
        user_id = query.from_user.id
        
        # Create invoice for star purchase
        title, prices, description = self.payment_manager.create_star_purchase_invoice(package)
        payload = f"star_purchase_{package}"
        
        try:
            # Send invoice
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Empty for Telegram Stars
                currency="XTR",  # Telegram Stars currency
                prices=prices,
                start_parameter=f"stars_{package}"
            )
            
            pkg_data = self.payment_manager.star_packages[package]
            await query.edit_message_text(
                f"💳 **Star Purchase Invoice Sent**\n\n"
                f"Please complete the payment to receive {pkg_data['stars']} ⭐\n\n"
                f"These Stars can be used to contribute to community pools!"
            )
            
        except Exception as e:
            logger.error(f"Error sending star purchase invoice: {e}")
            await query.edit_message_text("❌ Error creating payment. Please try again.")
    
    async def _handle_back_to_pools(self, query):
        """Handle back to pools navigation."""
        # Simulate the pools command
        from telegram import Message
        
        # Create a fake update for the pools command
        fake_message = Message(
            message_id=query.message.message_id,
            date=datetime.now(),
            chat=query.message.chat,
            from_user=query.from_user
        )
        fake_update = Update(update_id=0, message=fake_message)
        
        # Delete the current message and send new pools list
        try:
            await query.delete_message()
        except:
            pass
        
        await self.handle_pools_command(fake_update, None)
    
    def _create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """Create a visual progress bar."""
        filled = int(percentage / 100 * length)
        empty = length - filled
        return f"{'█' * filled}{'░' * empty} {percentage:.1f}%"
    
    async def handle_successful_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle successful payment callback."""
        try:
            payment = update.pre_checkout_query or update.message.successful_payment
            if not payment:
                return
            
            user_id = update.effective_user.id
            
            if update.pre_checkout_query:
                # Pre-checkout query - just approve it
                await update.pre_checkout_query.answer(ok=True)
                return
            
            # Successful payment
            successful_payment = update.message.successful_payment
            payload = successful_payment.invoice_payload
            charge_id = successful_payment.telegram_payment_charge_id
            total_amount = successful_payment.total_amount
            
            # Process the payment
            success = self.payment_manager.process_successful_payment(
                user_id, charge_id, total_amount, payload
            )
            
            if success:
                if payload.startswith('star_purchase_'):
                    # Star purchase
                    package = payload.replace('star_purchase_', '')
                    pkg_data = self.payment_manager.star_packages.get(package, {})
                    stars = pkg_data.get('stars', total_amount)
                    
                    await update.message.reply_text(
                        f"✅ **Payment Successful!**\n\n"
                        f"You received {stars} ⭐ Stars!\n\n"
                        f"Use /pools to find community pools to contribute to."
                    )
                
                elif payload.startswith('pool_contribution_') or payload.startswith('pool_join_'):
                    # Pool contribution with dynamic pricing
                    parts = payload.split('_')
                    if len(parts) >= 3:
                        if payload.startswith('pool_join_'):
                            pool_id = '_'.join(parts[2:-1])
                            expected_amount = int(parts[-1])
                        else:
                            pool_id = '_'.join(parts[2:-1])
                            expected_amount = int(parts[-1])
                        
                        # Process the contribution with dynamic pricing
                        success, message, actual_amount = self.pool_manager.contribute_to_pool(
                            pool_id, user_id, charge_id
                        )
                        
                        if success:
                            await update.message.reply_text(f"✅ {message}")
                        else:
                            await update.message.reply_text(f"❌ {message}")
                        
                        return True
            else:
                await update.message.reply_text("❌ Error processing payment. Please contact support.")
                
        except Exception as e:
            logger.error(f"Error handling successful payment: {e}")
            await update.message.reply_text("❌ Error processing payment. Please contact support.")
    
    async def handle_custom_amount_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Handle custom contribution amount messages.
        Returns True if message was handled, False otherwise.
        """
        try:
            user_id = update.effective_user.id
            user_contexts = context.bot_data.get('user_contexts', {})
            
            if user_id not in user_contexts or 'awaiting_custom_amount' not in user_contexts[user_id]:
                return False
            
            pool_id = user_contexts[user_id]['awaiting_custom_amount']
            
            # Parse amount
            try:
                amount = int(update.message.text.strip())
                if amount < 1 or amount > 100:
                    await update.message.reply_text("❌ Amount must be between 1 and 100 Stars.")
                    return True
            except ValueError:
                await update.message.reply_text("❌ Please send a valid number.")
                return True
            
            # Clear the context
            del user_contexts[user_id]
            context.bot_data['user_contexts'] = user_contexts
            
            # Process the contribution
            pool = self.pool_manager.get_pool(pool_id)
            if not pool or pool['status'] != 'active':
                await update.message.reply_text("❌ Pool is no longer available.")
                return True
            
            # Create invoice for custom amount
            title, prices, description = self.payment_manager.create_pool_contribution_invoice(
                pool_id, amount, pool['creator_name'], pool['content_title']
            )
            
            payload = f"pool_contribution_{pool_id}_{amount}"
            
            await update.message.reply_invoice(
                title=title,
                description=description,
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices,
                start_parameter=f"pool_{pool_id}"
            )
            
            await update.message.reply_text(
                f"💳 **Custom Contribution: {amount} ⭐**\n\n"
                f"Please complete the payment to contribute to:\n"
                f"**{pool['content_title']}** by **{pool['creator_name']}**"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling custom amount: {e}")
            await update.message.reply_text("❌ Error processing custom amount.")
            return True
    
    async def _handle_join_pool(self, query, context, pool_id: str):
        """Handle joining a pool with dynamic pricing."""
        user_id = query.from_user.id
        
        # Get pool details
        pool = self.pool_manager.get_pool(pool_id)
        if not pool or pool['status'] != 'active':
            await query.edit_message_text("❌ Pool is not available for contributions.")
            return
        
        # Check if pool is full
        if pool['contributors_count'] >= pool['max_contributors']:
            await query.edit_message_text("❌ Pool is full (maximum contributors reached).")
            return
        
        # Get current price
        current_price = pool['current_price_per_user']
        
        # Create invoice for payment
        title = f"Join Pool - {pool['creator_name']}"
        prices = [LabeledPrice(f"{current_price} Stars", current_price)]
        description = f"Join the community pool to unlock: {pool['content_title']}"
        
        # Create invoice payload
        payload = f"pool_join_{pool_id}_{current_price}"
        
        try:
            # Send invoice
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Empty for Telegram Stars
                currency="XTR",  # Telegram Stars currency
                prices=prices,
                start_parameter=f"pool_{pool_id}"
            )
            
            await query.edit_message_text(
                f"💳 **Payment Invoice Sent**\n\n"
                f"💰 **Your Price:** {current_price} ⭐\n\n"
                f"After payment, you'll be part of the community unlocking:\n"
                f"**{pool['content_title']}** by **{pool['creator_name']}**\n\n"
                f"💡 The price decreases as more people join!"
            )
            
        except Exception as e:
            logger.error(f"Error sending invoice: {e}")
            await query.edit_message_text("❌ Error creating payment. Please try again.")


# Global instance
_pool_handlers = None

def get_pool_handlers() -> PoolHandlers:
    """Get the global pool handlers instance."""
    global _pool_handlers
    if _pool_handlers is None:
        _pool_handlers = PoolHandlers()
    return _pool_handlers