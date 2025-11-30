"""
HTML Parsers - Extract data from HTML content
"""

import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_max_pages(html: str) -> int:
    """Extract the maximum number of pages from pagination"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        page_nav = soup.find('nav', class_='pageNavWrapper')
        if not page_nav:
            return 1
        
        page_links = page_nav.find_all('li', class_='pageNav-page')
        if not page_links:
            return 1
        
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


def extract_social_links(html: str) -> Dict[str, str]:
    """Extract OnlyFans and Instagram links from the first post"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        social_links = {
            'onlyfans': None,
            'instagram': None
        }
        
        first_message = soup.find('article', class_='message')
        if not first_message:
            return social_links
        
        message_body = first_message.find('div', class_='bbWrapper')
        if not message_body:
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
        
        return social_links
        
    except Exception as e:
        logger.error(f"Error extracting social links: {e}")
        return {'onlyfans': None, 'instagram': None}


def extract_preview_images(html: str) -> List[Dict[str, str]]:
    """Extract all preview images from posts (jpg, png, gif, webp)"""
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
                    
                    description = img.get('alt', '') or img.get('title', '')
                    
                    if 'avatar' in img_url.lower() or 'icon' in img_url.lower():
                        continue
                    
                    preview_images.append({
                        'url': img_url,
                        'link_text': description or 'Preview Image',
                        'description': description if description else None,
                        'context': '',
                        'type': '📷 Photo',
                        'domain': extract_domain(img_url)
                    })
        
        return preview_images
        
    except Exception as e:
        logger.error(f"Error extracting preview images: {e}")
        return []


def extract_content_links(html: str) -> List[Dict[str, str]]:
    """Extract bunkr, pixl, gofile, and other content links from HTML"""
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
                
                if any(domain in href.lower() for domain in [
                    'bunkr.', 'pixl.', 'gofile.', 'cdn.', 'imgur.', 
                    'jpg6.su', 'simp', 'delivery'
                ]):
                    content_type = determine_content_type(href, link_text)
                    description = extract_link_description(link)
                    
                    parent = link.find_parent(['p', 'div'])
                    context = parent.get_text(strip=True)[:150] if parent else message_text[:150]
                    
                    content_items.append({
                        'url': href,
                        'link_text': link_text,
                        'description': description,
                        'context': context,
                        'type': content_type,
                        'domain': extract_domain(href)
                    })
        
        return content_items
        
    except Exception as e:
        logger.error(f"Error extracting content links: {e}")
        return []


def determine_content_type(url: str, text: str) -> str:
    """Determine the type of content from URL and link text"""
    url_lower = url.lower()
    text_lower = text.lower()
    
    if 'album' in url_lower or 'gallery' in url_lower or 'album' in text_lower:
        return '📁 Album'
    
    if any(ext in url_lower for ext in ['.mov', '.mp4', '.avi', '.mkv']):
        return '🎬 Video'
    
    if 'video' in text_lower or 'vid' in text_lower:
        return '🎬 Video'
    
    if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        return '📷 Photo'
    
    if 'pic' in text_lower or 'photo' in text_lower or 'img' in text_lower:
        return '📷 Photo'
    
    if 'bunkr.cr/a/' in url_lower or 'pixl.li/album/' in url_lower:
        return '📦 Collection'
    
    return '📄 Content'


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


def group_content_by_type(content_items: List[Dict]) -> Dict[str, List[Dict]]:
    """Group content items by type"""
    grouped = {}
    for item in content_items:
        content_type = item['type']
        if content_type not in grouped:
            grouped[content_type] = []
        grouped[content_type].append(item)
    return grouped
