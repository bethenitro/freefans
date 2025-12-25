#!/usr/bin/env python3
"""
Cache Manager Factory

Provides Supabase-only cache manager for the application.
"""

import os
from decouple import config


def get_cache_manager():
    """
    Factory function to get the appropriate cache manager based on configuration.
    
    Returns:
        SupabaseCacheManager: Supabase-only cache manager instance
    """
    print("☁️  Using SUPABASE cache storage (PostgreSQL only)")
    return SupabaseCacheManager()


class SupabaseCacheManager:
    """
    Supabase-only cache manager that only uses PostgreSQL storage.
    No SQLite dependency - pure Supabase implementation.
    """
    
    def __init__(self):
        """Initialize Supabase-only cache manager."""
        import sys
        from pathlib import Path
        
        # Add project root to path for shared imports
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root))
        
        from shared.config.database import init_database, create_tables, is_database_available
        
        self.supabase_available = False
        self._init_supabase()
        print("☁️  Supabase-only cache manager initialized")
    
    def _init_supabase(self):
        """Initialize Supabase database connection."""
        import logging
        from shared.config.database import init_database, create_tables
        
        logger = logging.getLogger(__name__)
        
        try:
            if init_database():
                if create_tables():
                    self.supabase_available = True
                    logger.info("✓ Supabase integration enabled")
                else:
                    logger.warning("⚠ Supabase tables creation failed")
            else:
                logger.info("ℹ Supabase integration disabled")
        except Exception as e:
            logger.error(f"✗ Supabase initialization failed: {e}")
            self.supabase_available = False
    
    def save_creator_cache(self, creator_name: str, url: str, content_data: dict, 
                          post_count: int = 0, preview_images: list = None, 
                          video_links: list = None) -> bool:
        """Save creator cache to Supabase only."""
        try:
            if not self.supabase_available:
                print(f"❌ Supabase not available for saving {creator_name}")
                return False
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                result = crud.update_creator_content(db, creator_name, content_data)
                item_count = len(content_data.get('items', [])) if content_data else 0
                
                if result is None:
                    # Creator was skipped due to 0 items or deleted
                    if item_count == 0:
                        logger.info(f"⏭️  Skipped creator {creator_name} - no content items")
                    return False  # Indicate that nothing was saved
                else:
                    logger.info(f"✓ Saved creator {creator_name} to Supabase ({item_count} items)")
                    return True
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error saving to Supabase: {e}")
            return False
    
    def get_creator_cache(self, creator_name: str, max_age_hours: int = 24) -> dict:
        """Get creator cache from Supabase only."""
        try:
            if not self.supabase_available:
                print(f"❌ Supabase not available for getting {creator_name}")
                return None
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                result = crud.get_creator_content(db, creator_name, max_age_hours)
                if result:
                    logger.info(f"✓ Retrieved creator {creator_name} from Supabase")
                return result
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting from Supabase: {e}")
            return None
    
    def save_onlyfans_posts(self, username: str, posts: list) -> bool:
        """Save OnlyFans posts to Supabase only."""
        try:
            if not self.supabase_available:
                print(f"❌ Supabase not available for saving OnlyFans posts for {username}")
                return False
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                crud.save_onlyfans_posts(db, username, posts)
                post_count = len(posts) if posts else 0
                logger.info(f"✓ Saved OnlyFans posts for {username} to Supabase ({post_count} posts)")
                return True
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error saving OnlyFans posts to Supabase: {e}")
            return False
    
    def get_onlyfans_posts(self, username: str, max_age_hours: int = 24) -> list:
        """Get OnlyFans posts from Supabase only."""
        try:
            if not self.supabase_available:
                print(f"❌ Supabase not available for getting OnlyFans posts for {username}")
                return []
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                result = crud.get_onlyfans_posts(db, username, max_age_hours)
                if result:
                    logger.info(f"✓ Retrieved OnlyFans posts for {username} from Supabase")
                return result if result is not None else []
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting OnlyFans posts from Supabase: {e}")
            return []
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics from Supabase only."""
        try:
            # Only get stats from Supabase, skip SQLite
            if self.supabase_available:
                from shared.config.database import get_db_session_sync
                from shared.data import crud
                
                db = get_db_session_sync()
                try:
                    supabase_stats = crud.get_database_stats(db)
                    
                    return {
                        'total_creators': supabase_stats.get('total_creators', 0),
                        'total_content_items': supabase_stats.get('total_content_items', 0),
                        'total_preview_images': supabase_stats.get('total_preview_images', 0),
                        'total_video_links': supabase_stats.get('total_video_links', 0),
                        'total_onlyfans_users': supabase_stats.get('total_onlyfans_users', 0),
                        'total_onlyfans_posts': supabase_stats.get('total_onlyfans_posts', 0),
                        'database_size_mb': 0.0,  # Not applicable for Supabase
                        'supabase_enabled': True,
                        'storage_type': 'Supabase only'
                    }
                finally:
                    db.close()
            else:
                return {
                    'total_creators': 0,
                    'total_content_items': 0,
                    'total_preview_images': 0,
                    'total_video_links': 0,
                    'total_onlyfans_users': 0,
                    'total_onlyfans_posts': 0,
                    'database_size_mb': 0.0,
                    'supabase_enabled': False,
                    'storage_type': 'Supabase only (disconnected)'
                }
        except Exception as e:
            print(f"❌ Error getting Supabase stats: {e}")
            return {
                'total_creators': 0,
                'total_content_items': 0,
                'total_preview_images': 0,
                'total_video_links': 0,
                'total_onlyfans_users': 0,
                'total_onlyfans_posts': 0,
                'database_size_mb': 0.0,
                'supabase_enabled': False,
                'storage_type': 'Supabase only (error)'
            }    

    def get_all_cached_creators(self) -> list:
        """Get list of all cached creators from Supabase."""
        try:
            if not self.supabase_available:
                return []
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                creators = crud.get_all_creators(db)
                # Convert Creator objects to dictionaries
                return [
                    {
                        'name': creator.name,
                        'url': f"https://simpcity.su/threads/{creator.name.lower().replace(' ', '-')}.123456/",  # Placeholder URL
                        'last_scraped': creator.last_scraped.isoformat() if creator.last_scraped else None,
                        'item_count': creator.post_count or 0
                    }
                    for creator in creators
                ]
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting creators from Supabase: {e}")
            return []
    
    def get_cached_creator_names_optimized(self) -> set:
        """Get set of cached creator names using optimized query (names only)."""
        try:
            if not self.supabase_available:
                return set()
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                return crud.get_cached_creator_names(db)
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting cached creator names: {e}")
            return set()
    
    def get_uncached_creators_optimized(self, csv_creators: list, batch_size: int = 500) -> list:
        """
        Get uncached creators using optimized batched queries.
        
        Args:
            csv_creators: List of creator dicts with 'name' and 'url' keys
            batch_size: Batch size for database queries
            
        Returns:
            List of uncached creator dicts
        """
        try:
            if not self.supabase_available or not csv_creators:
                return csv_creators
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            # Extract creator names from CSV
            creator_names = [creator['name'] for creator in csv_creators]
            
            db = get_db_session_sync()
            try:
                # Use batched IN queries to get existing names
                existing_names = crud.get_cached_creator_names_batched(db, creator_names, batch_size)
                
                # Filter to uncached creators using set comparison (O(1) lookup)
                uncached_creators = [
                    creator for creator in csv_creators 
                    if creator['name'].lower() not in existing_names
                ]
                
                print(f"📊 Optimization results:")
                print(f"   • Total CSV creators: {len(csv_creators)}")
                print(f"   • Already cached: {len(existing_names)}")
                print(f"   • Uncached (to process): {len(uncached_creators)}")
                
                return uncached_creators
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"❌ Error in optimized uncached creator lookup: {e}")
            # Fallback to original method
            return csv_creators
    
    def delete_creator_cache(self, creator_name: str) -> bool:
        """Delete creator cache from Supabase."""
        try:
            if not self.supabase_available:
                return False
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                crud.delete_creator(db, creator_name)
                logger.info(f"✓ Deleted creator {creator_name} from Supabase")
                return True
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error deleting creator from Supabase: {e}")
            return False
    
    def update_video_title(self, video_url: str, new_title: str) -> bool:
        """Update video title in Supabase."""
        try:
            if not self.supabase_available:
                return False
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            import logging
            
            logger = logging.getLogger(__name__)
            
            db = get_db_session_sync()
            try:
                result = crud.update_video_title(db, video_url, new_title)
                if result:
                    logger.info(f"✓ Updated video title in Supabase: {video_url}")
                return result
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error updating video title in Supabase: {e}")
            return False
    
    def is_supabase_available(self) -> bool:
        """Check if Supabase integration is available."""
        from shared.config.database import is_database_available
        return self.supabase_available and is_database_available()
    
    def get_onlyfans_usernames(self) -> list:
        """Get list of all OnlyFans usernames from Supabase."""
        try:
            if not self.supabase_available:
                return []
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                return crud.get_onlyfans_usernames(db)
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting OnlyFans usernames from Supabase: {e}")
            return []
    
    def get_stale_creators(self, max_age_hours: int = 24) -> list:
        """Get list of creators that need to be refreshed from Supabase."""
        try:
            if not self.supabase_available:
                return []
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                creators = crud.get_stale_creators(db, max_age_hours)
                # Convert Creator objects to dictionaries
                return [
                    {
                        'name': creator.name,
                        'url': f"https://simpcity.su/threads/{creator.name.lower().replace(' ', '-')}.123456/",  # Placeholder URL
                        'last_scraped': creator.last_scraped.isoformat() if creator.last_scraped else None,
                        'item_count': creator.post_count or 0
                    }
                    for creator in creators
                ]
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting stale creators from Supabase: {e}")
            return []
    
    def cleanup_empty_creators(self) -> int:
        """Remove creators with 0 items from Supabase database."""
        try:
            if not self.supabase_available:
                return 0
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                return crud.cleanup_empty_creators(db)
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error cleaning up empty creators: {e}")
            return 0
    
    def get_random_creator_with_content(self, min_items: int = 25) -> dict:
        """Get a random creator with at least min_items content items."""
        try:
            if not self.supabase_available:
                return None
            
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                creator = crud.get_random_creator_with_content(db, min_items)
                if creator:
                    return {
                        'name': creator.name,
                        'url': f"https://simpcity.su/threads/{creator.name.lower().replace(' ', '-')}.123456/",
                        'last_scraped': creator.last_scraped.isoformat() if creator.last_scraped else None,
                        'item_count': creator.post_count or 0
                    }
                return None
            finally:
                db.close()
        except Exception as e:
            print(f"❌ Error getting random creator: {e}")
            return None