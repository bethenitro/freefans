"""
Background Scraper - Periodically scrapes and updates cache for popular creators
Enhanced with multithreading, intelligent batching, and advanced rate limiting
Now modularized for better maintainability
"""

# Import the modular BackgroundScraper
from scrapers.background_scraper import BackgroundScraper

# Re-export for backward compatibility
__all__ = ['BackgroundScraper']

