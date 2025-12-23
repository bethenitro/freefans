"""
Request Manager - Handles saving user requests to CSV
"""

import csv
import os
import logging
from datetime import datetime
from typing import Dict, Optional
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

class RequestManager:
    """Manages user requests and saves them to CSV files"""
    
    def __init__(self, requests_dir: str = None):
        if requests_dir is None:
            # Default to shared directory
            base_dir = Path(__file__).parent.parent.parent
            requests_dir = str(base_dir / 'shared' / 'data' / 'requests')
        self.requests_dir = requests_dir
        self.creator_requests_file = os.path.join(requests_dir, 'creator_requests.csv')
        self.content_requests_file = os.path.join(requests_dir, 'content_requests.csv')
        self._lock = threading.Lock()
        
        # Create requests directory if it doesn't exist
        os.makedirs(requests_dir, exist_ok=True)
        
        # Initialize CSV files with headers if they don't exist
        self._initialize_csv_files()
    
    def _initialize_csv_files(self):
        """Initialize CSV files with headers if they don't exist"""
        # Creator requests CSV
        if not os.path.exists(self.creator_requests_file):
            with open(self.creator_requests_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Request ID',
                    'Timestamp',
                    'User ID',
                    'Platform',
                    'Username',
                    'Status'
                ])
            logger.info(f"Created creator requests file: {self.creator_requests_file}")
        
        # Content requests CSV
        if not os.path.exists(self.content_requests_file):
            with open(self.content_requests_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Request ID',
                    'Timestamp',
                    'User ID',
                    'Platform',
                    'Username',
                    'Content Details',
                    'Status'
                ])
            logger.info(f"Created content requests file: {self.content_requests_file}")
    
    def save_creator_request(self, user_id: int, platform: str, username: str) -> str:
        """
        Save a creator request to CSV.
        
        Args:
            user_id: Telegram user ID
            platform: Social media platform (OnlyFans, Instagram, etc.)
            username: Creator's username
        
        Returns:
            Request ID (timestamp-based)
        """
        with self._lock:
            try:
                timestamp = datetime.now()
                request_id = f"CR-{timestamp.strftime('%Y%m%d%H%M%S')}-{user_id}"
                
                with open(self.creator_requests_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        request_id,
                        timestamp.isoformat(),
                        user_id,
                        platform,
                        username,
                        'Pending'
                    ])
                
                logger.info(f"Saved creator request: {request_id} - {platform}/{username} from user {user_id}")
                return request_id
                
            except Exception as e:
                logger.error(f"Error saving creator request: {e}")
                return f"ERROR-{datetime.now().timestamp()}"
    
    def save_content_request(self, user_id: int, platform: str, username: str, details: str) -> str:
        """
        Save a content request to CSV.
        
        Args:
            user_id: Telegram user ID
            platform: Social media platform
            username: Creator's username
            details: Detailed description of requested content
        
        Returns:
            Request ID (timestamp-based)
        """
        with self._lock:
            try:
                timestamp = datetime.now()
                request_id = f"CT-{timestamp.strftime('%Y%m%d%H%M%S')}-{user_id}"
                
                with open(self.content_requests_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        request_id,
                        timestamp.isoformat(),
                        user_id,
                        platform,
                        username,
                        details,
                        'Pending'
                    ])
                
                logger.info(f"Saved content request: {request_id} - {platform}/{username} from user {user_id}")
                return request_id
                
            except Exception as e:
                logger.error(f"Error saving content request: {e}")
                return f"ERROR-{datetime.now().timestamp()}"
    
    def get_pending_creator_requests(self, limit: Optional[int] = None) -> list:
        """Get list of pending creator requests"""
        requests = []
        
        try:
            if not os.path.exists(self.creator_requests_file):
                return requests
            
            with open(self.creator_requests_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Status'] == 'Pending':
                        requests.append(row)
                        if limit and len(requests) >= limit:
                            break
        except Exception as e:
            logger.error(f"Error reading creator requests: {e}")
        
        return requests
    
    def get_pending_content_requests(self, limit: Optional[int] = None) -> list:
        """Get list of pending content requests"""
        requests = []
        
        try:
            if not os.path.exists(self.content_requests_file):
                return requests
            
            with open(self.content_requests_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Status'] == 'Pending':
                        requests.append(row)
                        if limit and len(requests) >= limit:
                            break
        except Exception as e:
            logger.error(f"Error reading content requests: {e}")
        
        return requests
    
    def get_request_stats(self) -> Dict[str, int]:
        """Get statistics about requests"""
        stats = {
            'total_creator_requests': 0,
            'pending_creator_requests': 0,
            'total_content_requests': 0,
            'pending_content_requests': 0
        }
        
        try:
            # Count creator requests
            if os.path.exists(self.creator_requests_file):
                with open(self.creator_requests_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        stats['total_creator_requests'] += 1
                        if row['Status'] == 'Pending':
                            stats['pending_creator_requests'] += 1
            
            # Count content requests
            if os.path.exists(self.content_requests_file):
                with open(self.content_requests_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        stats['total_content_requests'] += 1
                        if row['Status'] == 'Pending':
                            stats['pending_content_requests'] += 1
        
        except Exception as e:
            logger.error(f"Error getting request stats: {e}")
        
        return stats


# Global instance
_request_manager = None

def get_request_manager() -> RequestManager:
    """Get or create global RequestManager instance"""
    global _request_manager
    if _request_manager is None:
        _request_manager = RequestManager()
    return _request_manager
