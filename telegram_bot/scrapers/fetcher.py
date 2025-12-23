"""
HTTP Fetcher - Handle HTTP requests with proper headers and cookies
Enhanced with multithreading, rotating headers, advanced rate limiting, and anti-bot detection
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
import hashlib

logger = logging.getLogger(__name__)

# HTTP response cache to avoid refetching same pages
_http_response_cache = {}
_http_cache_ttl = timedelta(minutes=10)  # Cache HTTP responses for 10 minutes
_http_cache_max_size = 100

# Thread-safe lock for cache operations
_cache_lock = threading.Lock()

# Anti-bot detection: Track request patterns
_request_history = {}  # domain -> list of timestamps
_suspicious_activity_cooldown = {}  # domain -> cooldown_until_timestamp
_failed_request_backoff = {}  # domain -> backoff_seconds

# Pool of different user agents to rotate (more variety)
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
    def __init__(self, curl_config_path: str = None):
        """Initialize HTTP fetcher with enhanced multithreading and rate limiting."""
        if curl_config_path is None:
            base_dir = Path(__file__).parent.parent.parent
            curl_config_path = str(base_dir / 'shared' / 'config' / 'curl_config.txt')
        
        logger.info(f"🔧 Initializing HTTPFetcher")
        logger.debug(f"   Config path: {curl_config_path}")
        
        headers, cookies = self._load_curl_config(curl_config_path)
        self.base_headers = headers
        self.cookies = cookies
        
        logger.info(f"✅ HTTPFetcher initialized with {len(headers)} headers and {len(cookies)} cookies")
        
        # Enhanced rate limiting settings (increased to reduce 403 errors)
        self._min_delay = 1.5  # Minimum 1.5s delay between requests
        self._max_delay = 3.0   # Maximum 3s delay
        self._last_request_times = {}  # Track per-domain timing
        self._domain_locks = {}  # Per-domain locks (per event loop)
        
        # Request failure tracking for adaptive delays
        self._failure_counts = {}
        self._success_counts = {}
        
        # Connection pool settings optimized for multithreading
        limits = httpx.Limits(
            max_keepalive_connections=15,
            max_connections=30,
            keepalive_expiry=60.0
        )
        
        # Store clients per event loop to avoid cross-loop issues
        self._clients = {}  # {loop_id: {domain: client}}
        self._limits = limits
        self._client_locks = {}  # Per-loop locks
        
        # Thread pool for CPU-intensive operations
        self._thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fetcher")
    
    def _cleanup_old_tracking_data(self):
        """Clean up old tracking data to prevent memory growth."""
        global _request_history, _suspicious_activity_cooldown, _failed_request_backoff
        
        now = time.time()
        cleaned_items = []
        
        # Clean request history older than 5 minutes
        for domain in list(_request_history.keys()):
            old_count = len(_request_history[domain])
            _request_history[domain] = [t for t in _request_history[domain] if now - t < 300]
            if not _request_history[domain]:
                del _request_history[domain]
                cleaned_items.append(f"{domain} (history)")
            elif old_count > len(_request_history[domain]):
                cleaned = old_count - len(_request_history[domain])
                logger.debug(f"🧹 Cleaned {cleaned} old records for {domain}")
        
        # Clean expired cooldowns
        for domain in list(_suspicious_activity_cooldown.keys()):
            if now > _suspicious_activity_cooldown[domain]:
                del _suspicious_activity_cooldown[domain]
                cleaned_items.append(f"{domain} (expired cooldown)")
        
        # Clean backoff for domains with no recent history
        for domain in list(_failed_request_backoff.keys()):
            if domain not in _request_history or not _request_history[domain]:
                del _failed_request_backoff[domain]
                cleaned_items.append(f"{domain} (stale backoff)")
        
        if cleaned_items:
            logger.info(f"🧹 Cleanup: Removed tracking data for {len(cleaned_items)} domains: {', '.join(cleaned_items[:3])}{' and more...' if len(cleaned_items) > 3 else ''}")
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for per-domain rate limiting."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return 'default'
    
    def _get_loop_id(self) -> int:
        """Get unique ID for current event loop."""
        try:
            loop = asyncio.get_running_loop()
            return id(loop)
        except RuntimeError:
            return 0  # No loop
    
    async def _get_client_for_domain(self, domain: str) -> httpx.AsyncClient:
        """Get or create a client for specific domain with rotating headers (event loop aware)."""
        # Get current event loop
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop.is_closed():
                logger.warning(f"Current event loop is closed, cannot create client for {domain}")
                raise RuntimeError("Event loop is closed")
            loop_id = id(current_loop)
        except RuntimeError as e:
            logger.warning(f"No valid event loop available for {domain}: {e}")
            raise
        
        # Get or create lock for this event loop
        if loop_id not in self._client_locks:
            self._client_locks[loop_id] = asyncio.Lock()
        
        async with self._client_locks[loop_id]:
            # Initialize clients dict for this loop if needed
            if loop_id not in self._clients:
                self._clients[loop_id] = {}
            
            # Check if existing client is still valid
            if domain in self._clients[loop_id]:
                client = self._clients[loop_id][domain]
                # Test if client is still usable
                try:
                    if client.is_closed:
                        logger.debug(f"Client for {domain} in loop {loop_id} is closed, creating new one")
                        del self._clients[loop_id][domain]
                    else:
                        return client
                except Exception as e:
                    logger.debug(f"Client for {domain} in loop {loop_id} is invalid: {e}, creating new one")
                    try:
                        await client.aclose()
                    except:
                        pass
                    if domain in self._clients[loop_id]:
                        del self._clients[loop_id][domain]
            
            # Create new client with randomized headers
            headers = _get_random_headers()
            headers.update(self.base_headers)  # Override with config headers if available
            
            # Log header details for debugging
            logger.info(f"🔧 Creating new HTTP client for {domain}")
            logger.debug(f"   User-Agent: {headers.get('User-Agent', 'N/A')[:80]}")
            logger.debug(f"   Accept: {headers.get('Accept', 'N/A')[:60]}")
            logger.debug(f"   Accept-Language: {headers.get('Accept-Language', 'N/A')}")
            logger.debug(f"   Total headers: {len(headers)}")
            logger.debug(f"   Total cookies: {len(self.cookies)}")
            if self.cookies:
                cookie_names = list(self.cookies.keys())[:5]
                logger.debug(f"   Cookie names (first 5): {', '.join(cookie_names)}")
            
            self._clients[loop_id][domain] = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                limits=self._limits,
                headers=headers,
                cookies=self.cookies
            )
            logger.debug(f"✓ HTTP client created for {domain} in loop {loop_id}")
            
            return self._clients[loop_id][domain]
    
    def _detect_suspicious_pattern(self, domain: str) -> bool:
        """
        Detect suspicious request patterns that might trigger anti-bot systems.
        Returns True if pattern is suspicious and should trigger additional delays.
        """
        global _request_history
        
        now = time.time()
        
        # Initialize history for domain
        if domain not in _request_history:
            _request_history[domain] = []
        
        # Clean old history (keep last 60 seconds)
        old_count = len(_request_history[domain])
        _request_history[domain] = [t for t in _request_history[domain] if now - t < 60]
        cleaned_count = old_count - len(_request_history[domain])
        if cleaned_count > 0:
            logger.debug(f"🧹 Cleaned {cleaned_count} old request records for {domain}")
        
        # Check request frequency
        current_count = len(_request_history[domain])
        if current_count > 10:  # More than 10 requests in 60 seconds
            logger.warning(f"⚠️ High request frequency detected for {domain}: {current_count} requests in 60s")
            return True
        elif current_count > 5:
            logger.info(f"📊 Request frequency for {domain}: {current_count} requests in last 60s")
        
        # Check for burst patterns (3+ requests within 5 seconds)
        recent_requests = [t for t in _request_history[domain] if now - t < 5]
        if len(recent_requests) >= 3:
            logger.warning(f"⚠️ Burst pattern detected for {domain}: {len(recent_requests)} requests in 5s")
            return True
        
        logger.debug(f"✓ Pattern check passed for {domain}: {current_count} requests/60s, {len(recent_requests)} requests/5s")
        return False
    
    async def _apply_backoff_if_needed(self, domain: str):
        """Apply exponential backoff if domain is experiencing failures."""
        global _failed_request_backoff, _suspicious_activity_cooldown
        
        now = time.time()
        
        # Check if domain is in cooldown period
        if domain in _suspicious_activity_cooldown:
            cooldown_until = _suspicious_activity_cooldown[domain]
            if now < cooldown_until:
                wait_time = cooldown_until - now
                logger.warning(f"🛑 Domain {domain} in cooldown, waiting {wait_time:.1f}s (cooldown until {datetime.fromtimestamp(cooldown_until).strftime('%H:%M:%S')})")
                await asyncio.sleep(wait_time)
                logger.info(f"✓ Cooldown expired for {domain}, resuming requests")
                return
            else:
                # Cooldown expired, remove it
                del _suspicious_activity_cooldown[domain]
                logger.info(f"✓ Cooldown period ended for {domain}")
        
        # Check if domain has backoff
        if domain in _failed_request_backoff:
            backoff_time = _failed_request_backoff[domain]
            logger.info(f"⏳ Applying exponential backoff of {backoff_time:.1f}s for {domain} (previous failures)")
            await asyncio.sleep(backoff_time)
    
    def _update_request_metrics(self, domain: str, success: bool, status_code: Optional[int] = None):
        """Update request metrics and adjust backoff strategies."""
        global _request_history, _failed_request_backoff, _suspicious_activity_cooldown
        
        now = time.time()
        
        # Record request timestamp
        if domain not in _request_history:
            _request_history[domain] = []
        _request_history[domain].append(now)
        
        # Get current stats
        total_success = self._success_counts.get(domain, 0)
        total_failure = self._failure_counts.get(domain, 0)
        current_backoff = _failed_request_backoff.get(domain, 0)
        
        # Update success/failure counts
        if success:
            self._success_counts[domain] = total_success + 1
            logger.info(f"✅ Request succeeded for {domain} (successes: {total_success + 1}, failures: {total_failure})")
            
            # Gradually reduce backoff on success
            if domain in _failed_request_backoff:
                old_backoff = _failed_request_backoff[domain]
                _failed_request_backoff[domain] = max(0, old_backoff * 0.7)
                new_backoff = _failed_request_backoff[domain]
                
                if new_backoff < 0.5:
                    del _failed_request_backoff[domain]
                    logger.info(f"✓ Backoff cleared for {domain} (was {old_backoff:.1f}s)")
                else:
                    logger.info(f"↓ Backoff reduced for {domain}: {old_backoff:.1f}s → {new_backoff:.1f}s")
        else:
            self._failure_counts[domain] = total_failure + 1
            logger.warning(f"❌ Request failed for {domain} (successes: {total_success}, failures: {total_failure + 1}, status: {status_code or 'unknown'})")
            
            if status_code == 403:
                # 403 = likely anti-bot detection, apply aggressive backoff
                new_backoff = min(30, max(5, current_backoff * 2 + 5))
                _failed_request_backoff[domain] = new_backoff
                # Set cooldown period
                cooldown_until = now + new_backoff
                _suspicious_activity_cooldown[domain] = cooldown_until
                logger.error(f"🚫 403 FORBIDDEN detected for {domain}")
                logger.error(f"   ↑ Applying aggressive backoff: {current_backoff:.1f}s → {new_backoff:.1f}s")
                logger.error(f"   ⏰ Cooldown until: {datetime.fromtimestamp(cooldown_until).strftime('%H:%M:%S')}")
                
            elif status_code == 429:
                # 429 = rate limited, apply moderate backoff
                new_backoff = min(60, max(10, current_backoff * 2 + 10))
                _failed_request_backoff[domain] = new_backoff
                cooldown_until = now + new_backoff
                _suspicious_activity_cooldown[domain] = cooldown_until
                logger.error(f"⏱️ 429 RATE LIMITED for {domain}")
                logger.error(f"   ↑ Applying moderate backoff: {current_backoff:.1f}s → {new_backoff:.1f}s")
                logger.error(f"   ⏰ Cooldown until: {datetime.fromtimestamp(cooldown_until).strftime('%H:%M:%S')}")
                
            else:
                # Other failures, gentle backoff increase
                new_backoff = min(10, current_backoff + 1)
                _failed_request_backoff[domain] = new_backoff
                logger.warning(f"   ↑ Gentle backoff increase: {current_backoff:.1f}s → {new_backoff:.1f}s")
    
    async def _adaptive_rate_limit(self, domain: str):
        """Apply adaptive rate limiting based on success/failure rates."""
        loop_id = self._get_loop_id()
        
        # Get or create domain lock for this event loop
        lock_key = (loop_id, domain)
        if lock_key not in self._domain_locks:
            self._domain_locks[lock_key] = asyncio.Lock()
        
        async with self._domain_locks[lock_key]:
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
                    logger.debug(f"⚠️ High failure rate for {domain}: {failure_rate:.1%} → using max delay {delay:.1f}s")
                elif failure_rate > 0.1:  # More than 10% failures
                    delay = (self._min_delay + self._max_delay) / 2
                    logger.debug(f"⚠️ Moderate failure rate for {domain}: {failure_rate:.1%} → using medium delay {delay:.1f}s")
                else:
                    delay = self._min_delay
                    logger.debug(f"✓ Low failure rate for {domain}: {failure_rate:.1%} → using min delay {delay:.1f}s")
            else:
                delay = self._min_delay
                logger.debug(f"🆕 First request to {domain} → using min delay {delay:.1f}s")
            
            # Add random jitter to make requests appear more human-like (increased)
            jitter = random.uniform(0.5, 1.5)  # 0.5-1.5 second random jitter
            total_delay = delay + jitter
            
            time_since_last = current_time - last_request
            if time_since_last < total_delay:
                sleep_time = total_delay - time_since_last
                logger.info(f"⏱️ Rate limiting {domain}: sleeping {sleep_time:.2f}s (base: {delay:.1f}s + jitter: {jitter:.2f}s)")
                await asyncio.sleep(sleep_time)
            else:
                logger.debug(f"✓ Rate limit satisfied for {domain}: {time_since_last:.2f}s since last request")
            
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
                logger.warning(f"⚠️ curl_config.txt not found at {config_path}, using default headers")
                logger.warning(f"   Expected path: {config_file.absolute()}")
                return self._get_default_headers()
            
            curl_command = config_file.read_text()
            logger.debug(f"📄 Loaded curl_config.txt ({len(curl_command)} bytes)")
            
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
                logger.warning("⚠️ No headers found in curl_config.txt, using defaults")
                return self._get_default_headers()
            
            logger.info(f"✅ Loaded {len(headers)} headers and {len(cookies)} cookies from {config_path}")
            logger.debug(f"   Headers: {', '.join(list(headers.keys())[:8])}")
            if cookies:
                cookie_names = list(cookies.keys())[:5]
                logger.debug(f"   Cookies (first 5): {', '.join(cookie_names)}")
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
            # Periodically cleanup old tracking data
            if random.random() < 0.1:  # 10% chance to cleanup on each request
                self._cleanup_old_tracking_data()
            
            # Check cache first
            cached_response = _get_cached_response(url)
            if cached_response is not None:
                logger.debug(f"💾 Cache hit for {url[:80]}...")
                return cached_response
            
            logger.info(f"🌐 Fetching {domain}: {url[:100]}...")
            
            # Apply backoff if domain has failures
            await self._apply_backoff_if_needed(domain)
            
            # Detect suspicious request patterns
            if self._detect_suspicious_pattern(domain):
                additional_delay = random.uniform(2.0, 5.0)
                logger.warning(f"⚠️ Suspicious pattern detected for {domain}, adding {additional_delay:.1f}s delay")
                await asyncio.sleep(additional_delay)
            
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
                        logger.info(f"🔄 Retry {attempt}/{retry_count} for {domain} after {retry_delay:.1f}s delay")
                        await asyncio.sleep(retry_delay)
                        
                        # Refresh headers for retry to avoid detection
                        new_headers = _get_random_headers()
                        new_headers.update(self.base_headers)
                        client.headers.update(new_headers)
                        logger.debug(f"🔄 Refreshed headers for retry (User-Agent: {new_headers.get('User-Agent', 'N/A')[:50]}...)")
                    
                    # Check if we're in a valid event loop
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_closed():
                            logger.warning(f"Event loop is closed for {url}, skipping request")
                            self._update_request_metrics(domain, False)
                            return None
                    except RuntimeError:
                        logger.warning(f"No event loop available for {url}, skipping request")
                        self._update_request_metrics(domain, False)
                        return None
                    
                    logger.debug(f"📤 Sending request to {domain}...")
                    response = await client.get(url)
                    
                    # Log response details before raising status
                    logger.debug(f"📥 Received response: status={response.status_code}, size={len(response.text)} bytes")
                    
                    response.raise_for_status()
                    
                    # Success - record and cache
                    response_text = response.text
                    response_size = len(response_text)
                    self._update_request_metrics(domain, True, response.status_code)
                    _cache_response(url, response_text)
                    
                    logger.info(f"✅ Successfully fetched {domain} ({response_size:,} bytes, status: {response.status_code}, attempt: {attempt + 1})")
                    return response_text
                    
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    response_headers = dict(e.response.headers)
                    response_text_preview = e.response.text if hasattr(e.response, 'text') else "N/A"
                    
                    # Log detailed error information
                    logger.error(f"❌ HTTP {status_code} error for {url}")
                    logger.error(f"   Response headers: {', '.join([f'{k}: {v}' for k, v in list(response_headers.items())[:8]])}")
                    
                    # For 403 errors, show FULL response to understand the challenge
                    if status_code == 403 and response_text_preview != "N/A":
                        logger.error(f"   ========== FULL 403 RESPONSE (first 2000 chars) ==========")
                        logger.error(f"{response_text_preview[:2000]}")
                        logger.error(f"   ========== END 403 RESPONSE ==========")
                    elif response_text_preview != "N/A":
                        logger.error(f"   Response preview (first 200 chars): {response_text_preview[:200]}")
                    
                    # Log current request headers being used (directly from client)
                    try:
                        actual_ua = None
                        actual_accept = None
                        for k, v in client.headers.items():
                            if k.lower() == 'user-agent':
                                actual_ua = v
                            if k.lower() == 'accept':
                                actual_accept = v
                        
                        logger.error(f"   Actual User-Agent sent: {actual_ua if actual_ua else 'MISSING!'}")
                        logger.error(f"   Actual Accept sent: {actual_accept[:60] if actual_accept else 'MISSING!'}")
                        logger.error(f"   Total request headers: {len(client.headers)}")
                        logger.error(f"   Request cookies: {len(client.cookies)}")
                        if client.cookies:
                            cookie_names = [k for k in client.cookies.keys()][:10]
                            logger.error(f"   Cookie names: {', '.join(cookie_names)}")
                    except Exception as log_err:
                        logger.error(f"   Error reading headers: {log_err}")
                    
                    if status_code == 429:
                        # Rate limited - update metrics and apply backoff
                        self._update_request_metrics(domain, False, status_code)
                        backoff_delay = min(30.0, (2 ** attempt) * 5)
                        logger.warning(f"Rate limited (429) for {url}, waiting {backoff_delay}s (attempt {attempt + 1})")
                        await asyncio.sleep(backoff_delay)
                        continue
                    elif status_code in [403, 404]:
                        # Don't retry on client errors - update metrics with status code
                        self._update_request_metrics(domain, False, status_code)
                        return None
                    else:
                        logger.warning(f"HTTP error {status_code} for {url} (attempt {attempt + 1})")
                        if attempt == retry_count:
                            self._update_request_metrics(domain, False, status_code)
                            return None
                        continue
                        
                except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    logger.warning(f"Timeout for {url} (attempt {attempt + 1}): {e}")
                    if attempt == retry_count:
                        self._update_request_metrics(domain, False)
                        return None
                    continue
                    
                except Exception as e:
                    error_msg = str(e)
                    if any(keyword in error_msg.lower() for keyword in [
                        "event loop is closed", 
                        "different event loop", 
                        "cannot send a request", 
                        "client has been closed",
                        "connection pool is closed"
                    ]):
                        logger.warning(f"Event loop error for {url} (attempt {attempt + 1}): {e}")
                        # Force recreate the client for this domain
                        if attempt < retry_count:
                            loop_id = self._get_loop_id()
                            if loop_id in self._client_locks:
                                async with self._client_locks[loop_id]:
                                    if loop_id in self._clients and domain in self._clients[loop_id]:
                                        try:
                                            await self._clients[loop_id][domain].aclose()
                                        except:
                                            pass
                                        del self._clients[loop_id][domain]
                            # Small delay before retry
                            await asyncio.sleep(1.0)
                            # Try to get a fresh client for next attempt
                            try:
                                client = await self._get_client_for_domain(domain)
                            except Exception as client_err:
                                logger.warning(f"Failed to recreate client for {domain}: {client_err}")
                                self._update_request_metrics(domain, False)
                                return None
                            continue
                        else:
                            self._update_request_metrics(domain, False)
                            return None
                    else:
                        logger.warning(f"Request error for {url} (attempt {attempt + 1}): {e}")
                        if attempt == retry_count:
                            self._update_request_metrics(domain, False)
                            return None
                        continue
            
            # All retries failed
            self._update_request_metrics(domain, False)
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            self._update_request_metrics(domain, False)
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
        
        # Count total clients across all event loops
        total_clients = sum(len(clients) for clients in self._clients.values())
        
        return {
            'total_requests': total_requests,
            'successful_requests': total_success,
            'failed_requests': total_failure,
            'success_rate': total_success / total_requests if total_requests > 0 else 0,
            'domains_tracked': len(self._success_counts),
            'active_clients': total_clients,
            'event_loops': len(self._clients),
            'cache_size': len(_http_response_cache)
        }
    
    async def close(self):
        """Close all HTTP clients and thread pool."""
        # Close clients for all event loops
        for loop_id in list(self._clients.keys()):
            if loop_id in self._client_locks:
                async with self._client_locks[loop_id]:
                    for domain, client in list(self._clients[loop_id].items()):
                        try:
                            await client.aclose()
                            logger.debug(f"Closed HTTP client for domain: {domain} in loop {loop_id}")
                        except Exception as e:
                            logger.warning(f"Error closing client for {domain} in loop {loop_id}: {e}")
                    self._clients[loop_id].clear()
            else:
                # No lock available, just try to close
                for domain, client in list(self._clients.get(loop_id, {}).items()):
                    try:
                        await client.aclose()
                    except:
                        pass
        
        self._clients.clear()
        self._client_locks.clear()
        
        # Shutdown thread pool
        self._thread_pool.shutdown(wait=True)
        logger.info("HTTP fetcher closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
