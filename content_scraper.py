"""
Content Scraper - Simplified main interface using modular components
"""

import asyncio
import logging
from typing import Optional, Dict
from scrapers.fetcher import HTTPFetcher
from scrapers.csv_handler import search_model_in_csv
from scrapers.parsers import (
    extract_max_pages, extract_social_links, extract_preview_images,
    extract_content_links, extract_video_links, group_content_by_type
)

logger = logging.getLogger(__name__)


class SimpleCityScraper:
    """Main scraper class that coordinates all scraping operations."""
    
    def __init__(self, curl_config_path: str = 'curl_config.txt'):
        self.fetcher = HTTPFetcher(curl_config_path)
    
    def search_model_in_csv(self, creator_name: str, csv_path: str = 'onlyfans_models.csv'):
        """Search for a creator in the CSV file."""
        return search_model_in_csv(creator_name, csv_path)
    
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
    
    async def scrape_creator_content(self, creator_name: str, max_pages: int = 3) -> Optional[Dict]:
        """
        Main scraping function that searches CSV and scrapes content
        """
        try:
            # Search for creator in CSV
            logger.info(f"Searching for creator: {creator_name}")
            match = self.search_model_in_csv(creator_name)
            
            if not match:
                logger.info(f"No match found for: {creator_name}")
                return None
            
            matched_name, url, similarity = match
            logger.info(f"Found match: {matched_name} (similarity: {similarity:.2f})")
            
            # Ask for confirmation if similarity is not perfect
            needs_confirmation = similarity < 1.0
            
            # Fetch the first page
            logger.info(f"Fetching page: {url}")
            html = await self.fetch_page(url)
            if not html:
                return None
            
            # Extract social links from first post
            social_links = self.extract_social_links(html)
            logger.info(f"Found social links: OnlyFans={social_links['onlyfans']}, Instagram={social_links['instagram']}")
            
            # Extract preview images
            preview_images = self.extract_preview_images(html)
            logger.info(f"Found {len(preview_images)} preview images on first page")
            
            # Extract video links
            video_links = self.extract_video_links(html)
            logger.info(f"Found {len(video_links)} video links on first page")
            
            # Extract max pages
            total_pages = self.extract_max_pages(html)
            logger.info(f"Total pages available: {total_pages}")
            
            # Limit pages to scrape
            pages_to_scrape = min(max_pages, total_pages)
            
            # Extract content from first page
            all_content = self.extract_content_links(html)
            all_images = preview_images.copy()
            all_videos = video_links.copy()
            
            # Fetch additional pages if available
            if pages_to_scrape > 1:
                for page_num in range(2, pages_to_scrape + 1):
                    page_url = f"{url}page-{page_num}"
                    logger.info(f"Fetching page {page_num}/{pages_to_scrape}: {page_url}")
                    
                    page_html = await self.fetch_page(page_url)
                    if page_html:
                        page_content = self.extract_content_links(page_html)
                        all_content.extend(page_content)
                        
                        page_images = self.extract_preview_images(page_html)
                        all_images.extend(page_images)
                        
                        page_videos = self.extract_video_links(page_html)
                        all_videos.extend(page_videos)
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(1)
            
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
            
            return {
                'creator_name': matched_name,
                'similarity': similarity,
                'needs_confirmation': needs_confirmation,
                'url': url,
                'total_pages': total_pages,
                'pages_scraped': pages_to_scrape,
                'content_items': unique_content,
                'total_items': len(unique_content),
                'preview_images': unique_images,
                'total_images': len(unique_images),
                'video_links': unique_videos,
                'total_videos': len(unique_videos),
                'social_links': social_links
            }
            
        except Exception as e:
            logger.error(f"Error in scrape_creator_content: {e}")
            return None
