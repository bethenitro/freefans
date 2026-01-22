"""
Deal Handlers - Handles content deal commands and callbacks
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


class DealHandlers:
    """Handles content deal system commands and callbacks."""
    
    def __init__(self):
        """Initialize deal handlers."""
        self.pool_manager = get_pool_manager()
        self.payment_manager = get_payment_manager()
    
    async def handle_pools_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deals command - show active content deals."""
        try:
            user_id = update.effective_user.id
            
            # Get active deals
            deals = self.pool_manager.get_active_pools(limit=10)
            
            if not deals:
                text = """
💎 **Exclusive Content**

No exclusive content available right now! 

💰 Use `/balance` to check your Stars balance
"""
                await update.message.reply_text(text, parse_mode='Markdown')
                return
            
            # Create deals list
            text = "💎 **Exclusive Content**\n\n"
            text += "💡 Get exclusive content at amazing prices!\n\n"
            
            keyboard = []
            for i, deal in enumerate(deals[:5], 1):  # Show max 5 deals
                
                text += f"**{i}. {deal['creator_name']}**\n"
                text += f"📝 {deal['content_title']}\n"
                text += f"💰 Price: {deal['current_price_per_user']} ⭐\n\n"
                
                # Add enticing view button
                button_texts = [
                    f"🔥 Hot Content {i}",
                    f"💎 VIP Access {i}",
                    f"🌟 Premium {i}",
                    f"💋 Exclusive {i}",
                    f"🎯 Special {i}"
                ]
                
                button_text = button_texts[i-1] if i-1 < len(button_texts) else f"💎 Content {i}"
                keyboard.append([InlineKeyboardButton(
                    button_text, 
                    callback_data=f"view_pool_{deal['pool_id']}"
                )])
            
            # Add navigation buttons
            # if len(deals) > 5:
            #     keyboard.append([InlineKeyboardButton("📄 View More", callback_data="pools_page_2")])
            
            keyboard.append([
                InlineKeyboardButton("💰 My Balance", callback_data="my_balance"),
                InlineKeyboardButton("📊 My Purchases", callback_data="my_contributions")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in pools command: {e}")
            await update.message.reply_text("❌ Error loading deals. Please try again.")
    
    async def handle_deal_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle deal-related callback queries."""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            user_id = update.effective_user.id
            
            if data.startswith('view_pool_'):
                await self._handle_view_deal(query, data.replace('view_pool_', ''))
            
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
            
            elif data == 'back_to_deals':
                await self._handle_back_to_deals(query)
            
            elif data == 'pools_menu':
                await self._handle_back_to_deals(query)  # Same as back to deals
            
        except Exception as e:
            logger.error(f"Error in deal callback: {e}")
            await query.edit_message_text("❌ Error processing request. Please try again.")
    
    async def _handle_view_deal(self, query, pool_id: str):
        """Handle viewing a specific deal."""
        deal = self.pool_manager.get_pool(pool_id)
        if not deal:
            await query.edit_message_text("❌ Deal not found.")
            return
        
        progress = deal['completion_percentage']
        progress_bar = self._create_progress_bar(progress)
        
        text = f"💎 **Deal Details**\n\n"
        text += f"👤 **Creator:** {deal['creator_name']}\n"
        text += f"📝 **Content:** {deal['content_title']}\n"
        
        if deal['content_description']:
            text += f"📄 **Description:** {deal['content_description']}\n"
        
        text += f"🎯 **Type:** {deal['content_type'].replace('_', ' ').title()}\n\n"
        
        # Show current price
        current_price = deal['current_price_per_user']
        remaining_cost = deal['total_cost'] - deal['current_amount']
        
        text += f"💫 **Price:** {current_price} ⭐\n\n"
        
        # Create keyboard
        keyboard = []
        
        if deal['status'] == 'active' and remaining_cost > 0:
            keyboard.append([InlineKeyboardButton(f"💎 Buy Now ({current_price} ⭐)", callback_data=f"join_pool_{pool_id}")])
        elif deal['status'] == 'completed':
            keyboard.append([InlineKeyboardButton("🎉 View Content", callback_data=f"view_content_{pool_id}")])
        elif remaining_cost <= 0:
            keyboard.append([InlineKeyboardButton("✅ Content Available", callback_data="pool_complete")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_deals")])
        
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
                f"Please complete the payment to purchase {amount} ⭐ of this content.\n\n"
                f"After payment, you'll have access to:\n"
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
        text += f"🤝 **Total Purchased:** {profile['total_contributed']} Stars\n"
        text += f"🏊‍♀️ **Content Purchased:** {profile['pools_joined']}\n\n"
        
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
            text += f"• Buy Stars to purchase exclusive content\n"
            text += f"• Browse exclusive content to unlock premium material\n"
            text += f"• Check `/content` for available content"
        
        keyboard = [
            [InlineKeyboardButton("💳 Buy Stars", callback_data="buy_stars_menu")],
            [InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_deals")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_my_contributions(self, query):
        """Handle viewing user contributions."""
        user_id = query.from_user.id
        
        contributions = self.pool_manager.get_user_contributions(user_id, limit=5)
        
        text = f"📊 **Your Exclusive Content Purchases**\n\n"
        
        if not contributions:
            text += "You haven't purchased any exclusive content yet.\n\n"
            text += "💡 Browse exclusive content to unlock premium material!"
        else:
            for i, contrib in enumerate(contributions, 1):
                status_emoji = {
                    'completed': '✅',
                    'pending': '⏳',
                    'refunded': '💸'
                }.get(contrib['status'], '❓')
                
                text += f"**{i}. {contrib['creator_name']}**\n"
                text += f"📝 {contrib['content_title']}\n"
                text += f"💰 Paid: {contrib['amount']} ⭐ {status_emoji}\n"
                text += f"📅 {contrib['created_at'].strftime('%Y-%m-%d')}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Content", callback_data="back_to_deals")]]
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
                f"These Stars can be used to purchase exclusive content!"
            )
            
        except Exception as e:
            logger.error(f"Error sending star purchase invoice: {e}")
            await query.edit_message_text("❌ Error creating payment. Please try again.")
    
    async def _handle_back_to_deals(self, query):
        """Handle back to deals navigation."""
        user_id = query.from_user.id
        
        # Get active deals
        deals = self.pool_manager.get_active_pools(limit=10)
        
        if not deals:
            text = """
💎 **Exclusive Content**

No exclusive content available right now! 

💰 Use `/balance` to check your Stars balance
"""
            await query.edit_message_text(text, parse_mode='Markdown')
            return
        
        # Create deals list
        text = "💎 **Exclusive Content**\n\n"
        text += "💡 Get exclusive content at amazing prices!\n\n"
        
        keyboard = []
        for i, deal in enumerate(deals[:5], 1):  # Show max 5 deals
            
            text += f"**{i}. {deal['creator_name']}**\n"
            text += f"📝 {deal['content_title']}\n"
            text += f"💰 Price: {deal['current_price_per_user']} ⭐\n\n"
            
            # Add enticing view button
            button_texts = [
                f"🔥 Hot Content {i}",
                f"💎 VIP Access {i}",
                f"🌟 Premium {i}",
                f"💋 Exclusive {i}",
                f"🎯 Special {i}"
            ]
            
            button_text = button_texts[i-1] if i-1 < len(button_texts) else f"💎 Content {i}"
            keyboard.append([InlineKeyboardButton(
                button_text, 
                callback_data=f"view_pool_{deal['pool_id']}"
            )])
        
        # Add navigation buttons
        # if len(deals) > 5:
        #     keyboard.append([InlineKeyboardButton("📄 View More", callback_data="pools_page_2")])
        
        keyboard.append([
            InlineKeyboardButton("💰 My Balance", callback_data="my_balance"),
            InlineKeyboardButton("📊 My Purchases", callback_data="my_contributions")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
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
                        f"Use /content to find exclusive content to purchase."
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
                f"Please complete the payment to purchase:\n"
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
        
        # Check if pool is full (but don't show this to users)
        if pool['contributors_count'] >= pool['max_contributors']:
            await query.edit_message_text("❌ Content is currently unavailable.")
            return
        
        # Get current price
        current_price = pool['current_price_per_user']
        
        # Create invoice for payment
        title = f"Purchase Content - {pool['creator_name']}"
        prices = [LabeledPrice(f"{current_price} Stars", current_price)]
        description = f"Purchase exclusive content: {pool['content_title']}"
        
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
                f"After payment, you'll have access to:\n"
                f"**{pool['content_title']}** by **{pool['creator_name']}**\n\n"
                f"💡 Enjoy your exclusive content!"
            )
            
        except Exception as e:
            logger.error(f"Error sending invoice: {e}")
            await query.edit_message_text("❌ Error creating payment. Please try again.")


# Global instance
_deal_handlers = None

def get_pool_handlers() -> DealHandlers:
    """Get the global deal handlers instance."""
    global _deal_handlers
    if _deal_handlers is None:
        _deal_handlers = DealHandlers()
    return _deal_handlers