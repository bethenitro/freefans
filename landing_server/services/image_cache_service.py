"""
Video Preview Cache Service - Background service to cache video preview images for landing pages
"""

import asyncio
import aiohttp
import aiofiles
import hashlib
import logging
from pathlib import Path
from typing import Optional, Set
from datetime import datetime, timedelta
import sys
from decouple import config

# Add project root to path for shared imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import get_db_session_sync
from shared.data import crud

logger = logging.getLogger(__name__)

class VideoPreviewCacheService:
    """Background service to cache video preview images for landing pages"""
    
    def __init__(self, cache_dir: str = "landing_server/static/cached_previews"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cached_urls: Set[str] = set()
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        
    async def start(self):
        """Start the video preview caching service"""
        if self.running:
            return
            
        self.running = True
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
            headers={'User-Agent': 'FreeFans-VideoPreviewCache/1.0'}
        )
        
        logger.info("🎬 Video preview cache service started")
        
        # Don't start background caching immediately on startup
        # It will be triggered by new video landing page requests
        logger.info("🎬 Background video preview caching will start with new requests")
    
    def start_background_caching(self):
        """Start background caching loop (called when first video preview is requested)"""
        if self.running:
            asyncio.create_task(self._background_cache_loop())
    
    async def stop(self):
        """Stop the video preview caching service"""
        self.running = False
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("🎬 Video preview cache service stopped")
    
    def _get_cache_filename(self, url: str) -> str:
        """Generate cache filename from URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        # Try to preserve original extension
        if url.lower().endswith(('.jpg', '.jpeg')):
            ext = '.jpg'
        elif url.lower().endswith('.png'):
            ext = '.png'
        elif url.lower().endswith('.webp'):
            ext = '.webp'
        else:
            ext = '.jpg'  # Default
        return f"video_preview_{url_hash}{ext}"
    
    def get_cached_preview_path(self, url: str) -> Optional[str]:
        """Get cached video preview path if it exists"""
        if not url:
            return None
            
        filename = self._get_cache_filename(url)
        cache_path = self.cache_dir / filename
        
        if cache_path.exists():
            # Return relative path for web serving
            return f"/static/cached_previews/{filename}"
        return None
    
    async def cache_video_preview(self, url: str) -> Optional[str]:
        """Cache a video preview image and return the cached path"""
        if not url or not self.session:
            return None
            
        # Check if already cached in filesystem
        cached_path = self.get_cached_preview_path(url)
        if cached_path:
            return cached_path
        
        # Check if cached in database (another process may have cached it)
        db_cached_path = self._get_cached_from_db(url)
        if db_cached_path:
            # Verify file exists
            if Path(f"landing_server{db_cached_path}").exists():
                logger.debug(f"✅ Found cached preview in DB: {db_cached_path}")
                return db_cached_path
            
        try:
            filename = self._get_cache_filename(url)
            cache_path = self.cache_dir / filename
            
            # Download video preview
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Save to cache
                    async with aiofiles.open(cache_path, 'wb') as f:
                        await f.write(content)
                    
                    self.cached_urls.add(url)
                    relative_path = f"/static/cached_previews/{filename}"
                    logger.debug(f"✅ Cached video preview: {url} -> {filename}")
                    
                    # Update database records that use this preview URL
                    self._update_db_with_cached_path(url, relative_path)
                    
                    return relative_path
                else:
                    logger.warning(f"Failed to download video preview {url}: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Error caching video preview {url}: {e}")
            
        return None
    
    def _get_cached_from_db(self, preview_url: str) -> Optional[str]:
        """Check if preview URL is already cached in the database"""
        try:
            db = get_db_session_sync()
            try:
                from shared.data.models import LandingPage
                # Look for any landing page that has this preview URL and a cached path
                page = db.query(LandingPage).filter(
                    LandingPage.preview_url.like(f"%{preview_url.split('/')[-1]}%"),  # Match by filename
                    LandingPage.preview_url.like("%/static/cached_previews/%")  # Has cached path
                ).first()
                
                if page and page.preview_url:
                    # Extract the cached path
                    if "/static/cached_previews/" in page.preview_url:
                        start_idx = page.preview_url.find("/static/cached_previews/")
                        cached_path = page.preview_url[start_idx:]
                        return cached_path
                        
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error checking DB for cached preview: {e}")
            return None
    
    def _update_db_with_cached_path(self, original_url: str, cached_path: str):
        """Update database landing pages with cached preview path"""
        try:
            db = get_db_session_sync()
            try:
                from shared.data.models import LandingPage
                # Update all landing pages that use this original preview URL
                base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
                full_cached_url = f"{base_url}{cached_path}"
                
                updated = db.query(LandingPage).filter(
                    LandingPage.preview_url == original_url
                ).update({
                    LandingPage.preview_url: full_cached_url
                })
                
                if updated > 0:
                    db.commit()
                    logger.info(f"✅ Updated {updated} landing pages with cached preview path")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error updating DB with cached path: {e}")
    
    # Keep the old method name for compatibility
    async def cache_image(self, url: str) -> Optional[str]:
        """Alias for cache_video_preview for backward compatibility"""
        return await self.cache_video_preview(url)
    
    async def _background_cache_loop(self):
        """Background loop to cache video previews from recent landing pages"""
        while self.running:
            try:
                await self._cache_recent_video_previews()
                # Wait 10 minutes before next check
                await asyncio.sleep(600)
            except Exception as e:
                logger.error(f"Error in background cache loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _cache_recent_video_previews(self):
        """Cache video preview images from recent video landing pages"""
        try:
            db = get_db_session_sync()
            try:
                # Get recent video landing pages from last 2 hours
                cutoff_time = datetime.utcnow() - timedelta(hours=2)
                recent_pages = crud.get_recent_landing_pages(db, cutoff_time)
                
                cache_tasks = []
                for page in recent_pages:
                    # Only cache previews for video content
                    if page.content_type and '🎬' in page.content_type:
                        if page.preview_url and page.preview_url not in self.cached_urls:
                            cache_tasks.append(self.cache_video_preview(page.preview_url))
                
                if cache_tasks:
                    results = await asyncio.gather(*cache_tasks, return_exceptions=True)
                    success_count = sum(1 for r in results if isinstance(r, str))
                    logger.info(f"🎬 Cached {success_count}/{len(cache_tasks)} video previews from recent landing pages")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error caching recent video previews: {e}")
    
    def cleanup_old_cache(self, max_age_hours: int = 48):
        """Clean up old cached video previews"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            removed_count = 0
            
            for cache_file in self.cache_dir.glob("video_preview_*"):
                if cache_file.is_file():
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_time < cutoff_time:
                        cache_file.unlink()
                        removed_count += 1
            
            if removed_count > 0:
                logger.info(f"🧹 Cleaned up {removed_count} old cached video previews")
                
        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")

# Global instance
video_preview_cache_service = VideoPreviewCacheService()