"""
Video Preview Extractor for FastAPI Server
Extracts thumbnail/preview images from video hosting services like Bunkr, Gofile, etc.
"""

import re
import httpx
import asyncio
import logging
from typing import Optional, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class VideoPreviewExtractor:
    """Extract preview images from video hosting services"""
    
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # Simple in-memory cache
        self._cache: Dict[str, Optional[str]] = {}
        # Shared async client for connection pooling
        self._client: Optional[httpx.AsyncClient] = None
        # Semaphore to limit concurrent extractions
        self._semaphore = None
    
    async def _get_semaphore(self):
        """Get or create semaphore for limiting concurrent requests"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(10)  # Max 10 concurrent extractions
        return self._semaphore
    
    async def _get_client(self):
        """Get or create shared async client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                follow_redirects=True
            )
        return self._client
    
    async def close(self):
        """Close the shared client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def extract_preview_async(self, url: str) -> Optional[str]:
        """
        Extract preview/thumbnail URL from a video hosting URL (asynchronous)
        Uses semaphore to limit concurrent extractions
        
        Args:
            url: URL to video page (e.g., Bunkr, Gofile)
            
        Returns:
            Preview image URL or None if not found
        """
        # Check cache first
        if url in self._cache:
            return self._cache[url]
        
        # Use semaphore to limit concurrent extractions
        semaphore = await self._get_semaphore()
        async with semaphore:
            # Double-check cache after acquiring semaphore
            if url in self._cache:
                return self._cache[url]
            
            try:
                # For Gofile, just skip - their og:image is just the logo
                if 'gofile' in url.lower():
                    logger.debug(f"Skipping Gofile URL (no real preview available): {url}")
                    self._cache[url] = None
                    return None
                
                # Detect service and extract with timeout
                if 'bunkr' in url.lower():
                    preview = await asyncio.wait_for(
                        self._extract_bunkr_preview_async(url),
                        timeout=8.0  # 8 second timeout per extraction
                    )
                else:
                    # Generic OG image extraction
                    preview = await asyncio.wait_for(
                        self._extract_og_image_async(url),
                        timeout=5.0  # 5 second timeout for generic extraction
                    )
                
                # Cache the result
                self._cache[url] = preview
                return preview
                
            except asyncio.TimeoutError:
                logger.warning(f"Timeout extracting preview from {url}")
                self._cache[url] = None
                return None
            except Exception as e:
                logger.error(f"Error extracting preview from {url}: {e}")
                self._cache[url] = None
                return None
    
    async def _extract_bunkr_preview_async(self, url: str) -> Optional[str]:
        """Extract preview from Bunkr URL (asynchronous)"""
        try:
            # Fetch the page asynchronously using shared client
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Method 1: Try og:image meta tag
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                preview_url = og_image['content']
                logger.info(f"Found Bunkr preview via og:image: {preview_url}")
                return preview_url
            
            # Method 2: Try data-poster attribute on video element
            video = soup.find('video', {'data-poster': True})
            if video:
                preview_url = video['data-poster']
                logger.info(f"Found Bunkr preview via data-poster: {preview_url}")
                return preview_url
            
            # Method 3: Look for thumbnail patterns in HTML
            # Bunkr thumbnails usually follow pattern: https://i-*.bunkr.ru/thumbs/*
            thumb_pattern = r'https://i-[^"\']+\.bunkr\.ru/thumbs/[^"\']+\.(?:png|jpg|jpeg)'
            matches = re.findall(thumb_pattern, html)
            if matches:
                preview_url = matches[0]
                logger.info(f"Found Bunkr preview via pattern matching: {preview_url}")
                return preview_url
            
            logger.warning(f"No preview found for Bunkr URL: {url}")
            return None
                
        except Exception as e:
            logger.error(f"Error extracting Bunkr preview: {e}")
            return None
    
    async def _extract_og_image_async(self, url: str) -> Optional[str]:
        """Generic Open Graph image extraction for unknown services (asynchronous)"""
        try:
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try og:image
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                preview_url = og_image['content']
                logger.info(f"Found preview via og:image: {preview_url}")
                return preview_url
            
            # Try twitter:image
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                preview_url = twitter_image['content']
                logger.info(f"Found preview via twitter:image: {preview_url}")
                return preview_url
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting OG image: {e}")
            return None

# Global instance
video_preview_extractor = VideoPreviewExtractor()
