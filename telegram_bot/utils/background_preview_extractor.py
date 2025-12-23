"""
Background Video Preview Extractor
Extracts video previews in background without blocking bot responses
"""

import asyncio
import logging
from typing import Optional
from utils.video_preview_extractor import get_video_preview

logger = logging.getLogger(__name__)

class BackgroundPreviewExtractor:
    """Extract video previews in background"""
    
    def __init__(self):
        self.tasks = []
    
    async def extract_and_update(self, url: str, short_id: str):
        """
        Extract preview in background and update the stored URL data
        
        Args:
            url: Original video URL
            short_id: Short ID from landing service
        """
        try:
            # Run the extraction in a thread pool to not block
            loop = asyncio.get_event_loop()
            preview_url = await loop.run_in_executor(None, get_video_preview, url)
            
            if preview_url:
                logger.info(f"Background: Extracted preview for {short_id}: {preview_url}")
                # TODO: Update the stored URL data with the preview
                # This would require access to url_storage from fastapi_server
            else:
                logger.debug(f"Background: No preview found for {url}")
                
        except Exception as e:
            logger.error(f"Background preview extraction failed: {e}")
    
    def schedule_extraction(self, url: str, short_id: str):
        """Schedule a preview extraction in background"""
        if any(service in url.lower() for service in ['bunkr']):  # Only for Bunkr
            task = asyncio.create_task(self.extract_and_update(url, short_id))
            self.tasks.append(task)

# Global instance
background_extractor = BackgroundPreviewExtractor()
