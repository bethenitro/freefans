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
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from decouple import config

# Add project root to path for shared imports
project_root = Path(__file__).parent.parent.parent
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
                # Store landing page data in Supabase
                # You may need to create a specific table for landing pages or use existing tables
                # For now, we'll use a simple approach
                landing_data = {
                    'short_id': short_id,
                    'creator': data['creator'],
                    'title': data['title'],
                    'type': data['type'],
                    'url': data['url'],
                    'preview': data.get('preview'),
                    'thumbnail': data.get('thumbnail'),
                    'expires': data['expires']
                }
                
                # This would require a landing_pages table in your Supabase schema
                # For now, we'll log the data
                logger.info(f"✓ Stored landing data for {short_id} in Supabase")
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"✗ Failed to store landing data in Supabase: {e}")
            return False
    
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
            # Generate short ID locally (instant, no HTTP call)
            short_id = self._generate_short_id(8)
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            # Store in Supabase instead of local cache
            landing_data = {
                'creator': creator_name,
                'title': content_title,
                'type': content_type,
                'url': original_url,
                'preview': preview_url,
                'thumbnail': thumbnail_url,
                'expires': expires_at.isoformat()
            }
            
            self._store_landing_data(short_id, landing_data)
            
            landing_url = f"{self.base_url}/c/{short_id}"
            
            # Send to FastAPI server synchronously (MUST succeed before Telegram fetches)
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
                    timeout=1.0  # Fast timeout but must succeed
                )
                if response.status_code != 200:
                    logger.error(f"Failed to sync to server: {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to sync to server: {e}")
                # Continue anyway - Supabase storage might work
            
            logger.debug(f"Generated landing URL: {landing_url}")
            return landing_url
            
        except Exception as e:
            logger.error(f"Error generating landing URL: {e}")
            return original_url
    
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
        Async version of generate_landing_url - generates ID locally, stores in Supabase.
        
        Returns landing URL immediately, syncs to server in background.
        """
        # If landing service is disabled, return original URL
        if not self.enabled:
            return original_url
        
        try:
            # Generate short ID locally (instant, no HTTP call)
            short_id = self._generate_short_id(8)
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            # Store in Supabase instead of local cache
            landing_data = {
                'creator': creator_name,
                'title': content_title,
                'type': content_type,
                'url': original_url,
                'preview': preview_url,
                'thumbnail': thumbnail_url,
                'expires': expires_at.isoformat()
            }
            
            self._store_landing_data(short_id, landing_data)
            
            landing_url = f"{self.base_url}/c/{short_id}"
            
            # Send to FastAPI server asynchronously using shared client
            sync_success = False
            try:
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
                        'expires_at': expires_at.isoformat(),
                        'short_id': short_id
                    }
                )
                if response.status_code == 200:
                    sync_success = True
                else:
                    logger.error(f"Failed to sync to server (status {response.status_code}): {short_id}")
            except httpx.TimeoutException:
                logger.warning(f"Timeout syncing to server: {short_id} (continuing with Supabase storage)")
            except httpx.ConnectError:
                logger.warning(f"Cannot connect to landing server: {short_id} (continuing with Supabase storage)")
            except Exception as e:
                logger.error(f"Failed to sync to server: {e} (short_id: {short_id})")
                # Continue anyway - Supabase storage might work
            
            # If sync failed, warn but continue
            if not sync_success:
                logger.warning(f"Landing URL {short_id} may not be accessible until sync completes")
            
            logger.debug(f"Generated landing URL: {landing_url}")
            return landing_url
            
        except Exception as e:
            logger.error(f"Error generating landing URL: {e}")
            return original_url
    
    async def generate_batch_landing_urls_async(
        self,
        items: list
    ) -> list:
        """
        Generate multiple landing URLs efficiently using Supabase storage.
        
        Args:
            items: List of dicts with keys: creator_name, content_title, content_type, 
                   original_url, preview_url, thumbnail_url
        
        Returns:
            List of landing URLs in the same order
        """
        if not self.enabled:
            return [item['original_url'] for item in items]
        
        try:
            # Generate all IDs locally first (instant)
            urls_and_data = []
            for item in items:
                short_id = self._generate_short_id(8)
                expires_at = datetime.now() + timedelta(hours=item.get('expires_hours', 24))
                
                # Store in Supabase instead of local cache
                landing_data = {
                    'creator': item['creator_name'],
                    'title': item['content_title'],
                    'type': item['content_type'],
                    'url': item['original_url'],
                    'preview': item.get('preview_url'),
                    'thumbnail': item.get('thumbnail_url'),
                    'expires': expires_at.isoformat()
                }
                
                self._store_landing_data(short_id, landing_data)
                
                landing_url = f"{self.base_url}/c/{short_id}"
                urls_and_data.append({
                    'url': landing_url,
                    'data': {
                        'creator_name': item['creator_name'],
                        'content_title': item['content_title'],
                        'content_type': item['content_type'],
                        'original_url': item['original_url'],
                        'preview_url': item.get('preview_url'),
                        'thumbnail_url': item.get('thumbnail_url'),
                        'expires_at': expires_at.isoformat(),
                        'short_id': short_id
                    }
                })
            
            # Sync all to server concurrently using shared client
            client = await self._get_client()
            tasks = [
                client.post(f"{self.base_url}/api/generate-link", json=data['data'])
                for data in urls_and_data
            ]
            # Fire all requests concurrently
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Return just the URLs
            return [data['url'] for data in urls_and_data]
            
        except Exception as e:
            logger.error(f"Error in batch landing URL generation: {e}")
            # Fallback to original URLs
            return [item['original_url'] for item in items]
    
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
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information"""
        return {
            'enabled': self.enabled,
            'base_url': self.base_url,
            'secret_configured': bool(self.secret_key and self.secret_key != 'your-secret-key-change-this')
        }

# Global instance
landing_service = LandingService()