"""
Dual Cache Manager - Enhanced caching system with SQLite + Supabase support
Maintains backward compatibility while adding remote PostgreSQL storage
"""

import logging
import sys
from typing import Optional, Dict, List, Any
from pathlib import Path
from .cache_manager import CacheManager

# Add project root to path for shared imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import init_database, create_tables, get_db_session_sync, is_database_available
from shared.data import crud
from shared.data.models import Creator, OnlyFansUser, OnlyFansPost

logger = logging.getLogger(__name__)

class DualCacheManager(CacheManager):
    """
    Enhanced cache manager that stores data in both SQLite (local) and Supabase (remote).
    Maintains full backward compatibility with existing CacheManager interface.
    """
    
    def __init__(self, db_path: str = None):
        """Initialize dual cache manager with both SQLite and Supabase."""
        # Initialize parent SQLite cache manager (it handles the default path)
        super().__init__(db_path)
        
        # Initialize Supabase connection
        self.supabase_available = False
        self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase database connection."""
        try:
            if init_database():
                if create_tables():
                    self.supabase_available = True
                    logger.info("✓ Dual cache manager: Supabase integration enabled")
                else:
                    logger.warning("⚠ Dual cache manager: Supabase tables creation failed")
            else:
                logger.info("ℹ Dual cache manager: Supabase integration disabled")
        except Exception as e:
            logger.error(f"✗ Dual cache manager: Supabase initialization failed: {e}")
            self.supabase_available = False
    
    def _sync_to_supabase(self, operation: str, **kwargs):
        """Sync operation to Supabase if available."""
        if not self.supabase_available:
            return
        
        try:
            db = get_db_session_sync()
            try:
                if operation == 'save_creator':
                    crud.update_creator_content(db, kwargs['creator_name'], kwargs['content'])
                elif operation == 'save_onlyfans_posts':
                    crud.save_onlyfans_posts(db, kwargs['username'], kwargs['posts'])
                elif operation == 'delete_creator':
                    crud.delete_creator(db, kwargs['creator_name'])
                
                logger.debug(f"✓ Synced {operation} to Supabase")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to sync {operation} to Supabase: {e}")
    
    def _get_from_supabase(self, operation: str, **kwargs) -> Optional[Any]:
        """Get data from Supabase if available."""
        if not self.supabase_available:
            return None
        
        try:
            db = get_db_session_sync()
            try:
                if operation == 'get_creator':
                    return crud.get_creator_content(db, kwargs['creator_name'], kwargs.get('max_age_hours', 24))
                elif operation == 'get_onlyfans_posts':
                    return crud.get_onlyfans_posts(db, kwargs['username'], kwargs.get('max_age_hours', 24))
                
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to get {operation} from Supabase: {e}")
            return None
    
    # Override parent methods to add Supabase sync
    
    def save_creator_cache(self, creator_name: str, url: str, content_data: Dict):
        """Save creator cache to both SQLite and Supabase."""
        # Save to SQLite first (existing functionality)
        super().save_creator_cache(creator_name, url, content_data)
        
        # Sync to Supabase (convert to the format expected by Supabase)
        try:
            self._sync_to_supabase('save_creator', creator_name=creator_name, content=content_data)
        except Exception as e:
            logger.error(f"Failed to sync creator {creator_name} to Supabase: {e}")
    
    def get_creator_cache(self, creator_name: str, max_age_hours: int = 24) -> Optional[Dict]:
        """Get creator cache from SQLite first, fallback to Supabase."""
        # Try SQLite first (existing functionality)
        result = super().get_creator_cache(creator_name, max_age_hours)
        
        # If not found in SQLite, try Supabase
        if result is None and self.supabase_available:
            logger.debug(f"Trying Supabase for creator {creator_name}")
            supabase_result = self._get_from_supabase('get_creator', creator_name=creator_name, max_age_hours=max_age_hours)
            
            if supabase_result:
                # Save to SQLite for faster future access
                # We need to extract the URL from the supabase result or use a default
                url = supabase_result.get('url', f'https://simpcity.su/search/{creator_name}')
                super().save_creator_cache(creator_name, url, supabase_result)
                logger.info(f"✓ Retrieved creator {creator_name} from Supabase and cached locally")
                return supabase_result
        
        return result
    
    def save_onlyfans_posts(self, username: str, posts: List[Dict[str, Any]]):
        """Save OnlyFans posts to both SQLite and Supabase."""
        # Save to SQLite first (existing functionality)
        super().save_onlyfans_posts(username, posts)
        
        # Sync to Supabase
        try:
            self._sync_to_supabase('save_onlyfans_posts', username=username, posts=posts)
        except Exception as e:
            logger.error(f"Failed to sync OnlyFans posts for {username} to Supabase: {e}")
    
    def get_onlyfans_posts(self, username: str, max_age_hours: int = 24) -> Optional[List[Dict[str, Any]]]:
        """Get OnlyFans posts from SQLite first, fallback to Supabase."""
        # Try SQLite first (existing functionality)
        result = super().get_onlyfans_posts(username, max_age_hours)
        
        # If not found in SQLite, try Supabase
        if result is None and self.supabase_available:
            logger.debug(f"Trying Supabase for OnlyFans posts: {username}")
            supabase_result = self._get_from_supabase('get_onlyfans_posts', username=username, max_age_hours=max_age_hours)
            
            if supabase_result:
                # Save to SQLite for faster future access
                super().save_onlyfans_posts(username, supabase_result)
                logger.info(f"✓ Retrieved OnlyFans posts for {username} from Supabase and cached locally")
                return supabase_result
        
        return result
    
    def delete_creator_cache(self, creator_name: str):
        """Delete creator cache from both SQLite and Supabase."""
        # Delete from SQLite first (existing functionality)
        super().delete_creator_cache(creator_name)
        
        # Sync deletion to Supabase
        try:
            self._sync_to_supabase('delete_creator', creator_name=creator_name)
        except Exception as e:
            logger.error(f"Failed to delete creator {creator_name} from Supabase: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get combined cache statistics from both SQLite and Supabase."""
        # Get SQLite stats (existing functionality)
        sqlite_stats = super().get_cache_stats()
        
        # Add Supabase stats if available
        if self.supabase_available:
            try:
                db = get_db_session_sync()
                try:
                    supabase_stats = crud.get_database_stats(db)
                    
                    # Combine stats
                    combined_stats = sqlite_stats.copy()
                    combined_stats.update({
                        'supabase_enabled': True,
                        'supabase_creators': supabase_stats.get('total_creators', 0),
                        'supabase_onlyfans_users': supabase_stats.get('total_onlyfans_users', 0),
                        'supabase_onlyfans_posts': supabase_stats.get('total_onlyfans_posts', 0),
                        'storage_type': 'Dual (SQLite + Supabase)'
                    })
                    
                    return combined_stats
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"✗ Failed to get Supabase stats: {e}")
        
        # Return SQLite stats with Supabase disabled indicator
        sqlite_stats['supabase_enabled'] = False
        sqlite_stats['storage_type'] = 'SQLite only'
        return sqlite_stats
    
    def is_supabase_available(self) -> bool:
        """Check if Supabase integration is available."""
        return self.supabase_available and is_database_available()
    
    def force_sync_to_supabase(self) -> Dict[str, int]:
        """Force sync all SQLite data to Supabase (useful for migration)."""
        if not self.supabase_available:
            return {'error': 'Supabase not available'}
        
        synced_creators = 0
        synced_posts = 0
        errors = 0
        skipped_empty = 0
        
        try:
            # Get all creators from SQLite
            creators = self.get_all_cached_creators()
            logger.info(f"Found {len(creators)} creators to potentially sync")
            
            for creator_data in creators:
                try:
                    # Get full creator content
                    content = self.get_creator_cache(creator_data['name'], max_age_hours=999999)  # Get regardless of age
                    if content and content.get('items') and len(content.get('items', [])) > 0:
                        # Only sync creators that have actual content
                        self._sync_to_supabase('save_creator', creator_name=creator_data['name'], content=content)
                        synced_creators += 1
                        logger.info(f"✓ Synced creator {creator_data['name']} ({len(content.get('items', []))} items)")
                    else:
                        skipped_empty += 1
                        logger.debug(f"Skipped empty creator: {creator_data['name']}")
                except Exception as e:
                    logger.error(f"Failed to sync creator {creator_data['name']}: {e}")
                    errors += 1
            
            # Get all OnlyFans usernames from SQLite
            onlyfans_usernames = self.get_onlyfans_usernames()
            logger.info(f"Found {len(onlyfans_usernames)} OnlyFans users to potentially sync")
            
            for username in onlyfans_usernames:
                try:
                    posts = self.get_onlyfans_posts(username, max_age_hours=999999)  # Get regardless of age
                    if posts and len(posts) > 0:
                        # Only sync users that have actual posts
                        self._sync_to_supabase('save_onlyfans_posts', username=username, posts=posts)
                        synced_posts += len(posts)
                        logger.info(f"✓ Synced OnlyFans user {username} ({len(posts)} posts)")
                    else:
                        logger.debug(f"Skipped empty OnlyFans user: {username}")
                except Exception as e:
                    logger.error(f"Failed to sync OnlyFans posts for {username}: {e}")
                    errors += 1
            
            logger.info(f"✓ Force sync completed: {synced_creators} creators, {synced_posts} posts, {errors} errors, {skipped_empty} empty creators skipped")
            
            return {
                'synced_creators': synced_creators,
                'synced_posts': synced_posts,
                'errors': errors,
                'skipped_empty': skipped_empty
            }
            
        except Exception as e:
            logger.error(f"✗ Force sync failed: {e}")
            return {'error': str(e)}
    
    def clear_supabase_and_resync(self) -> Dict[str, Any]:
        """Clear all Supabase data and perform a complete resync from SQLite."""
        if not self.supabase_available:
            return {'error': 'Supabase not available'}
        
        try:
            db = get_db_session_sync()
            try:
                # Clear all existing data in Supabase
                logger.info("Clearing existing Supabase data...")
                db.query(OnlyFansPost).delete()
                db.query(OnlyFansUser).delete()
                db.query(Creator).delete()
                db.commit()
                logger.info("✓ Cleared all existing Supabase data")
                
                # Now perform a complete sync
                return self.force_sync_to_supabase()
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Clear and resync failed: {e}")
            return {'error': str(e)}