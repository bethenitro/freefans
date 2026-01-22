"""
Payment Manager - Handles Telegram Stars payments and user balances
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from telegram import LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

# Import database components
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import get_db_session_sync
from shared.data.models import UserProfile, Transaction

logger = logging.getLogger(__name__)


class PaymentManager:
    """Manages Telegram Stars payments and user balances."""
    
    def __init__(self):
        """Initialize payment manager."""
        # Telegram Stars pricing (in Stars)
        self.star_packages = {
            'small': {'stars': 50, 'price': 50, 'title': '50 Stars', 'description': 'Small package'},
            'medium': {'stars': 100, 'price': 100, 'title': '100 Stars', 'description': 'Medium package'},
            'large': {'stars': 250, 'price': 250, 'title': '250 Stars', 'description': 'Large package'},
            'mega': {'stars': 500, 'price': 500, 'title': '500 Stars', 'description': 'Mega package'}
        }
        
        # Pool contribution amounts (in Stars)
        self.contribution_amounts = [1, 5, 10, 25, 50, 100]
    
    def get_user_profile(self, user_id: int, username: str = None) -> Dict:
        """
        Get or create user profile.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            
        Returns:
            User profile data dict
        """
        try:
            db = get_db_session_sync()
            try:
                profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                
                if not profile:
                    # Create new profile
                    profile = UserProfile(
                        user_id=user_id,
                        username=username
                    )
                    db.add(profile)
                    db.commit()
                    logger.info(f"Created new user profile for {user_id}")
                else:
                    # Update username if provided
                    if username and profile.username != username:
                        profile.username = username
                        db.commit()
                
                return {
                    'user_id': profile.user_id,
                    'username': profile.username,
                    'balance': profile.balance,
                    'total_spent': profile.total_spent,
                    'total_contributed': profile.total_contributed,
                    'subscription_tier': profile.subscription_tier,
                    'subscription_expires': profile.subscription_expires,
                    'total_searches': profile.total_searches,
                    'total_downloads': profile.total_downloads,
                    'pools_joined': profile.pools_joined,
                    'created_at': profile.created_at
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            return {
                'user_id': user_id,
                'username': username,
                'balance': 0,
                'total_spent': 0,
                'total_contributed': 0,
                'subscription_tier': 'free',
                'subscription_expires': None,
                'total_searches': 0,
                'total_downloads': 0,
                'pools_joined': 0,
                'created_at': datetime.now()
            }
    
    def create_star_purchase_invoice(self, package: str) -> Tuple[str, List[LabeledPrice], str]:
        """
        Create invoice for Telegram Stars purchase.
        
        Args:
            package: Package type ('small', 'medium', 'large', 'mega')
            
        Returns:
            (title, prices, description)
        """
        if package not in self.star_packages:
            package = 'small'
        
        pkg = self.star_packages[package]
        
        title = f"Purchase {pkg['title']}"
        prices = [LabeledPrice(pkg['title'], pkg['price'])]
        description = f"Buy {pkg['stars']} Telegram Stars for getting exclusive content for cheap"
        
        return title, prices, description
    
    def create_pool_contribution_invoice(self, pool_id: str, amount: int, 
                                       creator_name: str, content_title: str) -> Tuple[str, List[LabeledPrice], str]:
        """
        Create invoice for pool contribution.
        
        Args:
            pool_id: Pool ID
            amount: Contribution amount in Stars
            creator_name: Creator name
            content_title: Content title
            
        Returns:
            (title, prices, description)
        """
        title = f"Pool Contribution - {creator_name}"
        prices = [LabeledPrice(f"{amount} Stars", amount)]
        description = f"Contribute {amount} Stars to unlock: {content_title}"
        
        return title, prices, description
    
    def process_successful_payment(self, user_id: int, payment_charge_id: str, 
                                 total_amount: int, invoice_payload: str) -> bool:
        """
        Process successful Telegram Stars payment.
        
        Args:
            user_id: User who made the payment
            payment_charge_id: Telegram payment charge ID
            total_amount: Amount paid in Stars
            invoice_payload: Invoice payload to determine payment type
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            db = get_db_session_sync()
            try:
                # Get or create user profile
                profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                if not profile:
                    profile = UserProfile(user_id=user_id)
                    db.add(profile)
                
                # Parse invoice payload to determine payment type
                if invoice_payload.startswith('star_purchase_'):
                    # Star purchase
                    package = invoice_payload.replace('star_purchase_', '')
                    if package in self.star_packages:
                        stars_amount = self.star_packages[package]['stars']
                        
                        # Add stars to balance
                        profile.balance += stars_amount
                        profile.total_spent += total_amount
                        
                        # Create transaction record
                        transaction_id = f"STAR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                        transaction = Transaction(
                            transaction_id=transaction_id,
                            user_id=user_id,
                            transaction_type='star_purchase',
                            amount=total_amount,
                            payment_charge_id=payment_charge_id,
                            status='completed',
                            description=f"Purchased {stars_amount} Stars ({package} package)"
                        )
                        db.add(transaction)
                        
                        db.commit()
                        logger.info(f"User {user_id} purchased {stars_amount} Stars for {total_amount}")
                        return True
                
                elif invoice_payload.startswith('pool_contribution_') or invoice_payload.startswith('pool_join_'):
                    # Pool contribution with dynamic pricing - let pool manager handle it
                    # Just record the basic transaction here
                    transaction_id = f"POOL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                    transaction = Transaction(
                        transaction_id=transaction_id,
                        user_id=user_id,
                        transaction_type='pool_contribution',
                        amount=total_amount,
                        payment_charge_id=payment_charge_id,
                        status='completed',
                        description=f"Pool contribution payment"
                    )
                    db.add(transaction)
                    db.commit()
                    
                    logger.info(f"Recorded pool contribution payment for user {user_id}: {total_amount} Stars")
                    return True
                
                else:
                    logger.warning(f"Unknown invoice payload: {invoice_payload}")
                    return False
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error processing payment for user {user_id}: {e}")
            return False
    
    def deduct_balance(self, user_id: int, amount: int, description: str = None) -> bool:
        """
        Deduct amount from user's balance.
        
        Args:
            user_id: User ID
            amount: Amount to deduct in Stars
            description: Transaction description
            
        Returns:
            True if successful, False if insufficient balance
        """
        try:
            db = get_db_session_sync()
            try:
                profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                if not profile or profile.balance < amount:
                    return False
                
                # Deduct from balance
                profile.balance -= amount
                
                # Create transaction record
                transaction_id = f"DEDUCT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                transaction = Transaction(
                    transaction_id=transaction_id,
                    user_id=user_id,
                    transaction_type='balance_deduction',
                    amount=amount,
                    status='completed',
                    description=description or f"Balance deduction: {amount} Stars"
                )
                db.add(transaction)
                
                db.commit()
                logger.info(f"Deducted {amount} Stars from user {user_id} balance")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error deducting balance for user {user_id}: {e}")
            return False
    
    def add_balance(self, user_id: int, amount: int, description: str = None) -> bool:
        """
        Add amount to user's balance.
        
        Args:
            user_id: User ID
            amount: Amount to add in Stars
            description: Transaction description
            
        Returns:
            True if successful, False otherwise
        """
        try:
            db = get_db_session_sync()
            try:
                profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                if not profile:
                    profile = UserProfile(user_id=user_id)
                    db.add(profile)
                
                # Add to balance
                profile.balance += amount
                
                # Create transaction record
                transaction_id = f"ADD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                transaction = Transaction(
                    transaction_id=transaction_id,
                    user_id=user_id,
                    transaction_type='balance_addition',
                    amount=amount,
                    status='completed',
                    description=description or f"Balance addition: {amount} Stars"
                )
                db.add(transaction)
                
                db.commit()
                logger.info(f"Added {amount} Stars to user {user_id} balance")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error adding balance for user {user_id}: {e}")
            return False
    
    def get_user_transactions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Get user's transaction history.
        
        Args:
            user_id: User ID
            limit: Maximum number of transactions to return
            
        Returns:
            List of transaction data dicts
        """
        try:
            db = get_db_session_sync()
            try:
                transactions = db.query(Transaction).filter(
                    Transaction.user_id == user_id
                ).order_by(Transaction.created_at.desc()).limit(limit).all()
                
                result = []
                for txn in transactions:
                    result.append({
                        'transaction_id': txn.transaction_id,
                        'transaction_type': txn.transaction_type,
                        'amount': txn.amount,
                        'status': txn.status,
                        'description': txn.description,
                        'pool_id': txn.pool_id,
                        'created_at': txn.created_at
                    })
                
                return result
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting transactions for user {user_id}: {e}")
            return []
    
    def create_star_purchase_keyboard(self) -> InlineKeyboardMarkup:
        """Create keyboard for star purchase options."""
        keyboard = []
        
        # Add package buttons in rows of 2
        packages = list(self.star_packages.items())
        for i in range(0, len(packages), 2):
            row = []
            for j in range(2):
                if i + j < len(packages):
                    pkg_key, pkg_data = packages[i + j]
                    button_text = f"⭐ {pkg_data['stars']} Stars"
                    callback_data = f"buy_stars_{pkg_key}"
                    row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.append(row)
        
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_deals")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def create_contribution_keyboard(self, pool_id: str) -> InlineKeyboardMarkup:
        """Create keyboard for pool contribution amounts."""
        keyboard = []
        
        # Add contribution amount buttons in rows of 3
        amounts = self.contribution_amounts
        for i in range(0, len(amounts), 3):
            row = []
            for j in range(3):
                if i + j < len(amounts):
                    amount = amounts[i + j]
                    button_text = f"⭐ {amount}"
                    callback_data = f"contribute_{pool_id}_{amount}"
                    row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard.append(row)
        
        # Add custom amount and back buttons
        keyboard.append([
            InlineKeyboardButton("💫 Custom Amount", callback_data=f"custom_contribute_{pool_id}"),
            InlineKeyboardButton("🔙 Back", callback_data=f"view_pool_{pool_id}")
        ])
        
        return InlineKeyboardMarkup(keyboard)


# Global instance
_payment_manager = None

def get_payment_manager() -> PaymentManager:
    """Get the global payment manager instance."""
    global _payment_manager
    if _payment_manager is None:
        _payment_manager = PaymentManager()
    return _payment_manager