"""
HTML Parsers - Extract data from HTML content
"""

import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urlparse
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools
import hashlib
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

# Create a thread pool executor for CPU-bound parsing tasks
# Increased workers from 4 to 8 for better performance
_executor = ThreadPoolExecutor(max_workers=8)

# Cache for parsed HTML content to avoid re-parsing
_html_parse_cache = {}
_cache_max_size = 100
_cache_ttl = timedelta(minutes=10)


def _get_html_hash(html: str) -> str:
    """Generate a hash for HTML content for caching."""
    return hashlib.md5(html.encode('utf-8')).hexdigest()[:16]


def _clean_html_cache():
    """Remove expired entries from HTML cache."""
    global _html_parse_cache
    now = datetime.now()
    expired_keys = [
        key for key, value in _html_parse_cache.items()
        if now - value['timestamp'] > _cache_ttl
    ]
    for key in expired_keys:
        del _html_parse_cache[key]
    
    # If cache is too large, remove oldest entries
    if len(_html_parse_cache) > _cache_max_size:
        sorted_items = sorted(_html_parse_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_items[:len(_html_parse_cache) - _cache_max_size]:
            del _html_parse_cache[key]


def _get_cached_parse(html: str, cache_key: str):
    """Get cached parse result if available."""
    _clean_html_cache()
    html_hash = _get_html_hash(html)
    full_key = f"{cache_key}_{html_hash}"
    
    if full_key in _html_parse_cache:
        logger.debug(f"Cache hit for {cache_key}")
        return _html_parse_cache[full_key]['data']
    return None


def _cache_parse_result(html: str, cache_key: str, data):
    """Cache parse result."""
    html_hash = _get_html_hash(html)
    full_key = f"{cache_key}_{hash}"
    _html_parse_cache[full_key] = {
        'data': data,
        'timestamp': datetime.now()
    }
    logger.debug(f"Cached {cache_key} (cache size: {len(_html_parse_cache)})")


def is_valid_content_image(image_url: str, min_size_indicator: int = 300) -> bool:
    """
    Filter out logos, icons, and other non-content images.
    Uses multiple heuristics for robust filtering without external API calls.
    
    Args:
        image_url: The image URL to validate
        min_size_indicator: Minimum dimension to consider as content (default 300px)
    
    Returns:
        bool: True if likely a content image, False otherwise
    """
    url_lower = image_url.lower()
    parsed = urlparse(image_url)
    path = parsed.path.lower()
    
    # Keywords that indicate non-content images
    exclude_keywords = [
        'logo', 'icon', 'avatar', 'profile', 'banner', 'header',
        'footer', 'badge', 'button', 'emoji', 'twemoji', 'smilie',
        'reaction', 'favicon', 'thumbnail_small', 'thumb_', 
        'preview_small', '_icon', '-icon', '_logo', '-logo',
        'watermark', 'signature', 'brand'
    ]
    
    # CDN domains known for serving UI elements
    exclude_domains = [
        'cdn.jsdelivr.net/gh/twitter/twemoji',
        'twemoji.maxcdn.com',
        'abs.twimg.com',
        'emoji.discourse-cdn.com'
    ]
    
    # 1. Check for excluded domains
    for domain in exclude_domains:
        if domain in url_lower:
            logger.debug(f"Filtered out (excluded domain): {image_url[:100]}")
            return False
    
    # 2. Check for excluded keywords in URL
    if any(keyword in url_lower for keyword in exclude_keywords):
        logger.debug(f"Filtered out (keyword match): {image_url[:100]}")
        return False
    
    # 3. Check file extension (icons often use specific extensions)
    if path.endswith('.ico'):
        return False
    
    if path.endswith('.svg') or path.endswith('.webp'):
        # SVG and WebP CAN be content, but check size indicators
        size_match = re.search(r'(\d+)x(\d+)', url_lower)
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            # Icons are typically < 300x300
            if width < min_size_indicator and height < min_size_indicator:
                logger.debug(f"Filtered out (small SVG/WebP {width}x{height}): {image_url[:100]}")
                return False
    
    # 4. Check for small dimensions in URL path
    # Common patterns: /72x72/, /icon_128x128, thumbnail_50x50, etc.
    small_size_patterns = [
        r'/(\d{1,3})x(\d{1,3})/',  # /72x72/
        r'_(\d{1,3})x(\d{1,3})[._]',  # _72x72.png or _72x72_
        r'-(\d{1,3})x(\d{1,3})[._-]',  # -72x72.png
    ]
    
    for pattern in small_size_patterns:
        match = re.search(pattern, path)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            # Consider images smaller than min_size_indicator as likely icons/logos
            if width < min_size_indicator and height < min_size_indicator:
                logger.debug(f"Filtered out (small dimensions {width}x{height}): {image_url[:100]}")
                return False
    
    # 5. Check for "thumb" or "thumbnail" with small size indicator
    if ('thumb' in url_lower or 'thumbnail' in url_lower):
        # If it's explicitly marked as thumbnail AND has small dimensions
        size_match = re.search(r'(\d{2,4})', path)
        if size_match and int(size_match.group(1)) < min_size_indicator:
            logger.debug(f"Filtered out (thumbnail): {image_url[:100]}")
            return False
    
    # 6. Check for CDN optimization parameters that indicate small images
    # e.g., ?w=72, ?width=100, ?size=small
    query = parsed.query.lower()
    if query:
        size_params = re.findall(r'(?:w|width|size|s)=(\d+)', query)
        if size_params:
            for size in size_params:
                if int(size) < min_size_indicator:
                    logger.debug(f"Filtered out (small query param): {image_url[:100]}")
                    return False
        
        # Check for explicit "small" or "icon" size parameters
        if any(param in query for param in ['size=small', 'size=icon', 'type=icon']):
            logger.debug(f"Filtered out (icon/small param): {image_url[:100]}")
            return False
    
    # 7. Check filename patterns
    filename = path.split('/')[-1].lower()
    
    # Very short filenames are often icons (e.g., "icon.png", "logo.jpg")
    if len(filename) < 10 and any(word in filename for word in ['icon', 'logo', 'btn']):
        logger.debug(f"Filtered out (short icon filename): {image_url[:100]}")
        return False
    
    # Emoji/Unicode pattern in filename
    if re.search(r'[0-9a-f]{4,}(-[0-9a-f]{4,})+', filename):
        # Pattern like: 1f9b8-200d-2642-fe0f.png (emoji code)
        logger.debug(f"Filtered out (emoji pattern): {image_url[:100]}")
        return False
    
    # 8. All checks passed - likely a content image
    return True


def load_video_domains(file_path: str = 'video_domains.txt') -> List[str]:
    """Load video hosting domains from configuration file."""
    domains = []
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        domains.append(line.lower())
            logger.info(f"Loaded {len(domains)} video domains from {file_path}")
        else:
            # Fallback to default domains if file doesn't exist
            domains = ['bunkr.', 'gofile.', 'cdn.bunkr', 'cdn9.bunkr']
            logger.warning(f"Video domains file not found, using defaults: {domains}")
    except Exception as e:
        logger.error(f"Error loading video domains: {e}")
        # Fallback to default domains
        domains = ['bunkr.', 'gofile.', 'cdn.bunkr', 'cdn9.bunkr']
    
    return domains


def load_content_domains(file_path: str = 'content_domains.txt') -> List[str]:
    """Load content hosting domains from configuration file."""
    domains = []
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        domains.append(line.lower())
            logger.info(f"Loaded {len(domains)} content domains from {file_path}")
        else:
            # Fallback to default domains if file doesn't exist
            domains = ['imgur.', 'jpg6.su', 'simp', 'delivery']
            logger.warning(f"Content domains file not found, using defaults: {domains}")
    except Exception as e:
        logger.error(f"Error loading content domains: {e}")
        # Fallback to default domains
        domains = ['imgur.', 'jpg6.su', 'simp', 'delivery']
    
    return domains


# Load domains once at module level
VIDEO_DOMAINS = load_video_domains()
CONTENT_DOMAINS = load_content_domains()
ALL_DOMAINS = VIDEO_DOMAINS + CONTENT_DOMAINS


def extract_max_pages(html: str) -> int:
    """Extract the maximum number of pages from pagination"""
    # Check cache first
    cached = _get_cached_parse(html, 'max_pages')
    if cached is not None:
        return cached
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        page_nav = soup.find('nav', class_='pageNavWrapper')
        if not page_nav:
            result = 1
            _cache_parse_result(html, 'max_pages', result)
            return result
        
        page_links = page_nav.find_all('li', class_='pageNav-page')
        if not page_links:
            result = 1
            _cache_parse_result(html, 'max_pages', result)
            return result
        
        max_page = 1
        for link_li in page_links:
            link = link_li.find('a')
            if link:
                text = link.get_text(strip=True)
                if text.isdigit():
                    page_num = int(text)
                    max_page = max(max_page, page_num)
        
        _cache_parse_result(html, 'max_pages', max_page)
        return max_page
        
    except Exception as e:
        logger.error(f"Error extracting max pages: {e}")
        return 1


def extract_social_links(html: str) -> Dict[str, str]:
    """Extract OnlyFans and Instagram links from the first post"""
    # Check cache first
    cached = _get_cached_parse(html, 'social_links')
    if cached is not None:
        return cached
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        social_links = {
            'onlyfans': None,
            'instagram': None
        }
        
        first_message = soup.find('article', class_='message')
        if not first_message:
            _cache_parse_result(html, 'social_links', social_links)
            return social_links
        
        message_body = first_message.find('div', class_='bbWrapper')
        if not message_body:
            _cache_parse_result(html, 'social_links', social_links)
            return social_links
        
        links = message_body.find_all('a', href=True)
        
        for link in links:
            href = link['href'].lower()
            
            if 'onlyfans.com' in href and not social_links['onlyfans']:
                social_links['onlyfans'] = link['href']
            
            elif 'instagram.com' in href and not social_links['instagram']:
                social_links['instagram'] = link['href']
            
            if social_links['onlyfans'] and social_links['instagram']:
                break
        
        _cache_parse_result(html, 'social_links', social_links)
        return social_links
        
    except Exception as e:
        logger.error(f"Error extracting social links: {e}")
        return {'onlyfans': None, 'instagram': None}


def extract_preview_images(html: str) -> List[Dict[str, str]]:
    """Extract all preview images from posts (jpg, png, gif, webp)"""
    # Check cache first
    cached = _get_cached_parse(html, 'preview_images')
    if cached is not None:
        return cached
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        preview_images = []
        seen_urls = set()
        
        message_blocks = soup.find_all('article', class_='message')
        
        for block in message_blocks:
            message_body = block.find('div', class_='bbWrapper')
            if not message_body:
                continue
            
            images = message_body.find_all('img', src=True)
            
            for img in images:
                src = img.get('src', '')
                data_url = img.get('data-url', '')
                
                img_url = data_url if data_url else src
                
                if any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    if img_url in seen_urls:
                        continue
                    seen_urls.add(img_url)
                    
                    # Apply robust filtering to exclude non-content images
                    if not is_valid_content_image(img_url):
                        continue
                    
                    description = img.get('alt', '') or img.get('title', '')
                    
                    preview_images.append({
                        'url': img_url,
                        'link_text': description or 'Preview Image',
                        'description': description if description else None,
                        'context': '',
                        'type': '📷 Photo',
                        'domain': extract_domain(img_url)
                    })
        
        _cache_parse_result(html, 'preview_images', preview_images)
        return preview_images
        
    except Exception as e:
        logger.error(f"Error extracting preview images: {e}")
        return []


def extract_content_links(html: str) -> List[Dict[str, str]]:
    """Extract bunkr, gofile, and other content links from HTML"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        content_items = []
        
        message_blocks = soup.find_all('article', class_='message')
        
        for block in message_blocks:
            message_body = block.find('div', class_='bbWrapper')
            if not message_body:
                continue
            
            message_text = message_body.get_text(strip=True)[:200]
            links = message_body.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                link_text = link.get_text(strip=True)
                
                # Check against all loaded domains (video + content)
                if any(domain in href.lower() for domain in ALL_DOMAINS):
                    content_type = determine_content_type(href, link_text)
                    description = extract_link_description(link)
                    
                    # For video links, try to extract title from text above the link
                    title = None
                    if content_type == '🎬 Video':
                        title = extract_video_title(link, message_body)
                    
                    parent = link.find_parent(['p', 'div'])
                    context = parent.get_text(strip=True)[:150] if parent else message_text[:150]
                    
                    content_items.append({
                        'url': href,
                        'link_text': link_text,
                        'description': description,
                        'title': title,  # Add title field
                        'context': context,
                        'type': content_type,
                        'domain': extract_domain(href)
                    })
        
        return content_items
        
    except Exception as e:
        logger.error(f"Error extracting content links: {e}")
        return []


@functools.lru_cache(maxsize=256)
def determine_content_type(url: str, text: str) -> str:
    """Determine the type of content from URL and link text - CACHED"""
    url_lower = url.lower()
    text_lower = text.lower()
    
    if 'album' in url_lower or 'gallery' in url_lower or 'album' in text_lower:
        return '📁 Album'
    
    # Check for video file extensions
    if any(ext in url_lower for ext in ['.mov', '.mp4', '.avi', '.mkv', '.webm', '.flv', '.wmv']):
        return '🎬 Video'
    
    # Check for video hosting domains (even without extensions)
    if any(domain in url_lower for domain in VIDEO_DOMAINS):
        # If it's from a video hosting domain and contains typical video filename patterns
        if any(pattern in url_lower for pattern in ['img_', 'vid_', 'video', 'mov', 'mp4']):
            return '🎬 Video'
    
    # Check text for video indicators
    if 'video' in text_lower or 'vid' in text_lower:
        return '🎬 Video'
    
    # Check for image extensions
    if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        return '📷 Photo'
    
    if 'pic' in text_lower or 'photo' in text_lower or 'img' in text_lower:
        return '📷 Photo'
    
    if 'bunkr.cr/a/' in url_lower:
        return '📦 Collection'
    
    return '📄 Content'


def extract_video_title(link_element, message_body) -> Optional[str]:
    """Extract intelligent title for video links by finding descriptive text before the link."""
    try:
        # Find the parent div containing the link
        link_parent = link_element.find_parent('div')
        if not link_parent:
            return None
        
        # Get all previous siblings and their text
        title_candidates = []
        
        # Look for text before the link within the bbWrapper
        for element in message_body.children:
            # Stop when we reach the link's parent or if element contains the link
            if element == link_parent:
                break
            
            # Check if this element or its descendants contain our link
            if hasattr(element, 'find_all'):
                links_in_element = element.find_all('a')
                if link_element in links_in_element:
                    break
            
            if hasattr(element, 'get_text'):
                text = element.get_text(strip=True)
                if text and len(text) > 0:
                    title_candidates.append(text)
            elif isinstance(element, str):
                text = str(element).strip()
                if text and text not in ['\n', '', ' ']:
                    title_candidates.append(text)
        
        # Process candidates to find the best title
        if title_candidates:
            # Get the last non-empty text before the link
            for candidate in reversed(title_candidates):
                # Clean up the candidate
                candidate = candidate.strip()
                
                # Skip if it's just whitespace or too short
                if len(candidate) < 3:
                    continue
                
                # Skip if it's just a URL
                if candidate.startswith('http') or 'www.' in candidate:
                    continue
                
                # Good title criteria: 
                # - Between 5 and 150 characters
                # - Contains spaces (not just a single word)
                # - Contains descriptive words like "video", "new", "min", etc.
                word_count = len(candidate.split())
                
                if 5 <= len(candidate) <= 150 and word_count >= 2:
                    # Truncate if too long
                    if len(candidate) > 100:
                        candidate = candidate[:97] + '...'
                    return candidate
                
                # Even if shorter, accept if it contains video-related keywords
                if word_count >= 2 and any(keyword in candidate.lower() for keyword in ['video', 'vid', 'new', 'min', 'play', 'clip', 'bts', 'behind']):
                    if len(candidate) > 100:
                        candidate = candidate[:97] + '...'
                    return candidate
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting video title: {e}")
        return None


def extract_link_description(link_element) -> Optional[str]:
    """Extract descriptive text near a link."""
    try:
        parent_div = link_element.find_parent(['div', 'p'])
        if not parent_div:
            return None
        
        grandparent = parent_div.find_parent('div', class_='bbWrapper')
        if not grandparent:
            grandparent = parent_div.find_parent('div')
        
        if not grandparent:
            return None
        
        description_candidates = []
        
        for sibling in grandparent.children:
            if sibling == parent_div:
                break
            
            if hasattr(sibling, 'name'):
                if sibling.name == 'br':
                    continue
                text = sibling.get_text(strip=True)
                if text and len(text) > 0:
                    description_candidates.append(text)
            else:
                text = str(sibling).strip()
                if text and text not in ['\n', '', ' ']:
                    description_candidates.append(text)
        
        if not description_candidates:
            return None
        
        description = description_candidates[-1]
        words = description.split()
        word_count = len(words)
        
        if 2 <= word_count <= 20:
            if 'http' in description.lower() or 'www.' in description.lower():
                return None
            
            if description.count('.com') > 1 or description.count('.ru') > 1:
                return None
            
            return description
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting link description: {e}")
        return None


def extract_domain(url: str) -> str:
    """Extract domain name from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return 'unknown'


def extract_video_links(html: str) -> List[Dict[str, str]]:
    """Extract video links (bunkr, gofile) with intelligent titles."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        video_items = []
        seen_urls = set()
        
        message_blocks = soup.find_all('article', class_='message')
        
        for block in message_blocks:
            message_body = block.find('div', class_='bbWrapper')
            if not message_body:
                continue
            
            links = message_body.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                
                # Check if it's a video hosting link using loaded domains
                if any(domain in href.lower() for domain in VIDEO_DOMAINS):
                    # Avoid duplicates
                    if href in seen_urls:
                        continue
                    
                    url_lower = href.lower()
                    
                    # Check if it's likely a video (has video extension or patterns)
                    is_video = False
                    
                    # Check for video extensions
                    if any(ext in url_lower for ext in ['.mov', '.mp4', '.avi', '.mkv', '.webm', '.flv', '.wmv']):
                        is_video = True
                    # Check for video filename patterns
                    elif any(pattern in url_lower for pattern in ['img_', 'vid_', 'video', '/mov/']):
                        is_video = True
                    # If it's from video hosting domains and NOT an image extension, assume video
                    elif not any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        if any(domain in url_lower for domain in VIDEO_DOMAINS):
                            is_video = True
                    
                    if is_video:
                        seen_urls.add(href)
                        
                        # Extract title
                        title = extract_video_title(link, message_body)
                        if not title:
                            title = f"Video {len(video_items) + 1}"
                        
                        video_items.append({
                            'url': href,
                            'title': title,
                            'type': '🎬 Video',
                            'domain': extract_domain(href)
                        })
        
        return video_items
        
    except Exception as e:
        logger.error(f"Error extracting video links: {e}")
        return []


def group_content_by_type(content_items: List[Dict]) -> Dict[str, List[Dict]]:
    """Group content items by type"""
    grouped = {}
    for item in content_items:
        content_type = item['type']
        if content_type not in grouped:
            grouped[content_type] = []
        grouped[content_type].append(item)
    return grouped


# Async wrappers for concurrent parsing operations
async def extract_preview_images_async(html: str) -> List[Dict[str, str]]:
    """Async wrapper for extract_preview_images to run in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, extract_preview_images, html)


async def extract_content_links_async(html: str) -> List[Dict[str, str]]:
    """Async wrapper for extract_content_links to run in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, extract_content_links, html)


async def extract_video_links_async(html: str) -> List[Dict[str, str]]:
    """Async wrapper for extract_video_links to run in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, extract_video_links, html)


async def parse_page_content_concurrent(html: str) -> tuple:
    """Parse all content from a page concurrently using thread pool.
    
    Returns:
        tuple: (content_links, preview_images, video_links)
    """
    # Run all parsing operations concurrently
    results = await asyncio.gather(
        extract_content_links_async(html),
        extract_preview_images_async(html),
        extract_video_links_async(html)
    )
    return results[0], results[1], results[2]
