"""
Landing Service for Telegram Bot - Standalone implementation for separate deployment
"""

import asyncio
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

logger = logging.getLogger(__name__)

class BotLandingService:
    """Standalone landing service for telegram bot with separate deployment support"""
    
    def __init__(self):
        # Read from bot's .env file
        self.base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
        self.secret_key = config('LANDING_SECRET_KEY', default='your-secret-key-change-this')
        self.enabled = config('LANDING_ENABLED', default='true').lower() == 'true'
        
        # Shared async client for better connection pooling
        self._client = None
        
        if not self.enabled:
            logger.info("Landing service is disabled - bot will provide direct links")
    
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
    
    def _convert_localhost_url(self, url: str) -> str:
        """Convert localhost URL to external domain URL"""
        if not url:
            return url
            
        # Replace localhost:8001 with the configured base URL
        if url.startswith('http://localhost:8001'):
            external_base = self.base_url.rstrip('/')
            return url.replace('http://localhost:8001', external_base)
        
        return url
    
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
            
            # Log request details
            logger.info(f"🔗 Requesting landing URL for: {creator_name} - {content_title} ({content_type})")
            logger.debug(f"   Original URL: {original_url[:100]}...")
            logger.debug(f"   Target server: {self.base_url}/api/generate-link")
            
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
                # Convert localhost URL to external domain
                landing_url = self._convert_localhost_url(landing_url)
                has_preview = result.get('preview_url') is not None
                logger.info(f"✅ Landing URL generated successfully: {landing_url}{' (with preview)' if has_preview else ''}")
                
                # Return the converted landing URL
                return landing_url
            else:
                error_msg = f"❌ FastAPI server returned error status {response.status_code}"
                logger.error(error_msg)
                logger.error(f"   Response body: {response.text[:500]}")
                logger.error(f"   Request: {content_type} - {creator_name}/{content_title}")
                raise RuntimeError(error_msg)
                
        except httpx.TimeoutException as e:
            error_msg = f"⏱️ FastAPI server timeout after 30s"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Content: {content_type} - {creator_name}/{content_title}")
            logger.error(f"   Exception: {str(e)}")
            raise RuntimeError(error_msg) from e
        except httpx.ConnectError as e:
            error_msg = f"🔌 Cannot connect to FastAPI server"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Is the landing server running?")
            logger.error(f"   Exception: {str(e)}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            error_msg = f"❌ Unexpected error calling FastAPI server"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Content: {content_type} - {creator_name}/{content_title}")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception: {str(e)}")
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
            
            logger.info(f"🔗 Requesting batch landing URLs for {len(batch_items)} items")
            logger.debug(f"   Target server: {self.base_url}/api/generate-batch-links")
            logger.debug(f"   Content types: {[item['content_type'] for item in batch_items[:5]]}...")
            
            # Call FastAPI server batch endpoint with longer timeout for preview extraction
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate-batch-links",
                json=batch_items,
                timeout=60.0  # 60 second timeout for batch processing with preview extraction
            )
            
            if response.status_code == 200:
                result = response.json()
                # Convert all localhost URLs to external domain
                urls = [self._convert_localhost_url(item['landing_url']) for item in result['results']]
                logger.info(f"✅ Generated {len(urls)} batch landing URLs successfully")
                return urls
            else:
                error_msg = f"❌ FastAPI batch request returned error status {response.status_code}"
                logger.error(error_msg)
                logger.error(f"   Response body: {response.text[:500]}")
                logger.error(f"   Batch size: {len(batch_items)} items")
                raise RuntimeError(error_msg)
                
        except httpx.TimeoutException as e:
            error_msg = f"⏱️ FastAPI batch request timeout after 60s"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Batch size: {len(items)} items")
            logger.error(f"   Consider reducing batch size or increasing timeout")
            logger.error(f"   Exception: {str(e)}")
            raise RuntimeError(error_msg) from e
        except httpx.ConnectError as e:
            error_msg = f"🔌 Cannot connect to FastAPI server for batch request"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Batch size: {len(items)} items")
            logger.error(f"   Is the landing server running?")
            logger.error(f"   Exception: {str(e)}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            error_msg = f"❌ Unexpected error in batch FastAPI call"
            logger.error(error_msg)
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Batch size: {len(items)} items")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception: {str(e)}")
            raise RuntimeError(error_msg) from e
    
    async def test_server_connection(self) -> bool:
        """Test if the landing server is accessible"""
        if not self.enabled:
            logger.info("🔌 Landing service is disabled - skipping connection test")
            return True  # Consider it "working" if disabled
        
        try:
            logger.info(f"🔍 Testing connection to landing server: {self.base_url}")
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            is_connected = response.status_code == 200
            if is_connected:
                logger.info(f"✅ Landing server is healthy and reachable")
            else:
                logger.error(f"❌ Landing server returned status {response.status_code}")
            return is_connected
        except httpx.ConnectError as e:
            logger.error(f"🔌 Landing server connection test failed - cannot connect")
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Is the server running?")
            logger.error(f"   Exception: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"❌ Landing server connection test failed")
            logger.error(f"   Server: {self.base_url}")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception: {str(e)}")
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
            logger.info(f"🎬 Extracting video preview for: {creator_name} - {content_title}")
            logger.debug(f"   Video URL: {video_url[:100]}...")
            
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
                    logger.info(f"✅ Video preview extracted successfully")
                    logger.debug(f"   Preview URL: {preview_url[:100]}...")
                    return preview_url
                else:
                    logger.info(f"ℹ️ No preview found for video")
                    return None
            else:
                logger.error(f"❌ FastAPI preview extraction returned error status {response.status_code}")
                logger.error(f"   Response body: {response.text[:500]}")
                return None
                
        except httpx.TimeoutException as e:
            logger.warning(f"⏱️ Timeout extracting video preview after 15s")
            logger.warning(f"   Video: {creator_name} - {content_title}")
            logger.debug(f"   Exception: {str(e)}")
            return None
        except httpx.ConnectError as e:
            logger.warning(f"🔌 Cannot connect to FastAPI for preview extraction")
            logger.warning(f"   Server: {self.base_url}")
            logger.debug(f"   Exception: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ Error extracting video preview")
            logger.error(f"   Video: {creator_name} - {content_title}")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception: {str(e)}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information"""
        return {
            'enabled': self.enabled,
            'base_url': self.base_url,
            'secret_configured': bool(self.secret_key and self.secret_key != 'your-secret-key-change-this')
        }

# Global instance configured with bot's environment
landing_service = BotLandingService()