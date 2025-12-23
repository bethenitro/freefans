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
from shared.data.models import Creator, OnlyFansUser, OnlyFansPost

logger = logging.getLogger(__name__)

# Creator CRUD Operations
def create_creator(db: Session, name: str, content: Dict[str, Any]) -> Creator:
    """Create a new creator record."""
    try:
        # Calculate post count from the correct field (SQLite uses 'items', not 'posts')
        post_count = len(content.get('items', []))
        
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
        creator = get_creator_by_name(db, name)
        if creator:
            # Calculate post count from the correct field (SQLite uses 'items', not 'posts')
            post_count = len(content.get('items', []))
            
            creator.content = json.dumps(content)
            creator.post_count = post_count
            creator.last_scraped = datetime.utcnow()
            creator.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(creator)
            logger.info(f"✓ Updated creator content for {name} ({post_count} items)")
            return creator
        else:
            # Create new if doesn't exist
            return create_creator(db, name, content)
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to update creator {name}: {e}")
        raise

def get_creator_content(db: Session, name: str, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
    """Get creator content if within max age."""
    creator = get_creator_by_name(db, name)
    if not creator:
        return None
    
    # Check if content is fresh enough
    if creator.last_scraped:
        age = datetime.utcnow() - creator.last_scraped
        if age.total_seconds() > max_age_hours * 3600:
            logger.info(f"Creator {name} content is stale ({age.total_seconds()/3600:.1f}h old)")
            return None
    
    try:
        return json.loads(creator.content) if creator.content else None
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

def get_all_creators(db: Session) -> List[Creator]:
    """Get all creators ordered by last update."""
    return db.query(Creator).order_by(desc(Creator.updated_at)).all()

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
        # Check if we have recent posts
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
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