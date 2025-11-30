"""
HTTP Fetcher - Handle HTTP requests with proper headers and cookies
"""

import httpx
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
import re

logger = logging.getLogger(__name__)


class HTTPFetcher:
    def __init__(self, curl_config_path: str = 'curl_config.txt'):
        """Initialize HTTP fetcher with headers and cookies from curl config."""
        headers, cookies = self._load_curl_config(curl_config_path)
        self.headers = headers
        self.cookies = cookies
    
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
        """Fetch a page from a URL with headers and cookies."""
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
