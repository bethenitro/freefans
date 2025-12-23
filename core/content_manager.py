"""
Content Manager - Handles content search and organization
"""

import asyncio
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
from core.content_scraper import SimpleCityScraper
from managers.dual_cache_manager import DualCacheManager
from services.landing_service import landing_service

logger = logging.getLogger(__name__)

class ContentManager:
    def __init__(self, cache_manager: Optional[DualCacheManager] = None):
        self.cache = {}
        self.scraper = SimpleCityScraper()
        self.cache_manager = cache_manager or DualCacheManager()
        self.search_providers = []  # Will be populated with search providers later
    
    async def search_creator_options(self, creator_name: str) -> Optional[Dict]:
        """
        Search for creator and return options if similarity is low.
        
        Returns:
            - None if no matches found
            - Dict with 'needs_selection': True and 'options' if similarity < 0.7
            - Dict with single match info if similarity >= 0.7
        """
        return await self.scraper.search_creator_options(creator_name)
    
    async def search_creator_content(self, creator_name: str, filters: Dict, max_pages: int = 3, start_page: int = 1, direct_url: Optional[str] = None, cache_only: bool = True) -> Optional[Dict]:
        """
        Search for creator content with applied filters.
        
        Args:
            creator_name: Name of the creator to search for
            filters: Filters to apply to content
            max_pages: Maximum number of pages to scrape (default 3) - only used if cache_only=False
            start_page: Starting page number (default 1) - only used if cache_only=False
            direct_url: Direct URL to scrape - only used if cache_only=False
            cache_only: If True (default), only return cached data, no external requests
        """
        try:
            # Always check persistent cache first
            cached_result = self.cache_manager.get_creator_cache(creator_name, max_age_hours=24)
            if cached_result:
                # Check if cached result has actual content (not empty cache)
                total_content = (
                    cached_result.get('total_items', 0) + 
                    cached_result.get('total_preview_images', 0) + 
                    cached_result.get('total_video_links', 0)
                )
                
                if total_content > 0:
                    logger.info(f"✓ Using cached content for: {creator_name} ({total_content} items)")
                    # Apply filters to cached content
                    filtered_result = self._apply_filters_to_result(cached_result, filters)
                    return filtered_result
                else:
                    logger.info(f"⚠️  Cached content for {creator_name} is empty (0 items), will fetch fresh data")
                    # Don't use empty cache, treat as cache miss and fetch if allowed
                    cached_result = None
            
            # If cache_only mode and no valid cache, return cache miss
            if cache_only and not cached_result:
                logger.info(f"⚠️  No cached content for: {creator_name} (cache-only mode, not fetching)")
                return {
                    'creator': creator_name,
                    'similarity': 0.0,
                    'needs_confirmation': False,
                    'last_updated': None,
                    'total_items': 0,
                    'items': [],
                    'preview_images': [],
                    'total_preview_images': 0,
                    'video_links': [],
                    'total_video_links': 0,
                    'pages_scraped': 0,
                    'total_pages': 0,
                    'start_page': 1,
                    'end_page': 0,
                    'has_more_pages': False,
                    'social_links': {},
                    'from_cache': False,
                    'cache_miss': True
                }
            
            # Fallback: Use real scraper to get content (only if cache_only=False)
            logger.info(f"Fetching content for creator: {creator_name}, pages {start_page}-{start_page + max_pages - 1}")
            scrape_result = await self.scraper.scrape_creator_content(creator_name, max_pages=max_pages, start_page=start_page, direct_url=direct_url)
            
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
                'start_page': scrape_result['start_page'],
                'end_page': scrape_result['end_page'],
                'has_more_pages': scrape_result['has_more_pages'],
                'social_links': scrape_result.get('social_links', {})  # Pass through social links
            }
            
            # Save to persistent cache for future use
            try:
                cache_data = {
                    'items': content_items,
                    'preview_images': preview_items,
                    'video_links': video_items,
                    'total_pages': scrape_result['total_pages'],
                    'social_links': scrape_result.get('social_links', {})
                }
                self.cache_manager.save_creator_cache(
                    creator_name=scrape_result['creator_name'],
                    url=scrape_result['url'],
                    content_data=cache_data
                )
                logger.info(f"✓ Cached content for {scrape_result['creator_name']}")
            except Exception as e:
                logger.error(f"Failed to cache content for {creator_name}: {e}")
            
            logger.info(f"Found {len(content_items)} items for creator: {creator_name}")
            return result
                
        except Exception as e:
            logger.error(f"Error searching for creator {creator_name}: {e}")
            return None
    
    async def fetch_more_pages(self, creator_name: str, filters: Dict, existing_content: Dict, pages_to_fetch: int = 3) -> Optional[Dict]:
        """
        Fetch additional pages for a creator and merge with existing content.
        
        Args:
            creator_name: Name of the creator
            filters: Filters to apply
            existing_content: The existing content dictionary
            pages_to_fetch: Number of additional pages to fetch (default 3)
        
        Returns:
            Updated content dictionary with merged results
        """
        try:
            # Calculate the starting page for the next batch
            start_page = existing_content['end_page'] + 1
            
            # Fetch more content
            logger.info(f"Fetching additional pages {start_page}-{start_page + pages_to_fetch - 1} for: {creator_name}")
            more_content = await self.search_creator_content(
                creator_name, 
                filters, 
                max_pages=pages_to_fetch, 
                start_page=start_page
            )
            
            if not more_content:
                logger.warning(f"Failed to fetch additional pages for: {creator_name}")
                return existing_content
            
            # Merge the new content with existing content
            # Merge items
            existing_items = existing_content.get('items', [])
            new_items = more_content.get('items', [])
            merged_items = existing_items + new_items
            
            # Merge preview images
            existing_images = existing_content.get('preview_images', [])
            new_images = more_content.get('preview_images', [])
            merged_images = existing_images + new_images
            
            # Merge video links
            existing_videos = existing_content.get('video_links', [])
            new_videos = more_content.get('video_links', [])
            merged_videos = existing_videos + new_videos
            
            # Update the content dictionary
            existing_content['items'] = merged_items
            existing_content['total_items'] = len(merged_items)
            existing_content['preview_images'] = merged_images
            existing_content['total_preview_images'] = len(merged_images)
            existing_content['video_links'] = merged_videos
            existing_content['total_video_links'] = len(merged_videos)
            existing_content['pages_scraped'] = existing_content['pages_scraped'] + more_content['pages_scraped']
            existing_content['end_page'] = more_content['end_page']
            existing_content['has_more_pages'] = more_content['has_more_pages']
            existing_content['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            logger.info(f"Successfully merged additional content. Total items: {len(merged_items)}")
            return existing_content
            
        except Exception as e:
            logger.error(f"Error fetching more pages for {creator_name}: {e}")
            return existing_content
    
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
        
        # Date range filter - skip for now since we don't have real dates from Fetching
        # Can be enhanced later if dates are extracted from the page
        
        # Quality filter - skip for now
        
        return True
    
    async def get_content_download_link(self, creator_name: str, content_idx: int) -> Optional[str]:
        """
        Get download link for specific content.
        Now returns a landing page URL instead of direct content URL.
        """
        try:
            # Look for the content in session cache first
            for cache_key, cache_entry in self.cache.items():
                if cache_key.startswith(creator_name):
                    items = cache_entry['data'].get('items', [])
                    if 0 <= content_idx < len(items):
                        item = items[content_idx]
                        original_url = item.get('url')
                        
                        if original_url:
                            # Generate landing page URL
                            landing_url = await landing_service.generate_landing_url_async(
                                creator_name=creator_name,
                                content_title=item.get('title', 'Untitled Content'),
                                content_type=item.get('type', 'Content'),
                                original_url=original_url,
                                preview_url=item.get('preview_url'),
                                thumbnail_url=item.get('thumbnail_url')
                            )
                            return landing_url
            
            # Try to get from persistent cache
            cached_result = self.cache_manager.get_creator_cache(creator_name, max_age_hours=24)
            if cached_result:
                items = cached_result.get('items', [])
                if 0 <= content_idx < len(items):
                    item = items[content_idx]
                    original_url = item.get('url')
                    
                    if original_url:
                        # Generate landing page URL
                        landing_url = await landing_service.generate_landing_url_async(
                            creator_name=creator_name,
                            content_title=item.get('title', 'Untitled Content'),
                            content_type=item.get('type', 'Content'),
                            original_url=original_url,
                            preview_url=item.get('preview_url'),
                            thumbnail_url=item.get('thumbnail_url')
                        )
                        return landing_url
            
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
    
    def _apply_filters_to_result(self, result: Dict, filters: Dict) -> Dict:
        """Apply filters to a cached result."""
        # Filter items based on content type
        filtered_items = [
            item for item in result.get('items', [])
            if self._matches_filters(item, filters)
        ]
        
        # Create a copy of the result with filtered items
        filtered_result = result.copy()
        filtered_result['items'] = filtered_items
        filtered_result['total_items'] = len(filtered_items)
        
        return filtered_result

    
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