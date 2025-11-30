"""
SimpCity Search - Search for creators on simpcity.cr when not found in CSV
"""

import logging
import re
import csv
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import hashlib
from scrapers.fuzzy_search import FuzzySearchEngine

logger = logging.getLogger(__name__)

# Global fuzzy search engine instance
_fuzzy_engine = FuzzySearchEngine(min_score=60)

# Cache for search results
_search_cache = {}
_search_cache_ttl = timedelta(minutes=30)  # Cache for 30 minutes
_search_cache_max_size = 50


def _get_search_hash(query: str) -> str:
    """Generate hash for search query."""
    return hashlib.md5(query.lower().encode('utf-8')).hexdigest()[:12]


def _clean_search_cache():
    """Remove expired entries from search cache."""
    global _search_cache
    now = datetime.now()
    expired_keys = [
        key for key, value in _search_cache.items()
        if now - value['timestamp'] > _search_cache_ttl
    ]
    for key in expired_keys:
        del _search_cache[key]
    
    # Limit cache size
    if len(_search_cache) > _search_cache_max_size:
        sorted_items = sorted(_search_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_items[:len(_search_cache) - _search_cache_max_size]:
            del _search_cache[key]


def parse_search_results(html: str) -> List[Dict]:
    """
    Parse search results from simpcity.cr search page.
    Filters for OnlyFans forum entries with more than 1 reply.
    Uses caching to avoid re-parsing same HTML.
    
    Returns list of dicts with:
        - title: Creator title/name
        - url: Thread URL
        - replies: Number of replies
        - forum: Forum name
        - author: Thread author
        - date: Creation date
        - snippet: Content snippet
        - thumbnail: Thumbnail URL if available
    """
    # Check cache first
    html_hash = hashlib.md5(html.encode('utf-8')).hexdigest()[:16]
    if html_hash in _search_cache:
        cache_entry = _search_cache[html_hash]
        if datetime.now() - cache_entry['timestamp'] < _search_cache_ttl:
            logger.debug(f"Search results cache hit for hash {html_hash}")
            return cache_entry['data']
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        # Find all contentRow elements
        content_rows = soup.find_all('div', class_='contentRow')
        
        for row in content_rows:
            try:
                # Extract title and URL
                title_elem = row.find('h3', class_='contentRow-title')
                if not title_elem:
                    continue
                    
                link_elem = title_elem.find('a')
                if not link_elem:
                    continue
                
                # Get text but preserve spaces around labels
                title_html = str(link_elem)
                # Remove HTML tags but keep text content
                from bs4 import NavigableString
                title_parts = []
                for content in link_elem.descendants:
                    if isinstance(content, NavigableString):
                        text = str(content).strip()
                        if text:
                            title_parts.append(text)
                title = ' '.join(title_parts)
                
                url = link_elem.get('href', '')
                
                # Make URL absolute if it's relative
                if url.startswith('/'):
                    url = f"https://simpcity.cr{url}"
                
                # Check if it's in OnlyFans forum
                minor_section = row.find('div', class_='contentRow-minor')
                if not minor_section:
                    continue
                
                # Find the forum link
                forum_name = None
                forum_links = minor_section.find_all('a')
                for link in forum_links:
                    if '/forums/' in link.get('href', ''):
                        forum_name = link.get_text(strip=True)
                        break
                
                # Only include OnlyFans forum results
                if forum_name != 'OnlyFans':
                    continue
                
                # Extract replies count from the minor section
                replies_elem = minor_section.find('li', string=re.compile(r'Replies:\s*\d+'))
                if not replies_elem:
                    continue
                    
                replies_text = replies_elem.get_text(strip=True)
                replies_match = re.search(r'Replies:\s*(\d+)', replies_text)
                if not replies_match:
                    continue
                    
                replies = int(replies_match.group(1))
                
                # Only include results with more than 1 reply
                if replies <= 1:
                    continue
                
                # Extract snippet
                snippet_elem = row.find('div', class_='contentRow-snippet')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                
                # Extract author from minor section
                author_elem = minor_section.find('a', class_='username')
                author = author_elem.get_text(strip=True) if author_elem else 'Unknown'
                
                # Extract date from minor section
                date_elem = minor_section.find('time', class_='u-dt')
                date = date_elem.get('data-date', '') if date_elem else ''
                
                # Extract thumbnail if available
                thumbnail_elem = row.find('img')
                thumbnail = None
                if thumbnail_elem:
                    style = thumbnail_elem.get('style', '')
                    thumb_match = re.search(r'background-image:\s*url\((.*?)\)', style)
                    if thumb_match:
                        thumbnail = thumb_match.group(1)
                
                # Check if labels include OnlyFans
                labels = title_elem.find_all('span', class_='label')
                has_onlyfans_label = any('OnlyFans' in label.get_text() for label in labels)
                
                # Add to results
                results.append({
                    'title': title,
                    'url': url,
                    'replies': replies,
                    'forum': forum_name,
                    'author': author,
                    'date': date,
                    'snippet': snippet[:200] if snippet else '',  # Limit snippet length
                    'thumbnail': thumbnail,
                    'has_onlyfans_label': has_onlyfans_label
                })
                
            except Exception as e:
                logger.error(f"Error parsing individual search result: {e}")
                continue
        
        logger.info(f"Parsed {len(results)} valid search results (OnlyFans forum, >1 reply)")
        
        logger.info(f"Parsed {len(results)} search results")
        
        # Cache the results
        _search_cache[html_hash] = {
            'data': results,
            'timestamp': datetime.now()
        }
        _clean_search_cache()
        
        return results
        
    except Exception as e:
        logger.error(f"Error parsing search results: {e}")
        return []
def build_search_url(creator_name: str) -> str:
    """
    Build the search URL for simpcity.cr
    
    Args:
        creator_name: Name to search for
    
    Returns:
        Full search URL
    """
    import random
    
    # Replace spaces with + for URL encoding
    query = creator_name.replace(' ', '+')
    
    # Generate a random search ID to avoid cached results
    search_id = random.randint(10000000, 99999999)
    
    # Build URL with title_only=1 and order by relevance
    url = f"https://simpcity.cr/search/{search_id}/?q={query}&c[title_only]=1&o=relevance"
    
    return url


def add_creator_to_csv(creator_name: str, profile_url: str, csv_path: str = 'onlyfans_models.csv') -> bool:
    """
    Add a new creator to the CSV file.
    
    Args:
        creator_name: Name of the creator
        profile_url: SimpCity thread URL
        csv_path: Path to CSV file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read existing entries to check for duplicates
        existing_urls = set()
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    existing_urls.add(row['profile_link'])
        except FileNotFoundError:
            # File doesn't exist yet, will be created
            pass
        
        # Check if URL already exists
        if profile_url in existing_urls:
            logger.info(f"Creator {creator_name} already exists in CSV")
            return False
        
        # Append new entry
        with open(csv_path, 'a', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['model_name', 'profile_link'])
            
            # Write header if file is empty
            if file.tell() == 0:
                writer.writeheader()
            
            writer.writerow({
                'model_name': creator_name,
                'profile_link': profile_url
            })
        
        logger.info(f"Added {creator_name} to CSV: {profile_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding creator to CSV: {e}")
        return False


def extract_creator_name_from_title(title: str) -> str:
    """
    Extract clean creator name from thread title.
    Removes platform names but keeps the full creator name/aliases.
    
    Args:
        title: Thread title from search results
    
    Returns:
        Cleaned creator name with aliases
    """
    # Remove common platform and category labels
    cleaned = title
    labels_to_remove = [
        'OnlyFans', 'Fansly', 'Instagram', 'Twitter', 'TikTok', 'Snapchat',
        'Request', 'Latina', 'Asian', 'Ebony', 'BBW', 'MILF', 'Teen', 
        'Amateur', 'Professional', 'Leaked', 'Premium', 'VIP', 'Free',
        'Model', 'Creator', 'Influencer', 'Cosplay', 'Gamer', 'Fitness',
        'Petite', 'Curvy', 'Slim', 'Thick', 'Blonde', 'Brunette', 'Redhead',
        'Tattooed', 'Natural', 'Enhanced', 'Solo', 'Couple', 'Group'
    ]
    
    for label in labels_to_remove:
        # Case insensitive removal
        cleaned = re.sub(r'\b' + re.escape(label) + r'\b', '', cleaned, flags=re.IGNORECASE)
    
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' |')
    
    # Remove leading/trailing pipes and spaces
    cleaned = re.sub(r'^[\s|]+|[\s|]+$', '', cleaned)
    
    return cleaned


def rank_search_results_by_query(query: str, results: List[Dict], limit: int = 10) -> List[Dict]:
    """
    Rank and filter search results using fuzzy matching to find the best matches for the query.
    
    Args:
        query: The original search query (creator name)
        results: List of parsed search results
        limit: Maximum number of results to return
    
    Returns:
        Ranked and filtered list of results with fuzzy_score added
    """
    if not results:
        return []
    
    logger.info(f"Ranking {len(results)} search results for query: '{query}'")
    
    # Apply fuzzy search ranking without boost factors
    ranked_results = _fuzzy_engine.rank_search_results(
        query=query,
        search_results=results,
        limit=limit,
        boost_factors={}  # No boost factors - pure fuzzy match scoring
    )
    
    logger.info(f"Fuzzy search returned {len(ranked_results)} ranked results")
    
    return ranked_results


def get_best_match(query: str, results: List[Dict], threshold: float = 70) -> Optional[Dict]:
    """
    Get the single best match from search results using fuzzy matching.
    
    Args:
        query: The original search query (creator name)
        results: List of parsed search results
        threshold: Minimum fuzzy score threshold (0-100)
    
    Returns:
        Best matching result or None if no match above threshold
    """
    if not results:
        return None
    
    match = _fuzzy_engine.get_best_match(
        query=query,
        candidates=results,
        threshold=int(threshold)
    )
    
    if match:
        best_result, score = match
        logger.info(f"Best match: '{best_result.get('title')}' with score {score:.1f}")
        return best_result
    
    logger.info(f"No match found above threshold {threshold}")
    return None
