"""
Landing Service - Integrates the bot with the FastAPI landing server
"""

import hashlib
import base64
import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from decouple import config

logger = logging.getLogger(__name__)

class LandingService:
    """Service to generate landing page URLs for content"""
    
    def __init__(self):
        self.base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
        self.secret_key = config('LANDING_SECRET_KEY', default='your-secret-key-change-this')
        self.enabled = config('LANDING_ENABLED', default='true').lower() == 'true'
        
        if not self.enabled:
            logger.info("Landing service is disabled - bot will provide direct links")
    
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
        Generate a landing page URL for content.
        
        Args:
            creator_name: Name of the creator
            content_title: Title of the content
            content_type: Type of content (e.g., "🎬 Video", "📷 Photo")
            original_url: Original URL to the content
            preview_url: Optional preview URL
            thumbnail_url: Optional thumbnail URL
            expires_hours: Hours until the link expires
            
        Returns:
            Landing page URL or original URL if service is disabled
        """
        
        # If landing service is disabled, return original URL
        if not self.enabled:
            return original_url
        
        try:
            # Create expiration timestamp
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            # Prepare data to sign
            data_to_sign = {
                'creator': creator_name,
                'title': content_title,
                'type': content_type,
                'url': original_url,
                'preview': preview_url,
                'thumbnail': thumbnail_url,
                'expires': expires_at.isoformat()
            }
            
            # Convert to string and encode
            data_string = str(sorted(data_to_sign.items()))
            signature = hashlib.sha256(f"{data_string}{self.secret_key}".encode()).hexdigest()
            
            # Encode the data
            encoded_data = base64.urlsafe_b64encode(str(data_to_sign).encode()).decode()
            
            # Generate the landing URL
            landing_url = f"{self.base_url}/content/{encoded_data}/{signature}"
            
            logger.debug(f"Generated landing URL for {creator_name}: {content_title}")
            return landing_url
            
        except Exception as e:
            logger.error(f"Error generating landing URL: {e}")
            # Fallback to original URL if there's an error
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
        """Async version of generate_landing_url"""
        return self.generate_landing_url(
            creator_name, content_title, content_type, original_url,
            preview_url, thumbnail_url, expires_hours
        )
    
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