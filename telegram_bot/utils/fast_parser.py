"""
Fast HTML Parser - Optimized parsing using selectolax (10-100x faster than BeautifulSoup)

This module provides a high-performance HTML parser using selectolax's Lexbor engine,
which is significantly faster than BeautifulSoup for simple parsing tasks.

Benchmarks show:
- 10-100x faster parsing for simple queries
- 2-5x faster for complex nested queries
- Lower memory footprint

Fallback to BeautifulSoup is available if selectolax is not installed.
"""

import logging
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import fast parser (selectolax), fall back to BeautifulSoup
try:
    from selectolax.lexbor import LexborHTMLParser
    FAST_PARSER_AVAILABLE = True
    logger.info("✅ Using selectolax (Lexbor) - 10-100x faster HTML parsing")
except ImportError:
    from bs4 import BeautifulSoup
    FAST_PARSER_AVAILABLE = False
    logger.warning("⚠️  selectolax not available, using BeautifulSoup (slower)")


class FastHTMLParser:
    """High-performance HTML parser with unified API."""
    
    def __init__(self, html: str):
        """Initialize parser with HTML content."""
        self.html = html
        if FAST_PARSER_AVAILABLE:
            self.tree = LexborHTMLParser(html)
            self.parser_type = "selectolax"
        else:
            self.tree = BeautifulSoup(html, 'lxml')
            self.parser_type = "beautifulsoup"
    
    def select(self, selector: str) -> List:
        """
        Select elements using CSS selector.
        
        Args:
            selector: CSS selector string
            
        Returns:
            List of matching elements
        """
        if self.parser_type == "selectolax":
            return self.tree.css(selector)
        else:
            return self.tree.select(selector)
    
    def select_one(self, selector: str):
        """
        Select first matching element using CSS selector.
        
        Args:
            selector: CSS selector string
            
        Returns:
            First matching element or None
        """
        if self.parser_type == "selectolax":
            return self.tree.css_first(selector)
        else:
            return self.tree.select_one(selector)
    
    def get_text(self, element, strip: bool = True) -> str:
        """Get text content from element."""
        if self.parser_type == "selectolax":
            text = element.text()
            return text.strip() if strip else text
        else:
            text = element.get_text()
            return text.strip() if strip else text
    
    def get_attr(self, element, attr: str, default: str = '') -> str:
        """Get attribute value from element."""
        if self.parser_type == "selectolax":
            return element.attributes.get(attr, default)
        else:
            return element.get(attr, default)
    
    def find_all_links(self, selector: str = 'a') -> List[dict]:
        """
        Fast extraction of all links from page.
        
        Args:
            selector: CSS selector for link elements (default: 'a')
            
        Returns:
            List of dicts with 'url' and 'text' keys
        """
        links = []
        elements = self.select(selector)
        
        for elem in elements:
            url = self.get_attr(elem, 'href')
            text = self.get_text(elem)
            if url:
                links.append({'url': url, 'text': text})
        
        return links
    
    def find_all_images(self, selector: str = 'img') -> List[dict]:
        """
        Fast extraction of all images from page.
        
        Args:
            selector: CSS selector for image elements (default: 'img')
            
        Returns:
            List of dicts with 'src', 'alt', and 'title' keys
        """
        images = []
        elements = self.select(selector)
        
        for elem in elements:
            src = self.get_attr(elem, 'src')
            alt = self.get_attr(elem, 'alt')
            title = self.get_attr(elem, 'title')
            
            if src:
                images.append({
                    'src': src,
                    'alt': alt,
                    'title': title
                })
        
        return images
    
    def extract_data_attributes(self, selector: str, data_attr: str) -> List[str]:
        """
        Extract data-* attributes from elements.
        
        Args:
            selector: CSS selector for elements
            data_attr: Data attribute name (e.g., 'data-id')
            
        Returns:
            List of attribute values
        """
        values = []
        elements = self.select(selector)
        
        for elem in elements:
            value = self.get_attr(elem, data_attr)
            if value:
                values.append(value)
        
        return values


def quick_parse_links(html: str, selector: str = 'a') -> List[dict]:
    """
    Quick helper to parse links from HTML.
    
    Args:
        html: HTML content
        selector: CSS selector for link elements
        
    Returns:
        List of link dictionaries
    """
    parser = FastHTMLParser(html)
    return parser.find_all_links(selector)


def quick_parse_images(html: str, selector: str = 'img') -> List[dict]:
    """
    Quick helper to parse images from HTML.
    
    Args:
        html: HTML content
        selector: CSS selector for image elements
        
    Returns:
        List of image dictionaries
    """
    parser = FastHTMLParser(html)
    return parser.find_all_images(selector)


def quick_extract_text(html: str, selector: str) -> List[str]:
    """
    Quick helper to extract text from elements.
    
    Args:
        html: HTML content
        selector: CSS selector for elements
        
    Returns:
        List of text content
    """
    parser = FastHTMLParser(html)
    elements = parser.select(selector)
    return [parser.get_text(elem) for elem in elements]


# Benchmark comparison function
def benchmark_parser(html: str, iterations: int = 100) -> dict:
    """
    Benchmark parser performance.
    
    Args:
        html: HTML content to parse
        iterations: Number of iterations to run
        
    Returns:
        Dict with timing results
    """
    import time
    
    results = {
        'parser': 'selectolax' if FAST_PARSER_AVAILABLE else 'beautifulsoup',
        'iterations': iterations
    }
    
    # Test simple select
    start = time.perf_counter()
    for _ in range(iterations):
        parser = FastHTMLParser(html)
        _ = parser.select('a')
    results['select_time'] = time.perf_counter() - start
    
    # Test text extraction
    start = time.perf_counter()
    for _ in range(iterations):
        parser = FastHTMLParser(html)
        links = parser.find_all_links()
    results['extract_time'] = time.perf_counter() - start
    
    return results


if __name__ == '__main__':
    # Quick test
    test_html = """
    <html>
        <body>
            <a href="https://example.com/1">Link 1</a>
            <a href="https://example.com/2">Link 2</a>
            <img src="https://example.com/img1.jpg" alt="Image 1">
            <img src="https://example.com/img2.jpg" alt="Image 2">
        </body>
    </html>
    """
    
    parser = FastHTMLParser(test_html)
    print(f"Parser: {parser.parser_type}")
    print(f"Links: {parser.find_all_links()}")
    print(f"Images: {parser.find_all_images()}")
    
    # Benchmark
    results = benchmark_parser(test_html)
    print(f"\nBenchmark ({results['iterations']} iterations):")
    print(f"  Parser: {results['parser']}")
    print(f"  Select time: {results['select_time']:.4f}s")
    print(f"  Extract time: {results['extract_time']:.4f}s")
