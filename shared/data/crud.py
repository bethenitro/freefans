"""
CRUD Operations - Database operations for Supabase PostgreSQL
Provides reusable functions for Create, Read, Update, Delete operations
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from shared.data.models import Creator, OnlyFansUser, OnlyFansPost, LandingPage, UserProfile, ContentPool, PoolContribution, Transaction

logger = logging.getLogger(__name__)

# Creator CRUD Operations
def create_creator(db: Session, name: str, content: Dict[str, Any]) -> Creator:
    """Create a new creator record."""
    try:
        # Calculate post count from the correct field (SQLite uses 'items', not 'posts')
        post_count = len(content.get('items', []))
        
        # Skip creators with 0 items - don't save them to database
        if post_count == 0:
            logger.info(f"⏭️  Skipping creator {name} - no content items found")
            return None
        
        creator = Creator(
            name=name,
            content=json.dumps(content),
            post_count=post_count,
            last_scraped=datetime.now(timezone.utc)
        )
        db.add(creator)
        db.commit()
        db.refresh(creator)
        logger.info(f"✓ Created creator record for {name} ({post_count} items)")
        return creator
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create creator {name}: {e}")
        raise

def get_creator_by_name(db: Session, name: str) -> Optional[Creator]:
    """Get creator by name (case-insensitive)."""
    return db.query(Creator).filter(func.lower(Creator.name) == func.lower(name)).first()

def update_creator_content(db: Session, name: str, content: Dict[str, Any]) -> Optional[Creator]:
    """Update creator content."""
    try:
        # Calculate post count from the correct field (SQLite uses 'items', not 'posts')
        post_count = len(content.get('items', []))
        
        creator = get_creator_by_name(db, name)
        if creator:
            # If updated content has 0 items, delete the creator instead of updating
            if post_count == 0:
                logger.info(f"🗑️  Deleting creator {name} - no content items found")
                db.delete(creator)
                db.commit()
                return None
            
            creator.content = json.dumps(content)
            creator.post_count = post_count
            creator.last_scraped = datetime.now(timezone.utc)
            creator.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(creator)
            logger.info(f"✓ Updated creator content for {name} ({post_count} items)")
            return creator
        else:
            # Create new if doesn't exist (will skip if 0 items)
            return create_creator(db, name, content)
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to update creator {name}: {e}")
        raise

def get_creator_content(db: Session, name: str, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
    """Get creator content (no age restrictions)."""
    creator = get_creator_by_name(db, name)
    if not creator:
        return None
    
    try:
        content = json.loads(creator.content) if creator.content else None
        if content:
            # Add URL to the cached content for proper cache key generation
            # Generate URL from creator name (this matches the pattern used in scraping)
            creator_url = f"https://simpcity.cr/threads/{name.lower().replace(' ', '-').replace('_', '-')}.11680/"
            content['url'] = creator_url
        return content
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON content for creator {name}")
        return None

def delete_creator(db: Session, name: str) -> bool:
    """Delete creator by name."""
    try:
        creator = get_creator_by_name(db, name)
        if creator:
            db.delete(creator)
            db.commit()
            logger.info(f"✓ Deleted creator {name}")
            return True
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to delete creator {name}: {e}")
        raise

def delete_video_from_creator(db: Session, video_url: str) -> bool:
    """
    Delete a specific video from all creators' content.
    Optimized to search only creators whose content contains the URL.
    Returns True if video was found and deleted, False otherwise.
    """
    try:
        # Use SQL LIKE query to find only creators that might contain this URL
        # This is much faster than loading all creators
        from sqlalchemy import or_
        
        creators_with_video = db.query(Creator).filter(
            or_(
                Creator.content.like(f'%{video_url}%'),
                Creator.content.like(f'%{video_url.replace("https://", "http://")}%')
            )
        ).all()
        
        if not creators_with_video:
            logger.info(f"⚠️  Video not found in any creator (quick search): {video_url[:80]}...")
            return False
        
        logger.info(f"Found {len(creators_with_video)} creators that might contain the video")
        
        video_deleted = False
        
        for creator in creators_with_video:
            if not creator.content:
                continue
                
            try:
                content = json.loads(creator.content)
                items = content.get('items', [])
                original_count = len(items)
                
                # Filter out the video with matching URL
                filtered_items = [
                    item for item in items 
                    if item.get('url') != video_url and item.get('original_url') != video_url
                ]
                
                # If video was found and removed
                if len(filtered_items) < original_count:
                    content['items'] = filtered_items
                    
                    # Update the creator with new content
                    if len(filtered_items) == 0:
                        # If no items left, delete the creator
                        logger.info(f"🗑️  Deleting creator {creator.name} - no content after video removal")
                        db.delete(creator)
                        video_deleted = True
                    else:
                        # Update creator with filtered content
                        creator.content = json.dumps(content)
                        creator.post_count = len(filtered_items)
                        creator.updated_at = datetime.now(timezone.utc)
                        logger.info(f"✓ Removed video from creator {creator.name} ({original_count} → {len(filtered_items)} items)")
                        video_deleted = True
                        
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON content for creator {creator.name}")
                continue
        
        if video_deleted:
            db.commit()
            logger.info(f"✓ Successfully deleted video: {video_url[:80]}...")
            return True
        else:
            logger.info(f"⚠️  Video not found in searched creators: {video_url[:80]}...")
            return False
            
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to delete video {video_url}: {e}")
        raise

def get_all_creators(db: Session) -> List[Creator]:
    """Get all creators ordered by last update."""
    return db.query(Creator).order_by(desc(Creator.updated_at)).all()

def get_stale_creators(db: Session, max_age_hours: int = 24) -> List[Creator]:
    """Get creators that need to be refreshed (older than max_age_hours)."""
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        stale_creators = db.query(Creator).filter(
            Creator.last_scraped < cutoff_time
        ).order_by(desc(Creator.last_scraped)).all()
        
        logger.info(f"Found {len(stale_creators)} stale creators (older than {max_age_hours}h)")
        return stale_creators
    except Exception as e:
        logger.error(f"✗ Failed to get stale creators: {e}")
        return []

# OnlyFans User CRUD Operations
def create_onlyfans_user(db: Session, username: str, display_name: str = None) -> OnlyFansUser:
    """Create a new OnlyFans user record."""
    try:
        user = OnlyFansUser(username=username, display_name=display_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"✓ Created OnlyFans user record for {username}")
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create OnlyFans user {username}: {e}")
        raise

def get_onlyfans_user(db: Session, username: str) -> Optional[OnlyFansUser]:
    """Get OnlyFans user by username."""
    return db.query(OnlyFansUser).filter(OnlyFansUser.username == username).first()

def get_or_create_onlyfans_user(db: Session, username: str, display_name: str = None) -> OnlyFansUser:
    """Get existing OnlyFans user or create new one."""
    user = get_onlyfans_user(db, username)
    if not user:
        user = create_onlyfans_user(db, username, display_name)
    return user

# OnlyFans Posts CRUD Operations
def save_onlyfans_posts(db: Session, username: str, posts: List[Dict[str, Any]]) -> bool:
    """Save OnlyFans posts for a user."""
    try:
        # Ensure user exists
        get_or_create_onlyfans_user(db, username)
        
        # Delete existing posts for this user
        db.query(OnlyFansPost).filter(OnlyFansPost.username == username).delete()
        
        # Create new post records
        for post_data in posts:
            post = OnlyFansPost(
                username=username,
                post_id=str(post_data.get('id', '')),
                content=json.dumps(post_data)
            )
            db.add(post)
        
        db.commit()
        logger.info(f"✓ Saved {len(posts)} OnlyFans posts for {username}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to save OnlyFans posts for {username}: {e}")
        raise

def get_onlyfans_posts(db: Session, username: str, max_age_hours: int = 24) -> Optional[List[Dict[str, Any]]]:
    """Get OnlyFans posts for a user if within max age."""
    try:
        # Check if we have recent posts - handle timezone issues
        from datetime import timezone
        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) - timedelta(hours=max_age_hours)
        
        posts = db.query(OnlyFansPost).filter(
            OnlyFansPost.username == username,
            OnlyFansPost.updated_at >= cutoff_time
        ).order_by(desc(OnlyFansPost.updated_at)).all()
        
        if not posts:
            return None
        
        # Convert to list of dictionaries
        result = []
        for post in posts:
            try:
                post_data = json.loads(post.content) if post.content else {}
                result.append(post_data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON content for post {post.id}")
                continue
        
        return result if result else None
    except Exception as e:
        logger.error(f"✗ Failed to get OnlyFans posts for {username}: {e}")
        return None

def get_onlyfans_usernames(db: Session) -> List[str]:
    """Get all OnlyFans usernames."""
    try:
        users = db.query(OnlyFansUser).all()
        return [user.username for user in users]
    except Exception as e:
        logger.error(f"✗ Failed to get OnlyFans usernames: {e}")
        return []

# Statistics and Utility Functions
def get_database_stats(db: Session) -> Dict[str, Any]:
    """Get database statistics."""
    try:
        creator_count = db.query(Creator).count()
        onlyfans_user_count = db.query(OnlyFansUser).count()
        onlyfans_post_count = db.query(OnlyFansPost).count()
        
        return {
            'total_creators': creator_count,
            'total_onlyfans_users': onlyfans_user_count,
            'total_onlyfans_posts': onlyfans_post_count,
            'database_type': 'PostgreSQL (Supabase)'
        }
    except Exception as e:
        logger.error(f"✗ Failed to get database stats: {e}")
        return {
            'total_creators': 0,
            'total_onlyfans_users': 0,
            'total_onlyfans_posts': 0,
            'database_type': 'PostgreSQL (Supabase) - Error'
        }

def get_cached_creator_names(db: Session) -> set:
    """Get set of all cached creator names for fast comparison (optimized)."""
    try:
        # Only select the name column for minimal data transfer
        result = db.query(Creator.name).all()
        # Convert to lowercase set for case-insensitive comparison
        return {name[0].lower() for name in result}
    except Exception as e:
        logger.error(f"✗ Failed to get cached creator names: {e}")
        return set()

def get_cached_creator_names_batched(db: Session, creator_names: List[str], batch_size: int = 500) -> set:
    """
    Get cached creator names using batched IN queries for optimal performance.
    
    Args:
        db: Database session
        creator_names: List of creator names to check
        batch_size: Size of each batch for IN query
        
    Returns:
        Set of cached creator names (lowercase)
    """
    try:
        existing_names = set()
        
        # Process in batches to avoid query size limits
        for i in range(0, len(creator_names), batch_size):
            batch = creator_names[i:i + batch_size]
            
            # Use case-insensitive IN query with only name column
            result = db.query(Creator.name).filter(
                func.lower(Creator.name).in_([name.lower() for name in batch])
            ).all()
            
            # Add to existing set (convert to lowercase)
            existing_names.update(name[0].lower() for name in result)
            
            logger.debug(f"Processed batch {i//batch_size + 1}: {len(result)} matches found")
        
        logger.info(f"Found {len(existing_names)} existing creators out of {len(creator_names)} checked")
        return existing_names
        
    except Exception as e:
        logger.error(f"✗ Failed to get cached creator names (batched): {e}")
        return set()

def get_creators_needing_refresh(db: Session, creator_names: List[str], max_age_hours: int = 24, batch_size: int = 500) -> List[str]:
    """
    Get creator names that need refresh using batched queries.
    
    Args:
        db: Database session
        creator_names: List of creator names to check
        max_age_hours: Maximum age in hours before refresh needed
        batch_size: Size of each batch for IN query
        
    Returns:
        List of creator names that need refresh
    """
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stale_names = []
        
        # Process in batches
        for i in range(0, len(creator_names), batch_size):
            batch = creator_names[i:i + batch_size]
            
            # Find creators that are stale or don't exist
            result = db.query(Creator.name).filter(
                func.lower(Creator.name).in_([name.lower() for name in batch]),
                Creator.last_scraped < cutoff_time
            ).all()
            
            stale_names.extend(name[0] for name in result)
        
        logger.info(f"Found {len(stale_names)} creators needing refresh")
        return stale_names
        
    except Exception as e:
        logger.error(f"✗ Failed to get creators needing refresh: {e}")
        return []

def cleanup_empty_creators(db: Session) -> int:
    """
    Remove creators with 0 items from the database.
    
    Returns:
        Number of creators removed
    """
    try:
        # Find creators with 0 post_count
        empty_creators = db.query(Creator).filter(Creator.post_count == 0).all()
        count = len(empty_creators)
        
        if count > 0:
            # Delete them
            db.query(Creator).filter(Creator.post_count == 0).delete()
            db.commit()
            logger.info(f"✓ Cleaned up {count} empty creators from database")
        else:
            logger.info("✓ No empty creators found to clean up")
        
        return count
        
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to cleanup empty creators: {e}")
        return 0

# Landing Page CRUD Operations
def create_landing_page(db: Session, short_id: str, creator: str, title: str, 
                       content_type: str, original_url: str, preview_url: Optional[str] = None,
                       thumbnail_url: Optional[str] = None, expires_at: datetime = None) -> LandingPage:
    """Create a new landing page record."""
    try:
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        landing_page = LandingPage(
            short_id=short_id,
            creator=creator,
            title=title,
            content_type=content_type,
            original_url=original_url,
            preview_url=preview_url,
            thumbnail_url=thumbnail_url,
            expires_at=expires_at
        )
        db.add(landing_page)
        db.commit()
        db.refresh(landing_page)
        logger.info(f"✓ Created landing page record for {short_id}")
        return landing_page
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create landing page {short_id}: {e}")
        raise

def upsert_landing_page(db: Session, short_id: str, creator: str, title: str, 
                        content_type: str, original_url: str, preview_url: Optional[str] = None,
                        thumbnail_url: Optional[str] = None, expires_at: datetime = None) -> LandingPage:
    """Create or update a landing page record (upsert)."""
    try:
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Check if record already exists
        existing = db.query(LandingPage).filter(LandingPage.short_id == short_id).first()
        
        if existing:
            # Update existing record
            existing.creator = creator
            existing.title = title
            existing.content_type = content_type
            existing.original_url = original_url
            existing.preview_url = preview_url
            existing.thumbnail_url = thumbnail_url
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            logger.info(f"✓ Updated landing page record for {short_id}")
            return existing
        else:
            # Create new record
            landing_page = LandingPage(
                short_id=short_id,
                creator=creator,
                title=title,
                content_type=content_type,
                original_url=original_url,
                preview_url=preview_url,
                thumbnail_url=thumbnail_url,
                expires_at=expires_at
            )
            db.add(landing_page)
            db.commit()
            db.refresh(landing_page)
            logger.info(f"✓ Created landing page record for {short_id}")
            return landing_page
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to upsert landing page {short_id}: {e}")
        raise

def get_landing_page(db: Session, short_id: str) -> Optional[LandingPage]:
    """Get landing page by short_id if not expired."""
    try:
        # Use timezone-aware datetime for consistency
        now = datetime.now(timezone.utc)
        landing_page = db.query(LandingPage).filter(
            LandingPage.short_id == short_id,
            LandingPage.expires_at > now
        ).first()
        return landing_page
    except Exception as e:
        logger.error(f"✗ Failed to get landing page {short_id}: {e}")
        return None

def update_landing_page(db: Session, short_id: str, **kwargs) -> Optional[LandingPage]:
    """Update landing page data."""
    try:
        landing_page = db.query(LandingPage).filter(LandingPage.short_id == short_id).first()
        if landing_page:
            for key, value in kwargs.items():
                if hasattr(landing_page, key):
                    setattr(landing_page, key, value)
            landing_page.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(landing_page)
            logger.info(f"✓ Updated landing page {short_id}")
            return landing_page
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to update landing page {short_id}: {e}")
        raise

def delete_landing_page(db: Session, short_id: str) -> bool:
    """Delete landing page by short_id."""
    try:
        landing_page = db.query(LandingPage).filter(LandingPage.short_id == short_id).first()
        if landing_page:
            db.delete(landing_page)
            db.commit()
            logger.info(f"✓ Deleted landing page {short_id}")
            return True
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to delete landing page {short_id}: {e}")
        raise

def cleanup_expired_landing_pages(db: Session) -> int:
    """Remove expired landing pages from the database."""
    try:
        now = datetime.now(timezone.utc)
        expired_pages = db.query(LandingPage).filter(LandingPage.expires_at <= now).all()
        count = len(expired_pages)
        
        if count > 0:
            db.query(LandingPage).filter(LandingPage.expires_at <= now).delete()
            db.commit()
            logger.info(f"✓ Cleaned up {count} expired landing pages from database")
        else:
            logger.info("✓ No expired landing pages found to clean up")
        
        return count
        
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to cleanup expired landing pages: {e}")
        return 0

def get_landing_pages_by_creator(db: Session, creator: str, max_age_hours: int = 24) -> List[LandingPage]:
    """Get all non-expired landing pages for a creator."""
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        pages = db.query(LandingPage).filter(
            LandingPage.creator == creator,
            LandingPage.expires_at > datetime.now(timezone.utc),
            LandingPage.created_at >= cutoff_time
        ).order_by(desc(LandingPage.created_at)).all()
        return pages
    except Exception as e:
        logger.error(f"✗ Failed to get landing pages for creator {creator}: {e}")
        return []

def get_recent_landing_pages(db: Session, cutoff_time: datetime) -> List[LandingPage]:
    """Get all non-expired landing pages created after cutoff_time."""
    try:
        pages = db.query(LandingPage).filter(
            LandingPage.expires_at > datetime.now(timezone.utc),
            LandingPage.created_at >= cutoff_time
        ).order_by(desc(LandingPage.created_at)).all()
        return pages
    except Exception as e:
        logger.error(f"✗ Failed to get recent landing pages: {e}")
        return []

def get_random_creator_with_content(db: Session, min_items: int = 25) -> Optional[Creator]:
    """Get a random creator with at least min_items content items."""
    try:
        # Get a random creator with sufficient content
        creator = db.query(Creator).filter(
            Creator.post_count >= min_items
        ).order_by(func.random()).first()
        
        if creator:
            logger.info(f"✓ Found random creator: {creator.name} ({creator.post_count} items)")
        else:
            logger.info(f"⚠️ No creators found with at least {min_items} items")
        
        return creator
    except Exception as e:
        logger.error(f"✗ Failed to get random creator: {e}")
        return None

# Pool System CRUD Operations

def create_user_profile(db: Session, user_id: int, username: str = None) -> UserProfile:
    """Create a new user profile."""
    try:
        profile = UserProfile(user_id=user_id, username=username)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info(f"✓ Created user profile for {user_id}")
        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create user profile {user_id}: {e}")
        raise

def get_user_profile(db: Session, user_id: int) -> Optional[UserProfile]:
    """Get user profile by user_id."""
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

def get_or_create_user_profile(db: Session, user_id: int, username: str = None) -> UserProfile:
    """Get existing user profile or create new one."""
    profile = get_user_profile(db, user_id)
    if not profile:
        profile = create_user_profile(db, user_id, username)
    elif username and profile.username != username:
        profile.username = username
        db.commit()
    return profile

def update_user_balance(db: Session, user_id: int, amount_change: int, description: str = None) -> bool:
    """Update user balance (positive for add, negative for deduct)."""
    try:
        profile = get_or_create_user_profile(db, user_id)
        
        if amount_change < 0 and profile.balance < abs(amount_change):
            return False  # Insufficient balance
        
        profile.balance += amount_change
        if amount_change > 0:
            # Adding balance doesn't count as spending
            pass
        else:
            # Deducting balance counts as spending
            profile.total_spent += abs(amount_change)
        
        db.commit()
        logger.info(f"✓ Updated balance for user {user_id}: {amount_change:+d} Stars")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to update balance for user {user_id}: {e}")
        return False

def create_content_pool(db: Session, pool_id: str, creator_name: str, content_title: str,
                       content_description: str, content_type: str, total_cost: int,
                       created_by: int, expires_at: datetime, max_contributors: int = 100,
                       request_id: str = None) -> ContentPool:
    """Create a new content pool with dynamic pricing."""
    try:
        # Calculate initial price per user
        initial_price = max(1, total_cost // max_contributors)
        
        pool = ContentPool(
            pool_id=pool_id,
            creator_name=creator_name,
            content_title=content_title,
            content_description=content_description,
            content_type=content_type,
            total_cost=total_cost,
            current_price_per_user=initial_price,
            max_contributors=max_contributors,
            created_by=created_by,
            expires_at=expires_at,
            request_id=request_id
        )
        db.add(pool)
        db.commit()
        db.refresh(pool)
        logger.info(f"✓ Created content pool {pool_id}")
        return pool
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create content pool {pool_id}: {e}")
        raise

def get_content_pool(db: Session, pool_id: str) -> Optional[ContentPool]:
    """Get content pool by pool_id."""
    return db.query(ContentPool).filter(ContentPool.pool_id == pool_id).first()

def get_active_pools(db: Session, limit: int = 10, creator_filter: str = None) -> List[ContentPool]:
    """Get active content pools."""
    try:
        query = db.query(ContentPool).filter(
            ContentPool.status == 'active',
            ContentPool.expires_at > datetime.now(timezone.utc)
        )
        
        if creator_filter:
            query = query.filter(ContentPool.creator_name.ilike(f"%{creator_filter}%"))
        
        pools = query.order_by(desc(ContentPool.created_at)).limit(limit).all()
        return pools
    except Exception as e:
        logger.error(f"✗ Failed to get active pools: {e}")
        return []

def update_pool_progress(db: Session, pool_id: str, amount_added: int) -> Optional[ContentPool]:
    """Update pool progress when contribution is made."""
    try:
        pool = get_content_pool(db, pool_id)
        if not pool:
            return None
        
        pool.current_amount += amount_added
        pool.contributors_count += 1
        pool.completion_percentage = (pool.current_amount / pool.total_cost * 100) if pool.total_cost > 0 else 0
        
        # Check if pool is completed
        if pool.current_amount >= pool.total_cost:
            pool.status = 'completed'
            pool.completed_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(pool)
        logger.info(f"✓ Updated pool {pool_id} progress: {pool.current_amount}/{pool.total_cost}")
        return pool
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to update pool progress {pool_id}: {e}")
        raise

def complete_pool(db: Session, pool_id: str, content_url: str, landing_page_id: str = None) -> bool:
    """Mark pool as completed and set content URL."""
    try:
        pool = get_content_pool(db, pool_id)
        if not pool:
            return False
        
        pool.status = 'completed'
        pool.completed_at = datetime.now(timezone.utc)
        pool.content_url = content_url
        if landing_page_id:
            pool.landing_page_id = landing_page_id
        
        db.commit()
        logger.info(f"✓ Completed pool {pool_id}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to complete pool {pool_id}: {e}")
        return False

def cancel_pool(db: Session, pool_id: str) -> bool:
    """Cancel a pool and mark contributions for refund."""
    try:
        pool = get_content_pool(db, pool_id)
        if not pool:
            return False
        
        pool.status = 'cancelled'
        
        # Mark all contributions as refunded
        contributions = db.query(PoolContribution).filter(
            PoolContribution.pool_id == pool_id,
            PoolContribution.status == 'completed'
        ).all()
        
        for contrib in contributions:
            contrib.status = 'refunded'
        
        db.commit()
        logger.info(f"✓ Cancelled pool {pool_id} with {len(contributions)} refunds")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to cancel pool {pool_id}: {e}")
        return False

def create_pool_contribution(db: Session, contribution_id: str, user_id: int, pool_id: str,
                           amount: int, payment_charge_id: str = None) -> PoolContribution:
    """Create a new pool contribution."""
    try:
        contribution = PoolContribution(
            contribution_id=contribution_id,
            user_id=user_id,
            pool_id=pool_id,
            amount=amount,
            payment_charge_id=payment_charge_id,
            status='completed'
        )
        db.add(contribution)
        db.commit()
        db.refresh(contribution)
        logger.info(f"✓ Created pool contribution {contribution_id}")
        return contribution
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create pool contribution {contribution_id}: {e}")
        raise

def get_user_contributions(db: Session, user_id: int, limit: int = 10) -> List[tuple]:
    """Get user's pool contributions with pool details."""
    try:
        contributions = db.query(PoolContribution, ContentPool).join(
            ContentPool, PoolContribution.pool_id == ContentPool.pool_id
        ).filter(
            PoolContribution.user_id == user_id
        ).order_by(desc(PoolContribution.created_at)).limit(limit).all()
        
        return contributions
    except Exception as e:
        logger.error(f"✗ Failed to get user contributions for {user_id}: {e}")
        return []

def get_pool_contributors(db: Session, pool_id: str) -> List[PoolContribution]:
    """Get all contributors for a pool."""
    try:
        contributions = db.query(PoolContribution).filter(
            PoolContribution.pool_id == pool_id,
            PoolContribution.status == 'completed'
        ).order_by(desc(PoolContribution.created_at)).all()
        
        return contributions
    except Exception as e:
        logger.error(f"✗ Failed to get pool contributors for {pool_id}: {e}")
        return []

def create_transaction(db: Session, transaction_id: str, user_id: int, transaction_type: str,
                      amount: int, pool_id: str = None, contribution_id: str = None,
                      payment_charge_id: str = None, description: str = None) -> Transaction:
    """Create a new transaction record."""
    try:
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id,
            transaction_type=transaction_type,
            amount=amount,
            pool_id=pool_id,
            contribution_id=contribution_id,
            payment_charge_id=payment_charge_id,
            status='completed',
            description=description
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        logger.info(f"✓ Created transaction {transaction_id}")
        return transaction
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to create transaction {transaction_id}: {e}")
        raise

def get_user_transactions(db: Session, user_id: int, limit: int = 10) -> List[Transaction]:
    """Get user's transaction history."""
    try:
        transactions = db.query(Transaction).filter(
            Transaction.user_id == user_id
        ).order_by(desc(Transaction.created_at)).limit(limit).all()
        
        return transactions
    except Exception as e:
        logger.error(f"✗ Failed to get user transactions for {user_id}: {e}")
        return []

def cleanup_expired_pools(db: Session) -> int:
    """Clean up expired pools and process refunds."""
    try:
        now = datetime.now(timezone.utc)
        expired_pools = db.query(ContentPool).filter(
            ContentPool.status == 'active',
            ContentPool.expires_at < now
        ).all()
        
        count = 0
        for pool in expired_pools:
            if cancel_pool(db, pool.pool_id):
                count += 1
        
        logger.info(f"✓ Cleaned up {count} expired pools")
        return count
    except Exception as e:
        logger.error(f"✗ Failed to cleanup expired pools: {e}")
        return 0

def get_pool_stats(db: Session) -> Dict[str, Any]:
    """Get pool system statistics."""
    try:
        total_pools = db.query(ContentPool).count()
        active_pools = db.query(ContentPool).filter(ContentPool.status == 'active').count()
        completed_pools = db.query(ContentPool).filter(ContentPool.status == 'completed').count()
        total_contributions = db.query(PoolContribution).count()
        total_users = db.query(UserProfile).count()
        
        # Calculate total Stars in system
        total_stars_result = db.query(func.sum(UserProfile.balance)).scalar()
        total_stars = total_stars_result or 0
        
        # Calculate total contributed
        total_contributed_result = db.query(func.sum(PoolContribution.amount)).filter(
            PoolContribution.status == 'completed'
        ).scalar()
        total_contributed = total_contributed_result or 0
        
        return {
            'total_pools': total_pools,
            'active_pools': active_pools,
            'completed_pools': completed_pools,
            'total_contributions': total_contributions,
            'total_users': total_users,
            'total_stars_in_system': total_stars,
            'total_stars_contributed': total_contributed
        }
    except Exception as e:
        logger.error(f"✗ Failed to get pool stats: {e}")
        return {
            'total_pools': 0,
            'active_pools': 0,
            'completed_pools': 0,
            'total_contributions': 0,
            'total_users': 0,
            'total_stars_in_system': 0,
            'total_stars_contributed': 0
        }