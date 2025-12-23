#!/usr/bin/env python3
"""
Cache Manager Factory

Provides the appropriate cache manager based on the CACHE_STORAGE_MODE environment variable.
"""

import os
from decouple import config
from .cache_manager import CacheManager
from .dual_cache_manager import DualCacheManager


def get_cache_manager():
    """
    Factory function to get the appropriate cache manager based on configuration.
    
    Returns:
        CacheManager or DualCacheManager: The appropriate cache manager instance
    """
    cache_mode = config('CACHE_STORAGE_MODE', default='BOTH').upper()
    
    if cache_mode == 'LOCAL':
        print("💾 Using LOCAL cache storage (SQLite only)")
        return CacheManager()
    elif cache_mode == 'SUPABASE':
        print("☁️  Using SUPABASE cache storage (PostgreSQL only)")
        return SupabaseCacheManager()
    elif cache_mode == 'BOTH':
        print("🔄 Using DUAL cache storage (SQLite + Supabase)")
        return DualCacheManager()
    else:
        print(f"⚠️  Unknown cache mode '{cache_mode}', defaulting to DUAL storage")
        return DualCacheManager()


class SupabaseCacheManager(DualCacheManager):
    """
    Supabase-only cache manager that only uses PostgreSQL storage.
    Inherits from DualCacheManager but overrides methods to skip SQLite operations.
    """
    
    def __init__(self):
        """Initialize Supabase-only cache manager."""
        # Initialize the parent but we'll override the methods
        super().__init__()
        print("☁️  Supabase-only cache manager initialized")
    
    def save_creator_cache(self, creator_name: str, url: str, content_data: dict, 
                          post_count: int = 0, preview_images: list = None, 
                          video_links: list = None) -> bool:
        """Save creator cache to Supabase only."""
        try:
            # Only save to Supabase, skip SQLite
            if not self.supabase_available:
                print(f"❌ Supabase not available for saving {creator_name}")
                return False
            
            self._sync_to_supabase('save_creator_cache', 
                                 creator_name=creator_name, 
                                 url=url, 
                                 content_data=content_data, 
                                 post_count=post_count,
                                 preview_images=preview_images or [],
                                 video_links=video_links or [])
            return True
        except Exception as e:
            print(f"❌ Error saving to Supabase: {e}")
            return False
    
    def get_creator_cache(self, creator_name: str, max_age_hours: int = 24) -> dict:
        """Get creator cache from Supabase only."""
        try:
            # Only get from Supabase, skip SQLite
            if not self.supabase_available:
                print(f"❌ Supabase not available for getting {creator_name}")
                return None
            
            return self._get_from_supabase('get_creator_cache', 
                                         creator_name=creator_name, 
                                         max_age_hours=max_age_hours)
        except Exception as e:
            print(f"❌ Error getting from Supabase: {e}")
            return None
    
    def save_onlyfans_posts(self, username: str, posts: list) -> bool:
        """Save OnlyFans posts to Supabase only."""
        try:
            # Only save to Supabase, skip SQLite
            if not self.supabase_available:
                print(f"❌ Supabase not available for saving OnlyFans posts for {username}")
                return False
            
            self._sync_to_supabase('save_onlyfans_posts', 
                                 username=username, 
                                 posts=posts)
            return True
        except Exception as e:
            print(f"❌ Error saving OnlyFans posts to Supabase: {e}")
            return False
    
    def get_onlyfans_posts(self, username: str, max_age_hours: int = 24) -> list:
        """Get OnlyFans posts from Supabase only."""
        try:
            # Only get from Supabase, skip SQLite
            if not self.supabase_available:
                print(f"❌ Supabase not available for getting OnlyFans posts for {username}")
                return []
            
            result = self._get_from_supabase('get_onlyfans_posts', 
                                           username=username, 
                                           max_age_hours=max_age_hours)
            return result if result is not None else []
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