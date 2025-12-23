"""
Cache Manager - Persistent caching system for creator content metadata
Stores scraped content in SQLite database to reduce real-time scraping load
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import threading

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages persistent cache for creator content metadata."""
    
    def __init__(self, db_path: str = 'data/cache/content_cache.db'):
        """Initialize cache manager with SQLite database."""
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for creator metadata
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS creators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    last_scraped TIMESTAMP,
                    total_pages INTEGER DEFAULT 0,
                    social_links TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table for content items
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS content_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    title TEXT,
                    type TEXT,
                    url TEXT NOT NULL,
                    domain TEXT,
                    content_type TEXT,
                    upload_date TEXT,
                    quality TEXT,
                    page_number INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES creators (id) ON DELETE CASCADE
                )
            ''')
            
            # Table for preview images
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS preview_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT,
                    page_number INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES creators (id) ON DELETE CASCADE
                )
            ''')
            
            # Table for video links
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS video_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    title TEXT,
                    url TEXT NOT NULL,
                    domain TEXT,
                    page_number INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES creators (id) ON DELETE CASCADE
                )
            ''')
            
            # Table for Coomer/OnlyFans feed posts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS onlyfans_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    post_data TEXT NOT NULL,
                    published TIMESTAMP,
                    last_cached TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(username, post_id)
                )
            ''')
            
            # Create indexes for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_creators_name ON creators(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_creators_last_scraped ON creators(last_scraped)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_creator ON content_items(creator_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_preview_creator ON preview_images(creator_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_creator ON video_links(creator_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_onlyfans_username ON onlyfans_posts(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_onlyfans_cached ON onlyfans_posts(last_cached)')
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    def get_creator_cache(self, creator_name: str, max_age_hours: int = 24) -> Optional[Dict]:
        """
        Get cached content for a creator if available and not expired.
        
        Args:
            creator_name: Name of the creator
            max_age_hours: Maximum age of cache in hours (default 24)
            
        Returns:
            Dict with creator content or None if not cached/expired
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get creator info
                cursor.execute('''
                    SELECT * FROM creators 
                    WHERE LOWER(name) = LOWER(?)
                ''', (creator_name,))
                
                creator = cursor.fetchone()
                if not creator:
                    logger.debug(f"No cache found for creator: {creator_name}")
                    return None
                
                # Check if cache is expired
                last_scraped = datetime.fromisoformat(creator['last_scraped']) if creator['last_scraped'] else None
                if not last_scraped or datetime.now() - last_scraped > timedelta(hours=max_age_hours):
                    logger.info(f"Cache expired for creator: {creator_name}")
                    return None
                
                creator_id = creator['id']
                
                # Get content items
                cursor.execute('''
                    SELECT * FROM content_items 
                    WHERE creator_id = ?
                    ORDER BY page_number, id
                ''', (creator_id,))
                content_items = [dict(row) for row in cursor.fetchall()]
                
                # Get preview images
                cursor.execute('''
                    SELECT * FROM preview_images 
                    WHERE creator_id = ?
                    ORDER BY page_number, id
                ''', (creator_id,))
                preview_images = [dict(row) for row in cursor.fetchall()]
                
                # Get video links
                cursor.execute('''
                    SELECT * FROM video_links 
                    WHERE creator_id = ?
                    ORDER BY page_number, id
                ''', (creator_id,))
                video_links = [dict(row) for row in cursor.fetchall()]
                
                # Parse social links
                social_links = json.loads(creator['social_links']) if creator['social_links'] else {}
                
                result = {
                    'creator': creator['name'],
                    'url': creator['url'],
                    'similarity': 1.0,  # From cache, exact match
                    'needs_confirmation': False,
                    'last_updated': creator['last_scraped'],
                    'total_items': len(content_items),
                    'items': content_items,
                    'preview_images': preview_images,
                    'total_preview_images': len(preview_images),
                    'video_links': video_links,
                    'total_video_links': len(video_links),
                    'pages_scraped': creator['total_pages'],
                    'total_pages': creator['total_pages'],
                    'start_page': 1,
                    'end_page': creator['total_pages'],
                    'has_more_pages': False,
                    'social_links': social_links,
                    'from_cache': True
                }
                
                logger.info(f"✓ Cache hit for {creator_name} ({len(content_items)} items)")
                return result
    
    def save_creator_cache(self, creator_name: str, url: str, content_data: Dict):
        """
        Save or update creator content in cache.
        
        Args:
            creator_name: Name of the creator
            url: Creator's page URL
            content_data: Dict containing scraped content
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert or update creator
                cursor.execute('''
                    INSERT INTO creators (name, url, last_scraped, total_pages, social_links, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(name) DO UPDATE SET
                        url = excluded.url,
                        last_scraped = excluded.last_scraped,
                        total_pages = excluded.total_pages,
                        social_links = excluded.social_links,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    creator_name,
                    url,
                    datetime.now().isoformat(),
                    content_data.get('total_pages', 0),
                    json.dumps(content_data.get('social_links', {}))
                ))
                
                # Get creator ID
                cursor.execute('SELECT id FROM creators WHERE LOWER(name) = LOWER(?)', (creator_name,))
                creator_id = cursor.fetchone()[0]
                
                # Delete old content for this creator
                cursor.execute('DELETE FROM content_items WHERE creator_id = ?', (creator_id,))
                cursor.execute('DELETE FROM preview_images WHERE creator_id = ?', (creator_id,))
                cursor.execute('DELETE FROM video_links WHERE creator_id = ?', (creator_id,))
                
                # Insert content items
                for item in content_data.get('items', []):
                    cursor.execute('''
                        INSERT INTO content_items 
                        (creator_id, title, type, url, domain, content_type, upload_date, quality, page_number)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        creator_id,
                        item.get('title'),
                        item.get('type'),
                        item.get('url'),
                        item.get('domain'),
                        item.get('content_type'),
                        item.get('upload_date'),
                        item.get('quality'),
                        item.get('page_number', 1)
                    ))
                
                # Insert preview images
                for img in content_data.get('preview_images', []):
                    cursor.execute('''
                        INSERT INTO preview_images (creator_id, url, domain, page_number)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        creator_id,
                        img.get('url'),
                        img.get('domain'),
                        img.get('page_number', 1)
                    ))
                
                # Insert video links
                for video in content_data.get('video_links', []):
                    cursor.execute('''
                        INSERT INTO video_links (creator_id, title, url, domain, page_number)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        creator_id,
                        video.get('title'),
                        video.get('url'),
                        video.get('domain'),
                        video.get('page_number', 1)
                    ))
                
                conn.commit()
                logger.info(f"✓ Cached content for {creator_name} ({len(content_data.get('items', []))} items)")
    
    def get_all_cached_creators(self) -> List[Dict]:
        """Get list of all cached creators with their metadata."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        name, url, last_scraped, total_pages,
                        (SELECT COUNT(*) FROM content_items WHERE creator_id = creators.id) as item_count
                    FROM creators
                    ORDER BY last_scraped DESC
                ''')
                
                return [dict(row) for row in cursor.fetchall()]
    
    def get_stale_creators(self, max_age_hours: int = 24) -> List[Dict]:
        """
        Get list of creators that need to be refreshed.
        
        Args:
            max_age_hours: Maximum age in hours before considering stale
            
        Returns:
            List of creator dicts that need refreshing
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
                
                cursor.execute('''
                    SELECT name, url, last_scraped
                    FROM creators
                    WHERE last_scraped IS NULL OR last_scraped < ?
                    ORDER BY last_scraped ASC NULLS FIRST
                ''', (cutoff_time.isoformat(),))
                
                return [dict(row) for row in cursor.fetchall()]
    
    def delete_creator_cache(self, creator_name: str):
        """Delete cached content for a specific creator."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM creators WHERE LOWER(name) = LOWER(?)', (creator_name,))
                conn.commit()
                logger.info(f"Deleted cache for creator: {creator_name}")
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the cache."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT COUNT(*) FROM creators')
                total_creators = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM content_items')
                total_items = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM preview_images')
                total_previews = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM video_links')
                total_videos = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(DISTINCT username) FROM onlyfans_posts')
                total_of_users = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM onlyfans_posts')
                total_of_posts = cursor.fetchone()[0]
                
                # Get database file size
                db_size = Path(self.db_path).stat().st_size / (1024 * 1024)  # MB
                
                return {
                    'total_creators': total_creators,
                    'total_content_items': total_items,
                    'total_preview_images': total_previews,
                    'total_video_links': total_videos,
                    'total_onlyfans_users': total_of_users,
                    'total_onlyfans_posts': total_of_posts,
                    'database_size_mb': round(db_size, 2)
                }
    
    def clear_old_cache(self, max_age_days: int = 7):
        """
        Clear cache entries older than specified days.
        
        Args:
            max_age_days: Maximum age in days to keep
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(days=max_age_days)
                
                cursor.execute('''
                    DELETE FROM creators 
                    WHERE last_scraped < ?
                ''', (cutoff_time.isoformat(),))
                
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f"Cleared {deleted} old cache entries (older than {max_age_days} days)")
                return deleted
    
    # OnlyFans/Coomer Cache Methods
    
    def get_onlyfans_posts(self, username: str, max_age_hours: int = 24) -> Optional[List[Dict]]:
        """
        Get cached OnlyFans posts for a user.
        
        Args:
            username: OnlyFans username
            max_age_hours: Maximum age of cache in hours (default 24)
            
        Returns:
            List of post dicts or None if not cached/expired
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
                
                cursor.execute('''
                    SELECT post_data, last_cached
                    FROM onlyfans_posts
                    WHERE LOWER(username) = LOWER(?)
                    AND last_cached > ?
                    ORDER BY published DESC
                ''', (username, cutoff_time.isoformat()))
                
                rows = cursor.fetchall()
                
                if not rows:
                    logger.debug(f"No cached OnlyFans posts for: {username}")
                    return None
                
                # Parse JSON data
                posts = [json.loads(row['post_data']) for row in rows]
                logger.info(f"✓ Cache hit for OnlyFans posts: {username} ({len(posts)} posts)")
                return posts
    
    def save_onlyfans_posts(self, username: str, posts: List[Dict]):
        """
        Save OnlyFans posts to cache.
        
        Args:
            username: OnlyFans username
            posts: List of post dicts from Coomer API
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete old posts for this user
                cursor.execute('DELETE FROM onlyfans_posts WHERE LOWER(username) = LOWER(?)', (username,))
                
                # Insert new posts
                for post in posts:
                    post_id = post.get('id', '')
                    published = post.get('published')
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO onlyfans_posts 
                        (username, post_id, post_data, published, last_cached)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        username,
                        post_id,
                        json.dumps(post),
                        published
                    ))
                
                conn.commit()
                logger.info(f"✓ Cached {len(posts)} OnlyFans posts for: {username}")
    
    def clear_onlyfans_cache(self, username: Optional[str] = None, max_age_days: int = 7):
        """
        Clear OnlyFans posts cache.
        
        Args:
            username: Specific username to clear (None for all)
            max_age_days: Clear posts older than this many days
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(days=max_age_days)
                
                if username:
                    cursor.execute('''
                        DELETE FROM onlyfans_posts 
                        WHERE LOWER(username) = LOWER(?)
                        AND last_cached < ?
                    ''', (username, cutoff_time.isoformat()))
                else:
                    cursor.execute('''
                        DELETE FROM onlyfans_posts 
                        WHERE last_cached < ?
                    ''', (cutoff_time.isoformat(),))
                
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f"Cleared {deleted} OnlyFans cache entries")
                return deleted
    
    def get_onlyfans_usernames(self) -> List[str]:
        """Get list of all cached OnlyFans usernames."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT username FROM onlyfans_posts ORDER BY username')
                return [row[0] for row in cursor.fetchall()]
    
    def update_video_title(self, video_url: str, new_title: str) -> bool:
        """
        Update the title of a video in the cache.
        
        Args:
            video_url: URL of the video to update
            new_title: New title for the video
            
        Returns:
            True if updated successfully, False if video not found
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Update in video_links table
                cursor.execute('''
                    UPDATE video_links 
                    SET title = ?
                    WHERE url = ?
                ''', (new_title, video_url))
                
                updated = cursor.rowcount > 0
                
                # Also update in content_items if it exists there
                cursor.execute('''
                    UPDATE content_items 
                    SET title = ?
                    WHERE url = ? AND type = 'video'
                ''', (new_title, video_url))
                
                updated = updated or cursor.rowcount > 0
                
                conn.commit()
                
                if updated:
                    logger.info(f"Updated video title in cache: {video_url} -> {new_title}")
                else:
                    logger.warning(f"Video not found in cache: {video_url}")
                
                return updated
    
    def get_video_by_url(self, video_url: str) -> Optional[Dict]:
        """
        Get video information by URL.
        
        Args:
            video_url: URL of the video
            
        Returns:
            Dict with video info or None if not found
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Try video_links first
                cursor.execute('''
                    SELECT v.*, c.name as creator_name
                    FROM video_links v
                    JOIN creators c ON v.creator_id = c.id
                    WHERE v.url = ?
                ''', (video_url,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                
                # Try content_items
                cursor.execute('''
                    SELECT ci.*, c.name as creator_name
                    FROM content_items ci
                    JOIN creators c ON ci.creator_id = c.id
                    WHERE ci.url = ? AND ci.type = 'video'
                ''', (video_url,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                
                return None

