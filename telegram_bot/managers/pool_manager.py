"""
Pool Manager - Manages community pooling system for content requests
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

# Import database components
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import get_db_session_sync
from shared.data.models import ContentPool, PoolContribution, UserProfile, Transaction

logger = logging.getLogger(__name__)


class PoolManager:
    """Manages community pooling system with dynamic pricing."""
    
    def __init__(self):
        """Initialize pool manager."""
        self.min_total_cost = 10  # Minimum total cost in Stars
        self.max_total_cost = 1000  # Maximum total cost in Stars
        self.default_pool_duration = 7  # Days until pool expires
        self.max_contributors = 100  # Maximum contributors per pool
        self.min_contributors = 2  # Minimum contributors to complete pool
        
    def create_pool(self, creator_name: str, content_title: str, content_description: str,
                   content_type: str, total_cost: int, created_by: int,
                   duration_days: int = None, request_id: str = None, 
                   max_contributors: int = None) -> Optional[str]:
        """
        Create a new content pool with dynamic pricing.
        
        Args:
            creator_name: Name of the creator
            content_title: Title/name of the content
            content_description: Description of the content
            content_type: Type of content ('photo_set', 'video', 'live_stream')
            total_cost: Total cost for the content in Stars
            created_by: User ID who created the pool
            duration_days: Days until pool expires (default: 7)
            request_id: Related request ID from CSV (optional)
            max_contributors: Maximum number of contributors (default: 100)
            
        Returns:
            pool_id if successful, None if failed
        """
        try:
            # Validate inputs
            if total_cost < self.min_total_cost or total_cost > self.max_total_cost:
                logger.error(f"Invalid total cost: {total_cost} (min: {self.min_total_cost}, max: {self.max_total_cost})")
                return None
            
            if not creator_name or not content_title:
                logger.error("Creator name and content title are required")
                return None
            
            # Set defaults
            max_contributors = max_contributors or self.max_contributors
            duration = duration_days or self.default_pool_duration
            
            # Calculate initial price per user (assuming max contributors)
            initial_price_per_user = max(1, total_cost // max_contributors)
            
            # Generate pool ID
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            pool_id = f"POOL-{timestamp}-{str(uuid.uuid4())[:8].upper()}"
            
            # Calculate expiration
            expires_at = datetime.now() + timedelta(days=duration)
            
            db = get_db_session_sync()
            try:
                # Create pool
                pool = ContentPool(
                    pool_id=pool_id,
                    creator_name=creator_name,
                    content_title=content_title,
                    content_description=content_description,
                    content_type=content_type,
                    total_cost=total_cost,
                    current_price_per_user=initial_price_per_user,
                    max_contributors=max_contributors,
                    created_by=created_by,
                    expires_at=expires_at,
                    request_id=request_id
                )
                
                db.add(pool)
                db.commit()
                
                logger.info(f"Created pool {pool_id} for {creator_name} - {content_title} (total cost: {total_cost} Stars)")
                return pool_id
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error creating pool: {e}")
            return None
    
    def get_pool(self, pool_id: str) -> Optional[Dict]:
        """
        Get pool details by ID.
        
        Returns:
            Pool data dict or None if not found
        """
        try:
            db = get_db_session_sync()
            try:
                pool = db.query(ContentPool).filter(ContentPool.pool_id == pool_id).first()
                if not pool:
                    return None
                
                # Calculate completion percentage
                completion_percentage = (pool.current_amount / pool.total_cost * 100) if pool.total_cost > 0 else 0
                
                return {
                    'pool_id': pool.pool_id,
                    'creator_name': pool.creator_name,
                    'content_title': pool.content_title,
                    'content_description': pool.content_description,
                    'content_type': pool.content_type,
                    'total_cost': pool.total_cost,
                    'current_amount': pool.current_amount,
                    'contributors_count': pool.contributors_count,
                    'max_contributors': pool.max_contributors,
                    'current_price_per_user': pool.current_price_per_user,
                    'completion_percentage': completion_percentage,
                    'status': pool.status,
                    'created_by': pool.created_by,
                    'expires_at': pool.expires_at,
                    'completed_at': pool.completed_at,
                    'content_url': pool.content_url,
                    'request_id': pool.request_id,
                    'created_at': pool.created_at
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting pool {pool_id}: {e}")
            return None
    
    def calculate_dynamic_price(self, total_cost: int, contributors_count: int, 
                              max_contributors: int) -> int:
        """
        Calculate dynamic price per user based on current contributors.
        
        The more people join, the cheaper it gets for everyone.
        Uses a logarithmic curve to ensure fair pricing.
        
        Args:
            total_cost: Total cost of the content
            contributors_count: Current number of contributors
            max_contributors: Maximum allowed contributors
            
        Returns:
            Price per user in Stars
        """
        import math
        
        if contributors_count >= max_contributors:
            # If at max capacity, split evenly
            return max(1, total_cost // max_contributors)
        
        # Calculate target contributors (how many we expect to join)
        # Start high and decrease as more people join
        if contributors_count == 0:
            # Initial price assumes 25% of max contributors will join
            target_contributors = max(2, max_contributors // 4)
        else:
            # As more join, we can be more optimistic about final count
            # Use logarithmic scaling to gradually reduce price
            progress_factor = contributors_count / max_contributors
            # Estimate final contributors based on current momentum
            estimated_final = min(max_contributors, 
                                contributors_count + (contributors_count * (1 + math.log(1 + progress_factor))))
            target_contributors = max(contributors_count + 1, int(estimated_final))
        
        # Calculate price per user
        price_per_user = max(1, total_cost // target_contributors)
        
        # Ensure we don't go below minimum viable price
        min_price = max(1, total_cost // max_contributors)
        price_per_user = max(min_price, price_per_user)
        
        return int(price_per_user)
    
    def contribute_to_pool(self, pool_id: str, user_id: int, 
                          payment_charge_id: str = None) -> Tuple[bool, str, int]:
        """
        Add a contribution to a pool using dynamic pricing.
        
        Args:
            pool_id: Pool ID to contribute to
            user_id: User making the contribution
            payment_charge_id: Telegram payment charge ID
            
        Returns:
            (success: bool, message: str, amount_charged: int)
        """
        try:
            db = get_db_session_sync()
            try:
                # Get pool
                pool = db.query(ContentPool).filter(ContentPool.pool_id == pool_id).first()
                if not pool:
                    return False, "Pool not found", 0
                
                # Check pool status
                if pool.status != 'active':
                    return False, f"Pool is {pool.status} and cannot accept contributions", 0
                
                # Check if pool expired
                if datetime.now() > pool.expires_at:
                    pool.status = 'expired'
                    db.commit()
                    return False, "Pool has expired", 0
                
                # Check if pool is full
                if pool.contributors_count >= pool.max_contributors:
                    return False, "Pool is full (maximum contributors reached)", 0
                
                # Check if user already contributed
                existing_contribution = db.query(PoolContribution).filter(
                    and_(
                        PoolContribution.pool_id == pool_id,
                        PoolContribution.user_id == user_id,
                        PoolContribution.status == 'completed'
                    )
                ).first()
                
                if existing_contribution:
                    return False, "You have already contributed to this pool", 0
                
                # Calculate current price for this user
                current_price = self.calculate_dynamic_price(
                    pool.total_cost, 
                    pool.contributors_count, 
                    pool.max_contributors
                )
                
                # Check if adding this contribution would complete the pool
                new_total = pool.current_amount + current_price
                if new_total >= pool.total_cost:
                    # Pool will be completed, adjust price to exact remaining amount
                    current_price = pool.total_cost - pool.current_amount
                
                # Create contribution record
                contribution_id = f"CONTRIB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                contribution = PoolContribution(
                    contribution_id=contribution_id,
                    user_id=user_id,
                    pool_id=pool_id,
                    amount=current_price,
                    payment_charge_id=payment_charge_id,
                    status='completed'
                )
                
                db.add(contribution)
                
                # Update pool totals
                pool.current_amount += current_price
                pool.contributors_count += 1
                
                # Recalculate price for next contributor
                pool.current_price_per_user = self.calculate_dynamic_price(
                    pool.total_cost,
                    pool.contributors_count,
                    pool.max_contributors
                )
                
                pool.completion_percentage = (pool.current_amount / pool.total_cost * 100)
                
                # Check if pool is completed
                if pool.current_amount >= pool.total_cost:
                    pool.status = 'completed'
                    pool.completed_at = datetime.now()
                
                # Update user profile
                user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                if user_profile:
                    user_profile.total_contributed += current_price
                    user_profile.pools_joined += 1
                else:
                    # Create user profile if doesn't exist
                    user_profile = UserProfile(
                        user_id=user_id,
                        total_contributed=current_price,
                        pools_joined=1
                    )
                    db.add(user_profile)
                
                # Create transaction record
                transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}"
                transaction = Transaction(
                    transaction_id=transaction_id,
                    user_id=user_id,
                    transaction_type='pool_contribution',
                    amount=current_price,
                    pool_id=pool_id,
                    contribution_id=contribution_id,
                    payment_charge_id=payment_charge_id,
                    status='completed',
                    description=f"Contribution to pool {pool_id} (dynamic price: {current_price} Stars)"
                )
                
                db.add(transaction)
                db.commit()
                
                completion_msg = ""
                if pool.status == 'completed':
                    completion_msg = " 🎉 Pool completed! Content will be unlocked soon."
                else:
                    # Show new price for next contributor
                    next_price = pool.current_price_per_user
                    completion_msg = f" Next contributor pays: {next_price} ⭐"
                
                logger.info(f"User {user_id} contributed {current_price} Stars to pool {pool_id}")
                return True, f"Contribution successful! You paid {current_price} ⭐{completion_msg}", current_price
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error contributing to pool {pool_id}: {e}")
            return False, "Failed to process contribution", 0
    
    def get_active_pools(self, limit: int = 10, creator_filter: str = None) -> List[Dict]:
        """
        Get list of active pools.
        
        Args:
            limit: Maximum number of pools to return
            creator_filter: Filter by creator name (optional)
            
        Returns:
            List of pool data dicts
        """
        try:
            db = get_db_session_sync()
            try:
                query = db.query(ContentPool).filter(
                    and_(
                        ContentPool.status == 'active',
                        ContentPool.expires_at > datetime.now()
                    )
                )
                
                if creator_filter:
                    query = query.filter(ContentPool.creator_name.ilike(f"%{creator_filter}%"))
                
                pools = query.order_by(desc(ContentPool.created_at)).limit(limit).all()
                
                result = []
                for pool in pools:
                    completion_percentage = (pool.current_amount / pool.target_amount * 100) if pool.target_amount > 0 else 0
                    result.append({
                        'pool_id': pool.pool_id,
                        'creator_name': pool.creator_name,
                        'content_title': pool.content_title,
                        'content_type': pool.content_type,
                        'target_amount': pool.target_amount,
                        'current_amount': pool.current_amount,
                        'contributors_count': pool.contributors_count,
                        'completion_percentage': completion_percentage,
                        'expires_at': pool.expires_at,
                        'created_at': pool.created_at
                    })
                
                return result
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting active pools: {e}")
            return []
    
    def get_pending_requests(self) -> List[Dict]:
        """
        Get pending content/creator requests that can be turned into pools.
        
        Returns:
            List of request data from CSV files
        """
        try:
            import csv
            import os
            
            requests = []
            
            # Read creator requests
            creator_requests_file = 'shared/data/requests/creator_requests.csv'
            if os.path.exists(creator_requests_file):
                with open(creator_requests_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('Status', '').lower() == 'pending':
                            requests.append({
                                'request_id': row.get('Request ID', ''),
                                'type': 'creator',
                                'platform': row.get('Platform', ''),
                                'username': row.get('Username', ''),
                                'user_id': row.get('User ID', ''),
                                'timestamp': row.get('Timestamp', ''),
                                'details': f"Creator: {row.get('Username', '')} on {row.get('Platform', '')}"
                            })
            
            # Read content requests
            content_requests_file = 'shared/data/requests/content_requests.csv'
            if os.path.exists(content_requests_file):
                with open(content_requests_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('Status', '').lower() == 'pending':
                            requests.append({
                                'request_id': row.get('Request ID', ''),
                                'type': 'content',
                                'platform': row.get('Platform', ''),
                                'username': row.get('Username', ''),
                                'user_id': row.get('User ID', ''),
                                'timestamp': row.get('Timestamp', ''),
                                'details': f"{row.get('Username', '')} - {row.get('Content Details', '')[:100]}"
                            })
            
            # Sort by timestamp (newest first)
            requests.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return requests[:20]  # Return latest 20 requests
            
        except Exception as e:
            logger.error(f"Error getting pending requests: {e}")
            return []
    
    def create_pool_from_request(self, request_id: str, total_cost: int, 
                               created_by: int, duration_days: int = None) -> Optional[str]:
        """
        Create a pool from an existing request.
        
        Args:
            request_id: Request ID from CSV
            total_cost: Total cost for the content
            created_by: Admin user ID
            duration_days: Pool duration
            
        Returns:
            pool_id if successful, None if failed
        """
        try:
            # Find the request in CSV files
            requests = self.get_pending_requests()
            request_data = None
            
            for req in requests:
                if req['request_id'] == request_id:
                    request_data = req
                    break
            
            if not request_data:
                logger.error(f"Request {request_id} not found")
                return None
            
            # Determine content type and title based on request type
            if request_data['type'] == 'creator':
                content_type = 'photo_set'  # Default for creator requests
                content_title = f"{request_data['username']} Content"
                content_description = f"Exclusive content from {request_data['username']} on {request_data['platform']}"
            else:
                content_type = 'video'  # Default for content requests
                content_title = f"{request_data['username']} - Specific Content"
                content_description = request_data['details']
            
            # Create the pool
            pool_id = self.create_pool(
                creator_name=request_data['username'],
                content_title=content_title,
                content_description=content_description,
                content_type=content_type,
                total_cost=total_cost,
                created_by=created_by,
                duration_days=duration_days,
                request_id=request_id
            )
            
            if pool_id:
                # Mark request as "In Pool" in CSV (optional - would need CSV update logic)
                logger.info(f"Created pool {pool_id} from request {request_id}")
            
            return pool_id
            
        except Exception as e:
            logger.error(f"Error creating pool from request {request_id}: {e}")
            return None
    
    def get_user_contributions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Get user's contribution history.
        
        Returns:
            List of contribution data dicts
        """
        try:
            db = get_db_session_sync()
            try:
                contributions = db.query(PoolContribution, ContentPool).join(
                    ContentPool, PoolContribution.pool_id == ContentPool.pool_id
                ).filter(
                    PoolContribution.user_id == user_id
                ).order_by(desc(PoolContribution.created_at)).limit(limit).all()
                
                result = []
                for contrib, pool in contributions:
                    result.append({
                        'contribution_id': contrib.contribution_id,
                        'pool_id': contrib.pool_id,
                        'amount': contrib.amount,
                        'status': contrib.status,
                        'created_at': contrib.created_at,
                        'creator_name': pool.creator_name,
                        'content_title': pool.content_title,
                        'pool_status': pool.status,
                        'pool_completion': (pool.current_amount / pool.target_amount * 100) if pool.target_amount > 0 else 0
                    })
                
                return result
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting user contributions for {user_id}: {e}")
            return []
    
    def complete_pool(self, pool_id: str, content_url: str, landing_page_id: str = None) -> bool:
        """
        Mark a pool as completed and set content URL.
        
        Args:
            pool_id: Pool ID to complete
            content_url: URL to the unlocked content
            landing_page_id: Landing page ID (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            db = get_db_session_sync()
            try:
                pool = db.query(ContentPool).filter(ContentPool.pool_id == pool_id).first()
                if not pool:
                    return False
                
                pool.status = 'completed'
                pool.completed_at = datetime.now()
                pool.content_url = content_url
                if landing_page_id:
                    pool.landing_page_id = landing_page_id
                
                db.commit()
                
                logger.info(f"Pool {pool_id} marked as completed with content URL")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error completing pool {pool_id}: {e}")
            return False
    
    def cancel_pool(self, pool_id: str, reason: str = None) -> bool:
        """
        Cancel a pool and process refunds.
        
        Args:
            pool_id: Pool ID to cancel
            reason: Reason for cancellation
            
        Returns:
            True if successful, False otherwise
        """
        try:
            db = get_db_session_sync()
            try:
                pool = db.query(ContentPool).filter(ContentPool.pool_id == pool_id).first()
                if not pool:
                    return False
                
                # Update pool status
                pool.status = 'cancelled'
                
                # Get all contributions for refund processing
                contributions = db.query(PoolContribution).filter(
                    and_(
                        PoolContribution.pool_id == pool_id,
                        PoolContribution.status == 'completed'
                    )
                ).all()
                
                # Mark contributions as refunded (actual refund processing would happen elsewhere)
                for contrib in contributions:
                    contrib.status = 'refunded'
                    
                    # Create refund transaction
                    transaction_id = f"REFUND-{datetime.now().strftime('%Y%m%d%H%M%S')}-{contrib.user_id}"
                    transaction = Transaction(
                        transaction_id=transaction_id,
                        user_id=contrib.user_id,
                        transaction_type='refund',
                        amount=contrib.amount,
                        pool_id=pool_id,
                        contribution_id=contrib.contribution_id,
                        status='completed',
                        description=f"Refund for cancelled pool {pool_id}: {reason or 'No reason provided'}"
                    )
                    db.add(transaction)
                
                db.commit()
                
                logger.info(f"Pool {pool_id} cancelled with {len(contributions)} refunds processed")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error cancelling pool {pool_id}: {e}")
            return False
    
    def cleanup_expired_pools(self) -> int:
        """
        Clean up expired pools and process refunds.
        
        Returns:
            Number of pools cleaned up
        """
        try:
            db = get_db_session_sync()
            try:
                # Find expired active pools
                expired_pools = db.query(ContentPool).filter(
                    and_(
                        ContentPool.status == 'active',
                        ContentPool.expires_at < datetime.now()
                    )
                ).all()
                
                cleaned_count = 0
                for pool in expired_pools:
                    # Cancel the pool (this handles refunds)
                    if self.cancel_pool(pool.pool_id, "Pool expired"):
                        cleaned_count += 1
                
                logger.info(f"Cleaned up {cleaned_count} expired pools")
                return cleaned_count
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error cleaning up expired pools: {e}")
            return 0


# Global instance
_pool_manager = None

def get_pool_manager() -> PoolManager:
    """Get the global pool manager instance."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = PoolManager()
    return _pool_manager