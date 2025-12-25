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
            client = await self._get_client()
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

# Global instance configured with bot's environment
landing_service = BotLandingService()