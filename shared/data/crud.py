"""
CRUD Operations - Database operations for Supabase PostgreSQL
Provides reusable functions for Create, Read, Update, Delete operations
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from shared.data.models import Creator, OnlyFansUser, OnlyFansPost, LandingPage

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
            last_scraped=datetime.utcnow()
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
            creator.last_scraped = datetime.utcnow()
            creator.updated_at = datetime.utcnow()
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
    Returns True if video was found and deleted, False otherwise.
    """
    try:
        all_creators = get_all_creators(db)
        video_deleted = False
        
        for creator in all_creators:
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
                        creator.updated_at = datetime.utcnow()
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
            logger.info(f"⚠️  Video not found in any creator: {video_url[:80]}...")
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
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
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
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=max_age_hours)
        
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
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
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
            expires_at = datetime.utcnow() + timedelta(hours=24)
        
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
            expires_at = datetime.utcnow() + timedelta(hours=24)
        
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
            existing.updated_at = datetime.utcnow()
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
        now = datetime.utcnow()
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
            landing_page.updated_at = datetime.utcnow()
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
        now = datetime.utcnow()
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
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        pages = db.query(LandingPage).filter(
            LandingPage.creator == creator,
            LandingPage.expires_at > datetime.utcnow(),
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
            LandingPage.expires_at > datetime.utcnow(),
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