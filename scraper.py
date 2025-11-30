#!/usr/bin/env python3
"""
OnlyFans Forum Scraper

This script scrapes model information from the SimpCity OnlyFans forum,
extracting model names and their profile links across multiple pages.
"""

import asyncio
import csv
import json
import os
import random
import re
import time
from typing import List, Dict, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


class OnlyFansForumScraper:
    """Scraper for OnlyFans forum model information."""
    
    def __init__(self):
        """Initialize the scraper with headers and base URL."""
        self.base_url = "https://simpcity.cr"
        self.forum_url = "https://simpcity.cr/forums/onlyfans.8/"
        self.data_file = 'onlyfans_models.csv'
        self.checkpoint_file = 'scraper_checkpoint.json'
        
        # Headers from the curl command
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://simpcity.cr/forums/onlyfans.8/page-2',
            'Sec-GPC': '1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Connection': 'keep-alive',
            'Cookie': '__ddg8_=SKdedQOzjarOknir; __ddg10_=1764437520; __ddg9_=205.147.17.5; __ddg1_=Z3YDAoXVvny2UQAHWVQa; cucksid=583ae1f4649e30d9968f89a97840ac73e0ad10b22d40590a45478e97964a2165; cucksed=b3; ogaddgmetaprof_csrf=TIbqKry1rfYSmwex; UGVyc2lzdFN0b3JhZ2U=%7B%7D; bnState_2086817=%7B%22impressions%22%3A12%2C%22delayStarted%22%3A0%7D; bnState_2086797=%7B%22impressions%22%3A6%2C%22delayStarted%22%3A0%7D; __PPU_ppucnt=1'
        }
    
    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        """
        Fetch a single page and return its HTML content.
        
        Args:
            client: The HTTP client instance
            url: The URL to fetch
            
        Returns:
            The HTML content of the page
            
        Raises:
            httpx.RequestError: If the request fails
        """
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            print(f"✓ Successfully fetched: {url}")
            return response.text
        except httpx.RequestError as e:
            print(f"✗ Error fetching {url}: {e}")
            raise
    
    def parse_model_info(self, html: str) -> List[Dict[str, str]]:
        """
        Parse model information from HTML content.
        
        Args:
            html: The HTML content to parse
            
        Returns:
            List of dictionaries containing model name and link
        """
        soup = BeautifulSoup(html, 'lxml')
        models = []
        
        # Find all thread items (using a lambda to check for required classes)
        thread_items = soup.find_all('div', class_=lambda x: x and 'structItem' in x and 'structItem--thread' in x if x else False)
        
        for item in thread_items:
            # Get all classes for this item
            item_classes = item.get('class', [])
            
            # Skip sticky threads (News prefix) and guidelines
            if 'is-prefix1' in item_classes:
                continue
                
            # Check if it's in the sticky section
            parent = item.find_parent('div', class_='structItemContainer-group--sticky')
            if parent:
                continue
                
            # Find the main thread title container
            title_div = item.find('div', class_='structItem-title')
            if not title_div:
                continue
                
            # Look for the main thread link (with data-tp-primary attribute)
            link_element = title_div.find('a', attrs={'data-tp-primary': 'on'})
            if not link_element:
                continue
            
            # Extract model name and link
            model_name = link_element.get_text(strip=True)
            relative_link = link_element.get('href', '')
            
            if model_name and relative_link and relative_link.startswith('/threads/'):
                # Convert relative link to absolute URL
                full_link = urljoin(self.base_url, relative_link)
                
                models.append({
                    'model_name': model_name,
                    'profile_link': full_link
                })
        
        return models
    
    def clean_model_name(self, name: str) -> str:
        """
        Clean the model name by removing extra whitespace and special characters.
        
        Args:
            name: The raw model name
            
        Returns:
            Cleaned model name
        """
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', name.strip())
        return cleaned
    
    def load_checkpoint(self) -> Dict:
        """Load checkpoint data from file."""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {'last_page': 0, 'total_models': 0, 'scraped_links': set()}
    
    def save_checkpoint(self, page_num: int, total_models: int, scraped_links: set):
        """Save checkpoint data to file."""
        checkpoint_data = {
            'last_page': page_num,
            'total_models': total_models,
            'scraped_links': list(scraped_links)  # Convert set to list for JSON serialization
        }
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)
    
    def load_existing_data(self) -> Tuple[List[Dict[str, str]], set]:
        """Load existing data from CSV file."""
        models = []
        scraped_links = set()
        
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        models.append(row)
                        scraped_links.add(row['profile_link'])
                print(f"📂 Loaded {len(models)} existing models from {self.data_file}")
            except FileNotFoundError:
                pass
        
        return models, scraped_links
    
    def save_to_csv(self, models: List[Dict[str, str]], filename: str = None, append_mode: bool = False):
        """
        Save the model data to a CSV file.
        
        Args:
            models: List of model dictionaries
            filename: Output CSV filename
            append_mode: If True, append to existing file; if False, overwrite
        """
        if filename is None:
            filename = self.data_file
            
        if not models:
            return
            
        mode = 'a' if append_mode and os.path.exists(filename) else 'w'
        write_header = mode == 'w' or not os.path.exists(filename)
        
        print(f"💾 {'Appending' if append_mode else 'Saving'} {len(models)} models to {filename}...")
        
        with open(filename, mode, newline='', encoding='utf-8') as csvfile:
            fieldnames = ['model_name', 'profile_link']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header only if it's a new file or overwrite mode
            if write_header:
                writer.writeheader()
            
            # Write model data
            for model in models:
                writer.writerow({
                    'model_name': self.clean_model_name(model['model_name']),
                    'profile_link': model['profile_link']
                })
        
        print(f"✓ Successfully {'appended' if append_mode else 'saved'} data to {filename}")
    
    def append_new_models_to_csv(self, new_models: List[Dict[str, str]]):
        """Append new models to the CSV file, avoiding duplicates."""
        if new_models:
            self.save_to_csv(new_models, append_mode=True)
    
    async def scrape_all_pages(self, max_pages: int = 165) -> List[Dict[str, str]]:
        """
        Scrape model information from all pages with incremental saving and checkpointing.
        
        Args:
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of all model dictionaries
        """
        # Load existing data and checkpoint
        all_models, scraped_links = self.load_existing_data()
        checkpoint = self.load_checkpoint()
        
        # Convert scraped_links from checkpoint (which is a list) back to a set
        if checkpoint.get('scraped_links'):
            scraped_links.update(checkpoint['scraped_links'])
        
        start_page = checkpoint.get('last_page', 0) + 1
        
        if start_page > 1:
            print(f"🔄 Resuming from page {start_page} (found checkpoint)")
            print(f"📊 Already have {len(all_models)} models")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"🚀 Starting to scrape pages {start_page} to {max_pages}...")
            print(f"📋 Base URL: {self.forum_url}")
            print("-" * 50)
            
            for page_num in range(start_page, max_pages + 1):
                try:
                    # Construct URL for each page
                    if page_num == 1:
                        url = self.forum_url
                    else:
                        url = f"{self.forum_url}page-{page_num}"
                    
                    # Random delay before each request (2-8 seconds)
                    delay = random.uniform(2.0, 8.0)
                    if page_num > start_page:  # Don't delay on the first page
                        print(f"⏱️  Waiting {delay:.1f} seconds before next request...")
                        await asyncio.sleep(delay)
                    
                    # Fetch the page
                    html = await self.fetch_page(client, url)
                    
                    # Parse model information
                    page_models = self.parse_model_info(html)
                    
                    # Filter out models we already have
                    new_models = []
                    for model in page_models:
                        if model['profile_link'] not in scraped_links:
                            new_models.append(model)
                            scraped_links.add(model['profile_link'])
                    
                    print(f"📊 Page {page_num}: Found {len(page_models)} models ({len(new_models)} new)")
                    
                    # Add new models to the collection
                    all_models.extend(new_models)
                    
                    # Save new models to CSV immediately (append mode)
                    if new_models:
                        self.append_new_models_to_csv(new_models)
                    
                    # Save checkpoint after each page
                    self.save_checkpoint(page_num, len(all_models), scraped_links)
                    
                    print(f"💾 Progress saved. Total models so far: {len(all_models)}")
                    
                except KeyboardInterrupt:
                    print(f"\n⚠️ Interrupted by user at page {page_num}")
                    print(f"📊 Progress saved up to page {page_num - 1}")
                    break
                except Exception as e:
                    print(f"❌ Error processing page {page_num}: {e}")
                    print(f"⏭️  Continuing to next page...")
                    continue
            
            print("-" * 50)
            print(f"🎉 Fetching completed! Total models found: {len(all_models)}")
            
            # Clean up checkpoint file when fully completed
            if page_num >= max_pages and os.path.exists(self.checkpoint_file):
                os.remove(self.checkpoint_file)
                print("🧹 Removed checkpoint file (Fetching completed)")
            
            return all_models


async def main():
    """Main function to run the scraper."""
    scraper = OnlyFansForumScraper()
    
    try:
        # Check if we have existing data
        existing_models, _ = scraper.load_existing_data()
        checkpoint = scraper.load_checkpoint()
        
        if existing_models:
            print(f"📂 Found existing data with {len(existing_models)} models")
            if checkpoint.get('last_page', 0) > 0:
                print(f"🔄 Can resume from page {checkpoint['last_page'] + 1}")
        
        # Scrape all pages (you can change this number if needed)
        models = await scraper.scrape_all_pages(max_pages=165)
        
        # Display some statistics
        print("\n📈 Final Fetching Statistics:")
        print(f"Total unique models: {len(models)}")
        print(f"CSV file: {scraper.data_file}")
        
        # Show first few models as example
        if models:
            print("\n🎯 First 5 models found:")
            for i, model in enumerate(models[:5], 1):
                print(f"{i}. {model['model_name']}")
                print(f"   Link: {model['profile_link']}")
        
    except KeyboardInterrupt:
        print("\n⚠️ Fetching interrupted by user")
        print("💾 Progress has been saved. You can resume by running the script again.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        print("💾 Progress has been saved up to the last successful page.")


if __name__ == "__main__":
    print("=" * 60)
    print("🔥 OnlyFans Forum Scraper")
    print("=" * 60)
    
    # Run the async main function
    asyncio.run(main())