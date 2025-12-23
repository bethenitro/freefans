#!/usr/bin/env python3
"""
Script to update all import statements after reorganizing project structure
"""

import os
import re

# Define import mappings (old -> new)
IMPORT_MAPPINGS = {
    'from managers.cache_manager import': 'from managers.cache_manager import',
    'from managers.permissions_manager import': 'from managers.permissions_manager import',
    'from managers.request_manager import': 'from managers.request_manager import',
    'from managers.title_manager import': 'from managers.title_manager import',
    'from core.user_session import': 'from core.user_session import',
    'from core.content_manager import': 'from core.content_manager import',
    'from core.content_scraper import': 'from core.content_scraper import',
    'from core.scraper import': 'from core.scraper import',
    'from services.fastapi_server import': 'from services.fastapi_server import',
    'from services.landing_service import': 'from services.landing_service import',
    'from utils.video_preview_extractor import': 'from utils.video_preview_extractor import',
    'from utils.background_preview_extractor import': 'from utils.background_preview_extractor import',
    'from utils.background_scraper import': 'from utils.background_scraper import',
    'import managers.cache_manager as cache_manager': 'import managers.cache_manager as cache_manager',
    'import managers.permissions_manager as permissions_manager': 'import managers.permissions_manager as permissions_manager',
    'import managers.request_manager as request_manager': 'import managers.request_manager as request_manager',
    'import managers.title_manager as title_manager': 'import managers.title_manager as title_manager',
    'import core.user_session as user_session': 'import core.user_session as user_session',
    'import core.content_manager as content_manager': 'import core.content_manager as content_manager',
    'import core.content_scraper as content_scraper': 'import core.content_scraper as content_scraper',
    'import services.landing_service as landing_service': 'import services.landing_service as landing_service',
    'import utils.video_preview_extractor as video_preview_extractor': 'import utils.video_preview_extractor as video_preview_extractor',
}

def update_file(filepath):
    """Update imports in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply all mappings
        for old_import, new_import in IMPORT_MAPPINGS.items():
            content = content.replace(old_import, new_import)
        
        # Only write if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Updated: {filepath}")
            return True
        return False
    except Exception as e:
        print(f"✗ Error updating {filepath}: {e}")
        return False

def main():
    """Update imports in all Python files"""
    print("🔄 Updating import statements...\n")
    
    # Directories to scan
    dirs_to_scan = [
        'bot',
        'core',
        'managers',
        'services',
        'utils',
        'scrapers',
        'scripts',
        '.'  # Root directory
    ]
    
    updated_count = 0
    
    for directory in dirs_to_scan:
        if not os.path.exists(directory):
            continue
            
        for root, dirs, files in os.walk(directory):
            # Skip __pycache__ and env directories
            if '__pycache__' in root or 'env' in root or '.git' in root:
                continue
                
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    if update_file(filepath):
                        updated_count += 1
    
    print(f"\n✅ Updated {updated_count} files")

if __name__ == '__main__':
    main()
