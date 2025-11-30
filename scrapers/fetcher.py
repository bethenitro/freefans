"""
HTTP Fetcher - Handle HTTP requests with proper headers and cookies
"""

import httpx
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

# HTTP response cache to avoid refetching same pages
_http_response_cache = {}
_http_cache_ttl = timedelta(minutes=10)  # Cache HTTP responses for 10 minutes
_http_cache_max_size = 100


def _get_http_cache_key(url: str) -> str:
    """Generate cache key for HTTP response."""
    return url


def _clean_http_cache():
    """Remove expired entries from HTTP cache."""
    global _http_response_cache
    now = datetime.now()
    expired_keys = [
        key for key, value in _http_response_cache.items()
        if now - value['timestamp'] > _http_cache_ttl
    ]
    for key in expired_keys:
        del _http_response_cache[key]
        logger.debug(f"Removed expired HTTP cache entry: {key}")
    
    # If cache is too large, remove oldest entries
    if len(_http_response_cache) > _http_cache_max_size:
        sorted_items = sorted(_http_response_cache.items(), key=lambda x: x[1]['timestamp'])
        for key, _ in sorted_items[:len(_http_response_cache) - _http_cache_max_size]:
            del _http_response_cache[key]
            logger.debug(f"Removed old HTTP cache entry: {key}")


def _get_cached_response(url: str) -> Optional[str]:
    """Get cached HTTP response if available."""
    _clean_http_cache()
    cache_key = _get_http_cache_key(url)
    
    if cache_key in _http_response_cache:
        logger.info(f"✓ HTTP cache hit for {url}")
        return _http_response_cache[cache_key]['data']
    return None


def _cache_response(url: str, data: str):
    """Cache HTTP response."""
    cache_key = _get_http_cache_key(url)
    _http_response_cache[cache_key] = {
        'data': data,
        'timestamp': datetime.now()
    }
    logger.debug(f"✓ Cached HTTP response for {url} (cache size: {len(_http_response_cache)})")


class HTTPFetcher:
    def __init__(self, curl_config_path: str = 'curl_config.txt'):
        """Initialize HTTP fetcher with headers and cookies from curl config."""
        headers, cookies = self._load_curl_config(curl_config_path)
        self.headers = headers
        self.cookies = cookies
        
        # Create a shared async client with connection pooling for better performance
        # Connection limits optimized for concurrent requests
        # Increased from 10/20 to 20/50 for better throughput
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50,
            keepalive_expiry=30.0
        )
        
        self._client = None
        self._limits = limits
    
    def _load_curl_config(self, config_path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Parse curl_config.txt and extract headers and cookies."""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"curl_config.txt not found, using default headers")
                return self._get_default_headers()
            
            curl_command = config_file.read_text()
            
            headers = {}
            cookies = {}
            
            header_pattern = r"-H\s+'([^:]+):\s*([^']+)'"
            header_matches = re.findall(header_pattern, curl_command)
            
            for header_name, header_value in header_matches:
                header_name = header_name.strip()
                header_value = header_value.strip()
                
                if header_name.lower() == 'cookie':
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
        }
        return headers, cookies
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page from a URL with headers and cookies using connection pooling."""
        try:
            # Check cache first
            cached_response = _get_cached_response(url)
            if cached_response is not None:
                return cached_response
            
            # Create client lazily if it doesn't exist
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=30.0,
                    follow_redirects=True,
                    limits=self._limits,
                    headers=self.headers,
                    cookies=self.cookies
                )
            
            response = await self._client.get(url)
            response.raise_for_status()
            
            # Cache the response
            response_text = response.text
            _cache_response(url, response_text)
            
            return response_text
        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}")
            return None
    
    async def close(self):
        """Close the HTTP client connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
