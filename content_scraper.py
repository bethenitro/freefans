"""
Content Scraper - Extracts content links from simpcity.cr pages
"""

import httpx
import csv
import asyncio
import re
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class SimpleCityScraper:
    def __init__(self, curl_config_path: str = 'curl_config.txt'):
        # Load headers and cookies from curl_config.txt
        headers, cookies = self._load_curl_config(curl_config_path)
        self.headers = headers
        self.cookies = cookies
    
    def _load_curl_config(self, config_path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Parse curl_config.txt and extract headers and cookies.
        Returns (headers_dict, cookies_dict)
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"curl_config.txt not found, using default headers")
                return self._get_default_headers()
            
            curl_command = config_file.read_text()
            
            headers = {}
            cookies = {}
            
            # Find all -H 'Header: value' patterns
            header_pattern = r"-H\s+'([^:]+):\s*([^']+)'"
            header_matches = re.findall(header_pattern, curl_command)
            
            for header_name, header_value in header_matches:
                header_name = header_name.strip()
                header_value = header_value.strip()
                
                if header_name.lower() == 'cookie':
                    # Parse cookies
                    cookie_parts = header_value.split(';')
                    for part in cookie_parts:
                        part = part.strip()
                        if '=' in part:
                            cookie_name, cookie_value = part.split('=', 1)
                            cookies[cookie_name.strip()] = cookie_value.strip()
                else:
                    headers[header_name] = header_value
            
            if not headers:
                logger.warning("No headers found in curl_config.txt, using defaults")
                return self._get_default_headers()
            
            logger.info(f"Loaded {len(headers)} headers and {len(cookies)} cookies from {config_path}")
            return headers, cookies
            
        except Exception as e:
            logger.error(f"Error loading curl config: {e}, using default headers")
            return self._get_default_headers()
    
    def _get_default_headers(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Return default headers and cookies as fallback."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Sec-GPC': '1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Connection': 'keep-alive',
        }
        cookies = {
            '__ddg8_': 'PsWCIUg2WRiSDeKJ',
            '__ddg10_': '1764475963',
            '__ddg9_': '175.110.114.88',
            '__ddg1_': 'v36dU5thIcnH3qDRm6AY',
            '__ddg8_': 'PsWCIUg2WRiSDeKJ',
            '__ddg10_': '1764475963',
            '__ddg9_': '175.110.114.88',
            '__ddg1_': 'v36dU5thIcnH3qDRm6AY',
        }
        return headers, cookies
        
    def search_model_in_csv(self, creator_name: str, csv_path: str = 'onlyfans_models.csv') -> Optional[Tuple[str, str, float]]:
        """
        Search for a creator in the CSV file.
        Returns (matched_name, url, similarity_score) or None
        """
        try:
            best_match = None
            best_score = 0.0
            creator_name_lower = creator_name.lower()
            
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    model_name = row['model_name']
                    profile_link = row['profile_link']
                    
                    # Check for exact match first
                    if creator_name_lower == model_name.lower():
                        return (model_name, profile_link, 1.0)
                    
                    # Check if creator name is in model name (handles aliases)
                    if creator_name_lower in model_name.lower():
                        score = 0.9
                        if score > best_score:
                            best_score = score
                            best_match = (model_name, profile_link, score)
                    
                    # Calculate similarity using SequenceMatcher
                    similarity = SequenceMatcher(None, creator_name_lower, model_name.lower()).ratio()
                    if similarity > best_score:
                        best_score = similarity
                        best_match = (model_name, profile_link, similarity)
            
            # Only return matches with at least 60% similarity
            if best_match and best_score >= 0.6:
                return best_match
                
            return None
            
        except Exception as e:
            logger.error(f"Error searching CSV: {e}")
            return None
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page from simpcity.cr"""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    url, 
                    headers=self.headers,
                    cookies=self.cookies
                )
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}")
            return None
    
    def extract_max_pages(self, html: str) -> int:
        """Extract the maximum number of pages from pagination"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the pagination section
            page_nav = soup.find('nav', class_='pageNavWrapper')
            if not page_nav:
                return 1
            
            # Find all page links
            page_links = page_nav.find_all('li', class_='pageNav-page')
            if not page_links:
                return 1
            
            # Get the highest page number
            max_page = 1
            for link_li in page_links:
                link = link_li.find('a')
                if link:
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        page_num = int(text)
                        max_page = max(max_page, page_num)
            
            return max_page
            
        except Exception as e:
            logger.error(f"Error extracting max pages: {e}")
            return 1
    
    def extract_social_links(self, html: str) -> Dict[str, str]:
        """Extract OnlyFans and Instagram links from the first post"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            social_links = {
                'onlyfans': None,
                'instagram': None
            }
            
            # Find the first message block (original post)
            first_message = soup.find('article', class_='message')
            if not first_message:
                return social_links
            
            message_body = first_message.find('div', class_='bbWrapper')
            if not message_body:
                return social_links
            
            # Find all links in the first post
            links = message_body.find_all('a', href=True)
            
            for link in links:
                href = link['href'].lower()
                
                # Extract OnlyFans link (take the first one found)
                if 'onlyfans.com' in href and not social_links['onlyfans']:
                    social_links['onlyfans'] = link['href']
                
                # Extract Instagram link
                elif 'instagram.com' in href and not social_links['instagram']:
                    social_links['instagram'] = link['href']
                
                # Stop if we found both
                if social_links['onlyfans'] and social_links['instagram']:
                    break
            
            return social_links
            
        except Exception as e:
            logger.error(f"Error extracting social links: {e}")
            return {'onlyfans': None, 'instagram': None}
    
    def extract_preview_images(self, html: str) -> List[Dict[str, str]]:
        """Extract all preview images from posts (jpg, png, gif, webp)"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            preview_images = []
            seen_urls = set()
            
            # Find all message blocks
            message_blocks = soup.find_all('article', class_='message')
            
            for block in message_blocks:
                message_body = block.find('div', class_='bbWrapper')
                if not message_body:
                    continue
                
                # Find all img tags
                images = message_body.find_all('img', src=True)
                
                for img in images:
                    src = img.get('src', '')
                    data_url = img.get('data-url', '')
                    
                    # Use data-url if available, otherwise src
                    img_url = data_url if data_url else src
                    
                    # Check if it's an image URL
                    if any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        # Skip if already seen
                        if img_url in seen_urls:
                            continue
                        seen_urls.add(img_url)
                        
                        # Get alt text or title for description
                        description = img.get('alt', '') or img.get('title', '')
                        
                        # Skip avatar images and small icons
                        if 'avatar' in img_url.lower() or 'icon' in img_url.lower():
                            continue
                        
                        preview_images.append({
                            'url': img_url,
                            'link_text': description or 'Preview Image',
                            'description': description if description else None,
                            'context': '',
                            'type': '📷 Photo',
                            'domain': self._extract_domain(img_url)
                        })
            
            return preview_images
            
        except Exception as e:
            logger.error(f"Error extracting preview images: {e}")
            return []
    
    def extract_content_links(self, html: str) -> List[Dict[str, str]]:
        """Extract bunkr, pixl, gofile, and other content links from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            content_items = []
            
            # Find all message blocks containing content
            message_blocks = soup.find_all('article', class_='message')
            
            for block in message_blocks:
                message_body = block.find('div', class_='bbWrapper')
                if not message_body:
                    continue
                
                # Get message text for context
                message_text = message_body.get_text(strip=True)[:200]  # First 200 chars
                
                # Find all links
                links = message_body.find_all('a', href=True)
                
                for link in links:
                    href = link['href']
                    link_text = link.get_text(strip=True)
                    
                    # Check if it's a content link (bunkr, pixl, gofile, cdn, etc.)
                    if any(domain in href.lower() for domain in [
                        'bunkr.', 'pixl.', 'gofile.', 'cdn.', 'imgur.', 
                        'jpg6.su', 'simp', 'delivery'
                    ]):
                        # Determine content type based on URL
                        content_type = self._determine_content_type(href, link_text)
                        
                        # Extract descriptive text near the link
                        description = self._extract_link_description(link)
                        
                        # Find nearby text for context (fallback)
                        parent = link.find_parent(['p', 'div'])
                        context = parent.get_text(strip=True)[:150] if parent else message_text[:150]
                        
                        content_items.append({
                            'url': href,
                            'link_text': link_text,
                            'description': description,  # Add description field
                            'context': context,
                            'type': content_type,
                            'domain': self._extract_domain(href)
                        })
            
            return content_items
            
        except Exception as e:
            logger.error(f"Error extracting content links: {e}")
            return []
    
    def _determine_content_type(self, url: str, text: str) -> str:
        """Determine the type of content from URL and link text"""
        url_lower = url.lower()
        text_lower = text.lower()
        
        # Check for galleries/albums
        if 'album' in url_lower or 'gallery' in url_lower or 'album' in text_lower:
            return '📁 Album'
        
        # Check for video indicators
        if any(ext in url_lower for ext in ['.mov', '.mp4', '.avi', '.mkv']):
            return '🎬 Video'
        
        if 'video' in text_lower or 'vid' in text_lower:
            return '🎬 Video'
        
        # Check for image indicators
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return '📷 Photo'
        
        if 'pic' in text_lower or 'photo' in text_lower or 'img' in text_lower:
            return '📷 Photo'
        
        # Check for collections
        if 'bunkr.cr/a/' in url_lower or 'pixl.li/album/' in url_lower:
            return '📦 Collection'
        
        return '📄 Content'
    
    def _extract_link_description(self, link_element) -> Optional[str]:
        """
        Extract descriptive text near a link.
        Returns the description if it's short enough (under 20 words), otherwise None.
        """
        try:
            # Find the immediate parent div/p of the link
            parent_div = link_element.find_parent(['div', 'p'])
            if not parent_div:
                return None
            
            # Get the grandparent (usually bbWrapper)
            grandparent = parent_div.find_parent('div', class_='bbWrapper')
            if not grandparent:
                grandparent = parent_div.find_parent('div')
            
            if not grandparent:
                return None
            
            # Look for text nodes that are siblings before this parent div
            description_candidates = []
            
            # Iterate through siblings before the parent_div
            for sibling in grandparent.children:
                if sibling == parent_div:
                    # We've reached the link's parent, stop
                    break
                
                if hasattr(sibling, 'name'):
                    if sibling.name == 'br':
                        # br tags separate sections
                        continue
                    # Get text from this element
                    text = sibling.get_text(strip=True)
                    if text and len(text) > 0:
                        description_candidates.append(text)
                else:
                    # It's a text node
                    text = str(sibling).strip()
                    if text and text not in ['\n', '', ' ']:
                        description_candidates.append(text)
            
            if not description_candidates:
                return None
            
            # Get the last candidate (closest to the link)
            description = description_candidates[-1]
            
            # Count words
            words = description.split()
            word_count = len(words)
            
            # Only return if it's a reasonable title length (2-20 words)
            if 2 <= word_count <= 20:
                # Skip if it looks like a URL
                if 'http' in description.lower() or 'www.' in description.lower():
                    return None
                
                # Skip if it contains multiple URLs or links
                if description.count('.com') > 1 or description.count('.ru') > 1:
                    return None
                
                return description
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting link description: {e}")
            return None
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return 'unknown'
    
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
            
            # Extract max pages
            total_pages = self.extract_max_pages(html)
            logger.info(f"Total pages available: {total_pages}")
            
            # Limit pages to scrape
            pages_to_scrape = min(max_pages, total_pages)
            
            # Extract content from first page
            all_content = self.extract_content_links(html)
            all_images = preview_images.copy()
            
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
            
            logger.info(f"Found {len(unique_content)} unique content items")
            logger.info(f"Found {len(unique_content)} unique content items")
            logger.info(f"Found {len(unique_images)} unique preview images")
            
            return {
                'creator_name': matched_name,
                'similarity': similarity,
                'needs_confirmation': needs_confirmation,
                'url': url,
                'total_pages': total_pages,
                'pages_scraped': pages_to_scrape,
                'content_items': unique_content,
                'total_items': len(unique_content),
                'preview_images': unique_images,  # Add preview images
                'total_images': len(unique_images),
                'social_links': social_links  # Add social links to the return data
            }
            
        except Exception as e:
            logger.error(f"Error in scrape_creator_content: {e}")
            return None
    
    def group_content_by_type(self, content_items: List[Dict]) -> Dict[str, List[Dict]]:
        """Group content items by type"""
        grouped = {}
        for item in content_items:
            content_type = item['type']
            if content_type not in grouped:
                grouped[content_type] = []
            grouped[content_type].append(item)
        return grouped
