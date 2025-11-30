"""
Content Manager - Handles content search and organization
"""

import asyncio
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
from content_scraper import SimpleCityScraper

logger = logging.getLogger(__name__)

class ContentManager:
    def __init__(self):
        self.cache = {}
        self.scraper = SimpleCityScraper()
        self.search_providers = []  # Will be populated with search providers later
    
    async def search_creator_content(self, creator_name: str, filters: Dict) -> Optional[Dict]:
        """
        Search for creator content with applied filters using real scraper.
        """
        try:
            # Check cache first
            cache_key = f"{creator_name}_{filters.get('content_type', 'all')}"
            if cache_key in self.cache:
                cache_entry = self.cache[cache_key]
                # Use cache if less than 1 hour old
                if (datetime.now() - cache_entry['timestamp']).seconds < 3600:
                    logger.info(f"Returning cached content for: {creator_name}")
                    return cache_entry['data']
            
            # Use real scraper to get content
            logger.info(f"Scraping content for creator: {creator_name}")
            scrape_result = await self.scraper.scrape_creator_content(creator_name, max_pages=3)
            
            if not scrape_result:
                logger.info(f"No content found for creator: {creator_name}")
                return None
            
            # Transform scraped content into our format
            content_items = []
            for idx, item in enumerate(scrape_result['content_items']):
                # Determine content type for filtering
                if item['type'] in ['📷 Photo']:
                    content_cat = 'photos'
                elif item['type'] in ['🎬 Video']:
                    content_cat = 'videos'
                else:
                    content_cat = 'other'
                
                # Use description as title if available
                title = item.get('description')
                if not title:
                    # Create a simple numbered title with type
                    content_type_name = item['type'].split()[1] if ' ' in item['type'] else 'Content'
                    title = f"{content_type_name} #{idx + 1}"
                
                content_item = {
                    'title': title,
                    'type': item['type'],
                    'url': item['url'],
                    'domain': item['domain'],
                    'content_type': content_cat,
                    'upload_date': datetime.now().strftime('%Y-%m-%d'),  # Default to today
                    'quality': 'HD',  # Default quality
                }
                
                # Apply filters
                if self._matches_filters(content_item, filters):
                    content_items.append(content_item)
            
            # Transform preview images
            preview_items = []
            for idx, item in enumerate(scrape_result.get('preview_images', [])):
                preview_item = {
                    'title': f"Picture #{idx + 1}",
                    'type': '🖼️ Picture',
                    'url': item['url'],
                    'domain': item['domain'],
                    'content_type': 'photos',
                    'upload_date': datetime.now().strftime('%Y-%m-%d'),
                    'quality': 'HD',
                }
                preview_items.append(preview_item)
            
            # Transform video links
            video_items = []
            for idx, item in enumerate(scrape_result.get('video_links', [])):
                video_item = {
                    'title': item.get('title', f"Video #{idx + 1}"),
                    'type': '🎬 Video',
                    'url': item['url'],
                    'domain': item['domain'],
                    'content_type': 'videos',
                    'upload_date': datetime.now().strftime('%Y-%m-%d'),
                    'quality': 'HD',
                }
                video_items.append(video_item)
            
            result = {
                'creator': scrape_result['creator_name'],
                'similarity': scrape_result['similarity'],
                'needs_confirmation': scrape_result['needs_confirmation'],
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'total_items': len(content_items),
                'items': content_items,
                'preview_images': preview_items,  # Add preview images
                'total_preview_images': len(preview_items),
                'video_links': video_items,  # Add video links
                'total_video_links': len(video_items),
                'pages_scraped': scrape_result['pages_scraped'],
                'total_pages': scrape_result['total_pages'],
                'social_links': scrape_result.get('social_links', {})  # Pass through social links
            }
            
            # Cache the result
            self.cache[cache_key] = {
                'timestamp': datetime.now(),
                'data': result
            }
            
            logger.info(f"Found {len(content_items)} items for creator: {creator_name}")
            return result
                
        except Exception as e:
            logger.error(f"Error searching for creator {creator_name}: {e}")
            return None
    
    def _generate_mock_content(self, creator_name: str, filters: Dict) -> List[Dict]:
        """
        Generate mock content for demonstration purposes.
        Replace this with actual search implementation.
        """
        base_items = [
            {
                'title': f'{creator_name} - Premium Photo Set #1',
                'type': '📷 Photo',
                'size': '15.2 MB',
                'upload_date': '2024-01-15',
                'quality': 'HD',
                'views': '1.2K',
                'description': 'Exclusive photo collection featuring stunning visuals and high-quality content.',
                'content_type': 'photos',
                'link_placeholder': 'https://example.com/content1'
            },
            {
                'title': f'{creator_name} - Behind the Scenes Video',
                'type': '🎬 Video',
                'size': '125.8 MB',
                'upload_date': '2024-01-14',
                'quality': 'HD',
                'views': '3.5K',
                'description': 'Exclusive behind-the-scenes footage from recent photoshoot.',
                'content_type': 'videos',
                'link_placeholder': 'https://example.com/content2'
            },
            {
                'title': f'{creator_name} - Live Stream Highlights',
                'type': '🎬 Video',
                'size': '89.3 MB',
                'upload_date': '2024-01-13',
                'quality': 'Standard',
                'views': '2.8K',
                'description': 'Best moments from recent live streaming session.',
                'content_type': 'videos',
                'link_placeholder': 'https://example.com/content3'
            },
            {
                'title': f'{creator_name} - Photo Collection #2',
                'type': '📷 Photo',
                'size': '28.7 MB',
                'upload_date': '2024-01-12',
                'quality': 'HD',
                'views': '4.1K',
                'description': 'Latest photo series with premium content and exclusive shots.',
                'content_type': 'photos',
                'link_placeholder': 'https://example.com/content4'
            },
            {
                'title': f'{creator_name} - Tutorial Video',
                'type': '🎬 Video',
                'size': '156.9 MB',
                'upload_date': '2024-01-10',
                'quality': 'HD',
                'views': '6.7K',
                'description': 'Educational content and tutorials for fans and followers.',
                'content_type': 'videos',
                'link_placeholder': 'https://example.com/content5'
            }
        ]
        
        # Apply content type filter
        filtered_items = []
        for item in base_items:
            if self._matches_filters(item, filters):
                filtered_items.append(item)
        
        return filtered_items
    
    
    def _matches_filters(self, item: Dict, filters: Dict) -> bool:
        """Check if an item matches the applied filters."""
        
        # Content type filter
        content_type_filter = filters.get('content_type', 'all').lower()
        if content_type_filter != 'all':
            if content_type_filter == 'photos' and item['content_type'] != 'photos':
                return False
            elif content_type_filter == 'videos' and item['content_type'] != 'videos':
                return False
        
        # Date range filter - skip for now since we don't have real dates from scraping
        # Can be enhanced later if dates are extracted from the page
        
        # Quality filter - skip for now
        
        return True
    
    async def get_content_download_link(self, creator_name: str, content_idx: int) -> Optional[str]:
        """
        Get download link for specific content.
        Returns the actual URL from the scraped content.
        """
        try:
            # Look for the content in cache
            for cache_key, cache_entry in self.cache.items():
                if cache_key.startswith(creator_name):
                    items = cache_entry['data'].get('items', [])
                    if 0 <= content_idx < len(items):
                        return items[content_idx].get('url')
            
            logger.warning(f"Content not found in cache: {creator_name} idx {content_idx}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting download link: {e}")
            return None
    
    async def get_content_preview(self, creator_name: str, content_idx: int) -> Optional[Dict]:
        """
        Get preview information for content.
        This is a placeholder for future preview functionality.
        """
        try:
            # Simulate preview generation
            await asyncio.sleep(0.5)
            
            return {
                'preview_url': f"https://preview.example.com/{creator_name}/content_{content_idx}",
                'thumbnail_url': f"https://thumbnails.example.com/{creator_name}/content_{content_idx}.jpg",
                'preview_type': 'image' if content_idx % 2 == 0 else 'video'
            }
            
        except Exception as e:
            logger.error(f"Error generating preview: {e}")
            return None
    
    def clear_cache(self):
        """Clear the content cache."""
        self.cache.clear()
        logger.info("Content cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            'cache_size': len(self.cache),
            'cached_creators': list(self.cache.keys())
        }