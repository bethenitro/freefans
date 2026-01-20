"""
Landing Service - Integrates the bot with the FastAPI landing server using Supabase storage
"""

import asyncio
import hashlib
import base64
import secrets
import string
import httpx
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pathlib import Path
from decouple import config

# Add project root to path for shared imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import get_db_session_sync, init_database, create_tables
from shared.data import crud

logger = logging.getLogger(__name__)

class LandingService:
    """Service to generate landing page URLs for content using Supabase storage"""
    
    def __init__(self):
        self.base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
        self.secret_key = config('LANDING_SECRET_KEY', default='your-secret-key-change-this')
        self.enabled = config('LANDING_ENABLED', default='true').lower() == 'true'
        
        # Initialize Supabase connection
        self.supabase_available = False
        self._init_supabase()
        
        # Shared async client for better connection pooling
        self._client = None
        
        if not self.enabled:
            logger.info("Landing service is disabled - bot will provide direct links")
    
    def _init_supabase(self):
        """Initialize Supabase database connection."""
        try:
            if init_database():
                if create_tables():
                    self.supabase_available = True
                    logger.info("✓ Landing service: Supabase integration enabled")
                else:
                    logger.warning("⚠ Landing service: Supabase tables creation failed")
            else:
                logger.info("ℹ Landing service: Supabase integration disabled")
        except Exception as e:
            logger.error(f"✗ Landing service: Supabase initialization failed: {e}")
            self.supabase_available = False
    
    async def _get_client(self):
        """Get or create shared async client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=2.0),  # 5s total, 2s connect
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
        return self._client
    
    async def close(self):
        """Close the shared client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _store_landing_data(self, short_id: str, data: Dict[str, Any]) -> bool:
        """Store landing page data in Supabase."""
        if not self.supabase_available:
            logger.warning(f"Supabase not available for storing landing data: {short_id}")
            return False
        
        try:
            db = get_db_session_sync()
            try:
                # Parse expires datetime
                expires_at = datetime.fromisoformat(data['expires'].replace('Z', '+00:00'))
                
                # Create landing page record
                landing_page = crud.create_landing_page(
                    db=db,
                    short_id=short_id,
                    creator=data['creator'],
                    title=data['title'],
                    content_type=data['type'],
                    original_url=data['url'],
                    preview_url=data.get('preview'),
                    thumbnail_url=data.get('thumbnail'),
                    expires_at=expires_at
                )
                
                logger.info(f"✓ Stored landing data for {short_id} in Supabase")
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to store landing data in Supabase: {e}")
            return False
    
    def _get_landing_data(self, short_id: str) -> Optional[Dict[str, Any]]:
        """Get landing page data from Supabase."""
        if not self.supabase_available:
            return None
        
        try:
            db = get_db_session_sync()
            try:
                landing_page = crud.get_landing_page(db, short_id)
                if landing_page:
                    return {
                        'creator': landing_page.creator,
                        'title': landing_page.title,
                        'type': landing_page.content_type,
                        'url': landing_page.original_url,
                        'preview': landing_page.preview_url,
                        'thumbnail': landing_page.thumbnail_url,
                        'expires': landing_page.expires_at.isoformat()
                    }
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to get landing data from Supabase: {e}")
            return None
    
    def _generate_short_id(self, length: int = 8) -> str:
        """Generate a short random ID for URLs"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def generate_landing_url(
        self, 
        creator_name: str, 
        content_title: str, 
        content_type: str, 
        original_url: str,
        preview_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        expires_hours: int = 24
    ) -> str:
        """
        Generate a short landing page URL for content using Supabase storage.
        
        Args:
            creator_name: Name of the creator
            content_title: Title of the content
            content_type: Type of content (e.g., "🎬 Video", "📷 Photo")
            original_url: Original URL to the content
            preview_url: Optional preview URL
            thumbnail_url: Optional thumbnail URL
            expires_hours: Hours until the link expires
            
        Returns:
            Short landing page URL or original URL if service is disabled
        """
        
        # If landing service is disabled, return original URL
        if not self.enabled:
            return original_url
        
        try:
            # Check if we already have a cached landing page for this URL
            if self.supabase_available:
                cached_landing = self._get_cached_landing_by_url(original_url, creator_name)
                if cached_landing:
                    logger.debug(f"Using cached landing URL for: {original_url}")
                    return f"{self.base_url}/c/{cached_landing['short_id']}"
            
            # Generate short ID locally (instant, no HTTP call)
            short_id = self._generate_short_id(8)
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            landing_url = f"{self.base_url}/c/{short_id}"
            
            # Store data and WAIT for sync to complete before returning URL
            landing_data = {
                'creator': creator_name,
                'title': content_title,
                'type': content_type,
                'url': original_url,
                'preview': preview_url,
                'thumbnail': thumbnail_url,
                'expires': expires_at.isoformat()
            }
            
            # Store in Supabase first (fast)
            self._store_landing_data(short_id, landing_data)
            
            # Then sync to FastAPI server and WAIT for completion
            sync_success = False
            try:
                response = httpx.post(
                    f"{self.base_url}/api/generate-link",
                    json={
                        'creator_name': creator_name,
                        'content_title': content_title,
                        'content_type': content_type,
                        'original_url': original_url,
                        'preview_url': preview_url,
                        'thumbnail_url': thumbnail_url,
                        'expires_at': expires_at.isoformat(),
                        'short_id': short_id
                    },
                    timeout=3.0  # Increased timeout to ensure sync completes
                )
                if response.status_code == 200:
                    sync_success = True
                    logger.debug(f"✓ Synced landing data to FastAPI: {short_id}")
                else:
                    logger.error(f"Failed to sync to server (status {response.status_code}): {short_id}")
            except httpx.TimeoutException:
                logger.warning(f"Timeout syncing to server: {short_id}")
            except httpx.ConnectError:
                logger.warning(f"Cannot connect to landing server: {short_id}")
            except Exception as e:
                logger.error(f"Failed to sync to server: {e} (short_id: {short_id})")
            
            # Only return URL if sync was successful or if we're in fallback mode
            if sync_success:
                logger.debug(f"Generated landing URL: {landing_url} (synced successfully)")
                return landing_url
            else:
                logger.warning(f"Sync failed for {short_id}, returning original URL to avoid 404s")
                return original_url
            
        except Exception as e:
            logger.error(f"Error generating landing URL: {e}")
            return original_url
    
    def _get_cached_landing_by_url(self, original_url: str, creator: str) -> Optional[Dict[str, Any]]:
        """Get cached landing page by original URL and creator."""
        if not self.supabase_available:
            return None
        
        try:
            from shared.data.models import LandingPage
            db = get_db_session_sync()
            try:
                # Look for recent landing pages for this URL and creator
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)  # Only reuse very recent ones
                landing_page = db.query(LandingPage).filter(
                    LandingPage.original_url == original_url,
                    LandingPage.creator == creator,
                    LandingPage.expires_at > datetime.now(timezone.utc),
                    LandingPage.created_at >= cutoff_time
                ).first()
                
                if landing_page:
                    return {
                        'short_id': landing_page.short_id,
                        'creator': landing_page.creator,
                        'title': landing_page.title,
                        'type': landing_page.content_type,
                        'url': landing_page.original_url,
                        'preview': landing_page.preview_url,
                        'thumbnail': landing_page.thumbnail_url,
                        'expires': landing_page.expires_at.isoformat()
                    }
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to get cached landing by URL: {e}")
            return None
    
    async def generate_landing_url_async(
        self, 
        creator_name: str, 
        content_title: str, 
        content_type: str, 
        original_url: str,
        preview_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        expires_hours: int = 24
    ) -> str:
        """
        Generate landing URL by calling FastAPI server.
        FastAPI server handles preview extraction, caching, and storage.
        Raises exception if FastAPI server is unavailable.
        
        Returns:
            Landing URL (preview URL is extracted and cached by FastAPI internally)
        """
        # If landing service is disabled, raise exception
        if not self.enabled:
            raise RuntimeError("Landing service is disabled")
        
        try:
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            # Call FastAPI server to generate landing URL with longer timeout
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate-link",
                json={
                    'creator_name': creator_name,
                    'content_title': content_title,
                    'content_type': content_type,
                    'original_url': original_url,
                    'preview_url': preview_url,
                    'thumbnail_url': thumbnail_url,
                    'expires_at': expires_at.isoformat()
                },
                timeout=30.0  # Increased timeout to allow for preview extraction
            )
            
            if response.status_code == 200:
                result = response.json()
                landing_url = result['landing_url']
                has_preview = result.get('preview_url') is not None
                logger.debug(f"✅ Generated landing URL via FastAPI: {landing_url}{' (with preview)' if has_preview else ''}")
                
                # Return just the landing URL (preview is used internally by landing page)
                return landing_url
            else:
                error_msg = f"FastAPI server error (status {response.status_code}): {response.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except httpx.TimeoutException as e:
            error_msg = "FastAPI server timeout - please try again"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except httpx.ConnectError as e:
            error_msg = "Cannot connect to FastAPI server - service may be down"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            error_msg = f"Error calling FastAPI server: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    async def generate_batch_landing_urls_async(
        self,
        items: list
    ) -> list:
        """
        Generate multiple landing URLs by calling FastAPI server batch endpoint.
        """
        if not self.enabled:
            return [item['original_url'] for item in items]
        
        try:
            # Prepare batch request
            batch_items = []
            for item in items:
                expires_at = datetime.now() + timedelta(hours=item.get('expires_hours', 24))
                batch_items.append({
                    'creator_name': item['creator_name'],
                    'content_title': item['content_title'],
                    'content_type': item['content_type'],
                    'original_url': item['original_url'],
                    'preview_url': item.get('preview_url'),
                    'thumbnail_url': item.get('thumbnail_url'),
                    'expires_at': expires_at.isoformat()
                })
            
            # Call FastAPI server batch endpoint with longer timeout for preview extraction
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate-batch-links",
                json=batch_items,
                timeout=60.0  # 60 second timeout for batch processing with preview extraction
            )
            
            if response.status_code == 200:
                result = response.json()
                urls = [item['landing_url'] for item in result['results']]
                logger.debug(f"✅ Generated {len(urls)} batch landing URLs via FastAPI")
                return urls
            else:
                error_msg = f"FastAPI batch error (status {response.status_code}): {response.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except httpx.TimeoutException as e:
            error_msg = f"FastAPI batch timeout after 60s - {len(items)} items may need more time"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except httpx.ConnectError as e:
            error_msg = "Cannot connect to FastAPI server - service may be down"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            error_msg = f"Error in batch FastAPI call: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    async def test_server_connection(self) -> bool:
        """Test if the landing server is accessible"""
        if not self.enabled:
            return True  # Consider it "working" if disabled
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Landing server connection test failed: {e}")
            return False
    
    async def extract_video_preview(self, video_url: str, creator_name: str = "Unknown", content_title: str = "Video") -> Optional[str]:
        """
        Extract video preview URL by calling FastAPI server.
        
        Args:
            video_url: URL to the video
            creator_name: Name of the creator (optional)
            content_title: Title of the content (optional)
            
        Returns:
            Preview URL or None if not found
        """
        if not self.enabled:
            return None
        
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/extract-video-preview",
                json={
                    'video_url': video_url,
                    'creator_name': creator_name,
                    'content_title': content_title
                },
                timeout=15.0  # Increased timeout for preview extraction
            )
            
            if response.status_code == 200:
                result = response.json()
                preview_url = result.get('preview_url')
                if preview_url:
                    logger.debug(f"✅ Extracted preview via FastAPI: {preview_url}")
                    return preview_url
                else:
                    logger.debug(f"ℹ️ No preview found for video: {video_url}")
                    return None
            else:
                logger.error(f"FastAPI preview extraction error (status {response.status_code}): {response.text}")
                return None
                
        except httpx.TimeoutException:
            logger.warning(f"Timeout calling FastAPI for preview extraction")
            return None
        except httpx.ConnectError:
            logger.warning(f"Cannot connect to FastAPI server for preview extraction")
            return None
        except Exception as e:
            logger.error(f"Error calling FastAPI for preview extraction: {e}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information"""
        return {
            'enabled': self.enabled,
            'base_url': self.base_url,
            'secret_configured': bool(self.secret_key and self.secret_key != 'your-secret-key-change-this')
        }

# Global instance
landing_service = LandingService()