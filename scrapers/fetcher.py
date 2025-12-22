"""
HTTP Fetcher - Handle HTTP requests with proper headers and cookies
Enhanced with multithreading, rotating headers, and advanced rate limiting
"""

import httpx
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime, timedelta
import re
import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# HTTP response cache to avoid refetching same pages
_http_response_cache = {}
_http_cache_ttl = timedelta(minutes=10)  # Cache HTTP responses for 10 minutes
_http_cache_max_size = 100

# Thread-safe lock for cache operations
_cache_lock = threading.Lock()

# Pool of different user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
]

# Pool of different accept headers
ACCEPT_HEADERS = [
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
]

# Pool of different accept-language headers
ACCEPT_LANGUAGES = [
    'en-US,en;q=0.9',
    'en-US,en;q=0.8',
    'en-GB,en-US;q=0.9,en;q=0.8',
    'en-US,en;q=0.5',
    'en-US,en;q=0.9,es;q=0.8'
]


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
    """Get cached HTTP response if available (thread-safe)."""
    with _cache_lock:
        _clean_http_cache()
        cache_key = _get_http_cache_key(url)
        
        if cache_key in _http_response_cache:
            logger.info(f"✓ HTTP cache hit for {url}")
            return _http_response_cache[cache_key]['data']
        return None


def _cache_response(url: str, data: str):
    """Cache HTTP response (thread-safe)."""
    with _cache_lock:
        cache_key = _get_http_cache_key(url)
        _http_response_cache[cache_key] = {
            'data': data,
            'timestamp': datetime.now()
        }
        logger.debug(f"✓ Cached HTTP response for {url} (cache size: {len(_http_response_cache)})")


def _get_random_headers() -> Dict[str, str]:
    """Generate randomized headers to avoid bot detection."""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': random.choice(ACCEPT_HEADERS),
        'Accept-Language': random.choice(ACCEPT_LANGUAGES),
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': random.choice(['none', 'same-origin', 'cross-site']),
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{random.choice(["Windows", "macOS", "Linux"])}"'
    }


class HTTPFetcher:
    def __init__(self, curl_config_path: str = 'curl_config.txt'):
        """Initialize HTTP fetcher with enhanced multithreading and rate limiting."""
        headers, cookies = self._load_curl_config(curl_config_path)
        self.base_headers = headers
        self.cookies = cookies
        
        # Enhanced rate limiting settings
        self._min_delay = 0.5  # Minimum 500ms delay
        self._max_delay = 2.0   # Maximum 2s delay
        self._last_request_times = {}  # Track per-domain timing
        self._rate_limit_lock = asyncio.Lock()
        self._domain_locks = {}  # Per-domain locks
        
        # Request failure tracking for adaptive delays
        self._failure_counts = {}
        self._success_counts = {}
        
        # Connection pool settings optimized for multithreading
        limits = httpx.Limits(
            max_keepalive_connections=15,
            max_connections=30,
            keepalive_expiry=60.0
        )
        
        self._clients = {}  # Multiple clients for different domains
        self._limits = limits
        self._client_lock = asyncio.Lock()
        
        # Thread pool for CPU-intensive operations
        self._thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fetcher")
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for per-domain rate limiting."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return 'default'
    
    async def _get_client_for_domain(self, domain: str) -> httpx.AsyncClient:
        """Get or create a client for specific domain with rotating headers."""
        async with self._client_lock:
            if domain not in self._clients:
                # Create client with randomized headers
                headers = _get_random_headers()
                headers.update(self.base_headers)  # Override with config headers if available
                
                self._clients[domain] = httpx.AsyncClient(
                    timeout=30.0,
                    follow_redirects=True,
                    limits=self._limits,
                    headers=headers,
                    cookies=self.cookies
                )
                logger.debug(f"Created new HTTP client for domain: {domain}")
            
            return self._clients[domain]
    
    async def _adaptive_rate_limit(self, domain: str):
        """Apply adaptive rate limiting based on success/failure rates."""
        # Get or create domain lock
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        
        async with self._domain_locks[domain]:
            current_time = time.time()
            last_request = self._last_request_times.get(domain, 0)
            
            # Calculate adaptive delay based on failure rate
            failure_count = self._failure_counts.get(domain, 0)
            success_count = self._success_counts.get(domain, 0)
            total_requests = failure_count + success_count
            
            if total_requests > 0:
                failure_rate = failure_count / total_requests
                # Increase delay if failure rate is high
                if failure_rate > 0.3:  # More than 30% failures
                    delay = self._max_delay
                elif failure_rate > 0.1:  # More than 10% failures
                    delay = (self._min_delay + self._max_delay) / 2
                else:
                    delay = self._min_delay
            else:
                delay = self._min_delay
            
            # Add random jitter to avoid synchronized requests
            jitter = random.uniform(0.1, 0.3)
            total_delay = delay + jitter
            
            time_since_last = current_time - last_request
            if time_since_last < total_delay:
                sleep_time = total_delay - time_since_last
                logger.debug(f"Rate limiting {domain}: sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
            
            self._last_request_times[domain] = time.time()
    
    def _record_request_result(self, domain: str, success: bool):
        """Record request success/failure for adaptive rate limiting."""
        if success:
            self._success_counts[domain] = self._success_counts.get(domain, 0) + 1
        else:
            self._failure_counts[domain] = self._failure_counts.get(domain, 0) + 1
        
        # Reset counters periodically to adapt to changing conditions
        total = self._success_counts.get(domain, 0) + self._failure_counts.get(domain, 0)
        if total > 100:  # Reset after 100 requests
            self._success_counts[domain] = max(1, self._success_counts.get(domain, 0) // 2)
            self._failure_counts[domain] = max(1, self._failure_counts.get(domain, 0) // 2)
    
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
    
    async def fetch_page(self, url: str, retry_count: int = 2) -> Optional[str]:
        """Fetch a page with enhanced error handling, retries, and bot detection avoidance."""
        domain = self._get_domain(url)
        
        try:
            # Check cache first
            cached_response = _get_cached_response(url)
            if cached_response is not None:
                return cached_response
            
            # Apply adaptive rate limiting
            await self._adaptive_rate_limit(domain)
            
            # Get client for this domain
            client = await self._get_client_for_domain(domain)
            
            # Attempt request with retries
            for attempt in range(retry_count + 1):
                try:
                    # Add random delay between retries
                    if attempt > 0:
                        retry_delay = random.uniform(1.0, 3.0) * attempt
                        logger.info(f"Retry {attempt}/{retry_count} for {url} after {retry_delay:.1f}s")
                        await asyncio.sleep(retry_delay)
                        
                        # Refresh headers for retry to avoid detection
                        new_headers = _get_random_headers()
                        new_headers.update(self.base_headers)
                        client.headers.update(new_headers)
                    
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    # Success - record and cache
                    self._record_request_result(domain, True)
                    response_text = response.text
                    _cache_response(url, response_text)
                    
                    logger.debug(f"Successfully fetched {url} (attempt {attempt + 1})")
                    return response_text
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Rate limited - exponential backoff
                        backoff_delay = min(30.0, (2 ** attempt) * 5)
                        logger.warning(f"Rate limited (429) for {url}, waiting {backoff_delay}s (attempt {attempt + 1})")
                        await asyncio.sleep(backoff_delay)
                        continue
                    elif e.response.status_code in [403, 404]:
                        # Don't retry on client errors
                        logger.error(f"Client error {e.response.status_code} for {url}")
                        self._record_request_result(domain, False)
                        return None
                    else:
                        logger.warning(f"HTTP error {e.response.status_code} for {url} (attempt {attempt + 1})")
                        if attempt == retry_count:
                            self._record_request_result(domain, False)
                            return None
                        continue
                        
                except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    logger.warning(f"Timeout for {url} (attempt {attempt + 1}): {e}")
                    if attempt == retry_count:
                        self._record_request_result(domain, False)
                        return None
                    continue
                    
                except Exception as e:
                    logger.warning(f"Request error for {url} (attempt {attempt + 1}): {e}")
                    if attempt == retry_count:
                        self._record_request_result(domain, False)
                        return None
                    continue
            
            # All retries failed
            self._record_request_result(domain, False)
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            self._record_request_result(domain, False)
            return None
    
    async def fetch_multiple_pages(self, urls: List[str], max_concurrent: int = 5) -> List[Tuple[str, Optional[str]]]:
        """
        Fetch multiple pages concurrently with controlled concurrency.
        
        Args:
            urls: List of URLs to fetch
            max_concurrent: Maximum number of concurrent requests
            
        Returns:
            List of (url, content) tuples
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_with_semaphore(url: str) -> Tuple[str, Optional[str]]:
            async with semaphore:
                content = await self.fetch_page(url)
                return url, content
        
        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions in results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching {urls[i]}: {result}")
                final_results.append((urls[i], None))
            else:
                final_results.append(result)
        
        return final_results
    
    def get_stats(self) -> Dict[str, any]:
        """Get fetcher statistics."""
        total_success = sum(self._success_counts.values())
        total_failure = sum(self._failure_counts.values())
        total_requests = total_success + total_failure
        
        return {
            'total_requests': total_requests,
            'successful_requests': total_success,
            'failed_requests': total_failure,
            'success_rate': total_success / total_requests if total_requests > 0 else 0,
            'domains_tracked': len(self._success_counts),
            'active_clients': len(self._clients),
            'cache_size': len(_http_response_cache)
        }
    
    async def close(self):
        """Close all HTTP clients and thread pool."""
        async with self._client_lock:
            for domain, client in self._clients.items():
                try:
                    await client.aclose()
                    logger.debug(f"Closed HTTP client for domain: {domain}")
                except Exception as e:
                    logger.warning(f"Error closing client for {domain}: {e}")
            self._clients.clear()
        
        # Shutdown thread pool
        self._thread_pool.shutdown(wait=True)
        logger.info("HTTP fetcher closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
