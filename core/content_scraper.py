"""
Content Scraper - Simplified main interface using modular components
"""

import asyncio
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from scrapers.fetcher import HTTPFetcher
from scrapers.csv_handler import search_model_in_csv, search_multiple_models_in_csv, search_multiple_models_in_csv_parallel
from scrapers.parsers import (
    extract_max_pages, extract_social_links, extract_preview_images,
    extract_content_links, extract_video_links, group_content_by_type,
    parse_page_content_concurrent
)
from scrapers.simpcity_search import (
    build_search_url, parse_search_results, add_creator_to_csv, 
    extract_creator_name_from_title
)

logger = logging.getLogger(__name__)

# Content cache to store complete scraping results
_content_cache = {}
_content_cache_ttl = timedelta(minutes=15)  # Cache content for 15 minutes
_content_cache_max_size = 50


def _get_content_cache_key(url: str, start_page: int, max_pages: int) -> str:
    """Generate cache key for content scraping."""
    return f"{url}|{start_page}|{max_pages}"


def _clean_content_cache():
    """Remove expired entries from content cache."""
    global _content_cache
    now = datetime.now()
    expired_keys = [
        key for key, value in _content_cache.items()
        if now - value['timestamp'] > _content_cache_ttl
    ]
    for key in expired_keys:
        del _content_cache[key]
        logger.debug(f"Removed expired cache entry: {key}")
    
    # If cache is too large, remove oldest entries
    if len(_content_cache) > _content_cache_max_size:
        sorted_items = sorted(_content_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_items[:len(_content_cache) - _content_cache_max_size]:
            del _content_cache[key]
            logger.debug(f"Removed old cache entry: {key}")


def _get_cached_content(url: str, start_page: int, max_pages: int) -> Optional[Dict]:
    """Get cached content if available."""
    _clean_content_cache()
    cache_key = _get_content_cache_key(url, start_page, max_pages)
    
    if cache_key in _content_cache:
        logger.info(f"✓ Content cache hit for {url} (pages {start_page}-{start_page+max_pages-1})")
        return _content_cache[cache_key]['data']
    return None


def _cache_content(url: str, start_page: int, max_pages: int, data: Dict):
    """Cache content scraping results."""
    cache_key = _get_content_cache_key(url, start_page, max_pages)
    _content_cache[cache_key] = {
        'data': data,
        'timestamp': datetime.now()
    }
    logger.info(f"✓ Cached content for {url} (cache size: {len(_content_cache)})")


class SimpleCityScraper:
    """Main scraper class that coordinates all Fetching operations."""
    
    def __init__(self, curl_config_path: str = 'shared/config/curl_config.txt'):
        self.fetcher = HTTPFetcher(curl_config_path)
    
    async def close(self):
        """Close the HTTP fetcher and cleanup resources."""
        if hasattr(self, 'fetcher') and self.fetcher:
            await self.fetcher.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def search_model_in_csv(self, creator_name: str, csv_path: str = 'data/onlyfans_models.csv'):
        """Search for a creator in the CSV file."""
        return search_model_in_csv(creator_name, csv_path)
    
    def search_multiple_models_in_csv(self, creator_name: str, csv_path: str = 'data/onlyfans_models.csv', max_results: int = 5):
        """Search for multiple potential matches in the CSV file."""
        return search_multiple_models_in_csv(creator_name, csv_path, max_results)
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page from simpcity.cr"""
        return await self.fetcher.fetch_page(url)
    
    def extract_max_pages(self, html: str) -> int:
        """Extract the maximum number of pages from pagination"""
        return extract_max_pages(html)
    
    def extract_social_links(self, html: str) -> Dict[str, str]:
        """Extract OnlyFans and Instagram links from the first post"""
        return extract_social_links(html)
    
    def extract_preview_images(self, html: str):
        """Extract all preview images from posts"""
        return extract_preview_images(html)
    
    def extract_content_links(self, html: str):
        """Extract bunkr, gofile, and other content links from HTML"""
        return extract_content_links(html)
    
    def extract_video_links(self, html: str):
        """Extract video links with intelligent titles"""
        return extract_video_links(html)
    
    def group_content_by_type(self, content_items):
        """Group content items by type"""
        return group_content_by_type(content_items)
    
    async def search_simpcity(self, creator_name: str) -> Optional[List[Dict]]:
        """
        Search for creator on SimpCity when not found in CSV.
        Returns list of search results filtered for OnlyFans forum or OnlyFans labeled content with >1 reply,
        ranked by fuzzy matching against the query.
        """
        try:
            search_url = build_search_url(creator_name)
            logger.info(f"Searching SimpCity for: {creator_name}")
            logger.info(f"Search URL: {search_url}")
            
            html = await self.fetch_page(search_url)
            if not html:
                logger.error("Failed to fetch search results page")
                return None
            
            results = parse_search_results(html)
            
            if not results:
                logger.info(f"No valid results found for {creator_name}")
                return None
            
            logger.info(f"Found {len(results)} raw results for {creator_name}")
            
            # Apply fuzzy search ranking to get best matches
            from scrapers.simpcity_search import rank_search_results_by_query
            ranked_results = rank_search_results_by_query(creator_name, results, limit=15)
            
            if ranked_results:
                logger.info(f"Returning {len(ranked_results)} ranked results")
            
            return ranked_results if ranked_results else results
            
        except Exception as e:
            logger.error(f"Error searching SimpCity: {e}")
            return None
    
    def add_creator_to_csv(self, creator_name: str, profile_url: str) -> bool:
        """Add a new creator to the CSV file."""
        return add_creator_to_csv(creator_name, profile_url)
    
    async def search_creator_options(self, creator_name: str) -> Optional[Dict]:
        """
        Search for creator and return multiple options.
        First searches CSV using rapidfuzz, then falls back to SimpCity search if not found.
        
        Returns:
            - None if no matches found
            - Dict with 'needs_selection': True and 'options' for all searches
            - Dict with 'simpcity_search': True if showing SimpCity results
        """
        try:
            logger.info(f"Searching for creator options: {creator_name}")
            
            # First, try CSV search with rapidfuzz for better performance and accuracy
            from scrapers.csv_handler import search_csv_with_rapidfuzz
            multiple_matches = await search_csv_with_rapidfuzz(creator_name, max_results=10)
            
            if multiple_matches:
                # Filter matches with at least 50% similarity
                filtered_matches = [m for m in multiple_matches if m[2] >= 0.5]
                
                if filtered_matches:
                    logger.info(f"Found {len(filtered_matches)} CSV matches with rapidfuzz, showing options")
                    
                    # Always show options for user to select
                    return {
                        'needs_selection': True,
                        'options': [
                            {
                                'name': name,
                                'url': url,
                                'similarity': sim,
                                'source': 'csv'
                            }
                            for name, url, sim in filtered_matches[:10]  # Show up to 10 matches
                        ],
                        'searched_name': creator_name,
                        'simpcity_search': False
                    }
            
            # If no CSV matches, search SimpCity with fuzzy ranking
            logger.info(f"No CSV matches found, searching SimpCity for: {creator_name}")
            simpcity_results = await self.search_simpcity(creator_name)
            
            if not simpcity_results:
                logger.info(f"No SimpCity results found for: {creator_name}")
                return None
            
            # Format SimpCity results for display
            logger.info(f"Found {len(simpcity_results)} SimpCity results")
            return {
                'needs_selection': True,
                'simpcity_search': True,
                'options': [
                    {
                        'name': result['title'],
                        'url': result['url'],
                        'replies': result['replies'],
                        'date': result['date'],
                        'snippet': result['snippet'],
                        'thumbnail': result['thumbnail'],
                        'source': 'simpcity'
                    }
                    for result in simpcity_results
                ],
                'searched_name': creator_name
            }
                
        except Exception as e:
            logger.error(f"Error in search_creator_options: {e}")
            return None
    
    async def scrape_creator_content(self, creator_name: str, max_pages: int = None, start_page: int = 1, direct_url: Optional[str] = None) -> Optional[Dict]:
        """
        Main Fetching function that searches CSV and scrapes content
        
        Args:
            creator_name: Name of the creator to search for
            max_pages: Maximum number of pages to scrape (None = all pages, default 3)
            start_page: Starting page number (default 1, for fetching additional pages)
            direct_url: Direct URL to scrape (bypasses CSV search, for pre-selected creators)
        """
        try:
            # If direct_url is provided, skip CSV search
            if direct_url:
                matched_name = creator_name
                url = direct_url
                similarity = 1.0
                needs_confirmation = False
                logger.info(f"Using direct URL for: {creator_name}")
            else:
                # Search for creator in CSV
                logger.info(f"Searching for creator: {creator_name}")
                match = self.search_model_in_csv(creator_name)
                
                if not match:
                    logger.info(f"No match found for: {creator_name}")
                    return None
                
                matched_name, url, similarity = match
                logger.info(f"Found match: {matched_name} (similarity: {similarity:.2f})")
                
                # Ask for confirmation if similarity is less than 70%
                needs_confirmation = similarity < 0.7
            
            # Check cache first
            cached_result = _get_cached_content(url, start_page, max_pages)
            if cached_result is not None:
                return cached_result
            
            # Fetch the first page
            logger.info(f"Fetching page: {url}")
            html = await self.fetch_page(url)
            if not html:
                return None
            
            # Extract social links from first post (only on first run)
            social_links = {'onlyfans': None, 'instagram': None}
            if start_page == 1:
                social_links = self.extract_social_links(html)
                logger.info(f"Found social links: OnlyFans={social_links['onlyfans']}, Instagram={social_links['instagram']}")
            
            # Extract content from first page using concurrent parsing
            all_content, preview_images, video_links = await parse_page_content_concurrent(html)
            logger.info(f"Found {len(preview_images)} preview images on first page")
            logger.info(f"Found {len(video_links)} video links on first page")
            
            # Extract max pages
            total_pages = self.extract_max_pages(html)
            logger.info(f"Total pages available: {total_pages}")
            
            # Limit pages to scrape (start from start_page and scrape up to max_pages)
            # If max_pages is None, scrape all available pages
            if max_pages is None:
                end_page = total_pages
            else:
                end_page = min(start_page + max_pages - 1, total_pages)
            pages_to_scrape = end_page - start_page + 1
            logger.info(f"Will scrape {pages_to_scrape} pages (from {start_page} to {end_page})")
            
            # Create lists for aggregating content
            all_images = preview_images.copy()
            all_videos = video_links.copy()
            
            # Fetch additional pages if available - ENHANCED WITH MULTITHREADED FETCHING
            if pages_to_scrape > 1 or start_page > 1:
                # Determine the range of pages to fetch
                page_start = start_page + 1 if start_page == 1 else start_page
                page_end = end_page + 1
                
                # Create URLs for all pages to fetch
                page_urls = [f"{url}page-{page_num}" for page_num in range(page_start, page_end)]
                
                logger.info(f"🚀 Fetching {len(page_urls)} pages concurrently with enhanced multithreading...")
                
                # Use the enhanced multithreaded fetcher
                page_results = await self.fetcher.fetch_multiple_pages(
                    urls=page_urls,
                    max_concurrent=5  # Conservative concurrency for stability
                )
                
                # Process results concurrently
                async def parse_page_result(url_content_tuple):
                    """Parse a single page result."""
                    page_url, page_html = url_content_tuple
                    if page_html:
                        page_num = int(page_url.split('page-')[1]) if 'page-' in page_url else 1
                        logger.debug(f"✅ Parsing page {page_num}")
                        return await parse_page_content_concurrent(page_html)
                    else:
                        page_num = int(page_url.split('page-')[1]) if 'page-' in page_url else 1
                        logger.warning(f"❌ Failed to fetch page {page_num}")
                        return [], [], []
                
                # Parse all pages concurrently
                parse_tasks = [parse_page_result(result) for result in page_results]
                parse_results = await asyncio.gather(*parse_tasks)
                
                # Aggregate results from all pages
                for page_content, page_images, page_videos in parse_results:
                    all_content.extend(page_content)
                    all_images.extend(page_images)
                    all_videos.extend(page_videos)
                
                logger.info(f"✅ Enhanced multithreaded fetching completed for {len(page_urls)} pages")
            
            # Remove duplicates based on URL
            unique_content = []
            seen_urls = set()
            for item in all_content:
                if item['url'] not in seen_urls:
                    seen_urls.add(item['url'])
                    unique_content.append(item)
            
            # Remove duplicate images
            unique_images = []
            seen_image_urls = set()
            for item in all_images:
                if item['url'] not in seen_image_urls:
                    seen_image_urls.add(item['url'])
                    unique_images.append(item)
            
            # Remove duplicate videos
            unique_videos = []
            seen_video_urls = set()
            for item in all_videos:
                if item['url'] not in seen_video_urls:
                    seen_video_urls.add(item['url'])
                    unique_videos.append(item)
            
            logger.info(f"Found {len(unique_content)} unique content items")
            logger.info(f"Found {len(unique_images)} unique preview images")
            logger.info(f"Found {len(unique_videos)} unique video links")
            
            result = {
                'creator_name': matched_name,
                'similarity': similarity,
                'needs_confirmation': needs_confirmation,
                'url': url,
                'total_pages': total_pages,
                'pages_scraped': end_page - start_page + 1,
                'start_page': start_page,
                'end_page': end_page,
                'has_more_pages': end_page < total_pages,
                'content_items': unique_content,
                'total_items': len(unique_content),
                'preview_images': unique_images,
                'total_images': len(unique_images),
                'video_links': unique_videos,
                'total_videos': len(unique_videos),
                'social_links': social_links
            }
            
            # Cache the result
            _cache_content(url, start_page, max_pages, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in scrape_creator_content: {e}")
            return None
