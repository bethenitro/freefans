"""
Permissions Manager - Manages admin and worker permissions
"""

import json
import os
import logging
from typing import List, Optional, Dict
import threading

logger = logging.getLogger(__name__)


class PermissionsManager:
    """Manages admin and worker user IDs."""
    
    def __init__(self, config_path: str = 'permissions_config.json'):
        """Initialize permissions manager."""
        self.config_path = config_path
        self.lock = threading.Lock()
        self._load_config()
    
    def _load_config(self):
        """Load permissions configuration from file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.error(f"Error loading permissions config: {e}")
                self._init_default_config()
        else:
            self._init_default_config()
    
    def _init_default_config(self):
        """Initialize default configuration."""
        self.config = {
            'admins': [],
            'workers': [],
            'settings': {
                'auto_save': True
            }
        }
        self._save_config()
    
    def _save_config(self):
        """Save permissions configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving permissions config: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        with self.lock:
            return user_id in self.config.get('admins', [])
    
    def is_worker(self, user_id: int) -> bool:
        """Check if user is a worker."""
        with self.lock:
            return user_id in self.config.get('workers', [])
    
    def add_admin(self, user_id: int) -> bool:
        """Add a user as admin."""
        with self.lock:
            if user_id not in self.config['admins']:
                self.config['admins'].append(user_id)
                self._save_config()
                logger.info(f"Added admin: {user_id}")
                return True
            return False
    
    def remove_admin(self, user_id: int) -> bool:
        """Remove a user from admins."""
        with self.lock:
            if user_id in self.config['admins']:
                self.config['admins'].remove(user_id)
                self._save_config()
                logger.info(f"Removed admin: {user_id}")
                return True
            return False
    
    def add_worker(self, user_id: int) -> bool:
        """Add a user as worker."""
        with self.lock:
            if user_id not in self.config['workers']:
                self.config['workers'].append(user_id)
                self._save_config()
                logger.info(f"Added worker: {user_id}")
                return True
            return False
    
    def remove_worker(self, user_id: int) -> bool:
        """Remove a user from workers."""
        with self.lock:
            if user_id in self.config['workers']:
                self.config['workers'].remove(user_id)
                self._save_config()
                logger.info(f"Removed worker: {user_id}")
                return True
            return False
    
    def get_admins(self) -> List[int]:
        """Get list of all admin user IDs."""
        with self.lock:
            return self.config.get('admins', []).copy()
    
    def get_workers(self) -> List[int]:
        """Get list of all worker user IDs."""
        with self.lock:
            return self.config.get('workers', []).copy()
    
    def get_all_permissions(self) -> Dict:
        """Get all permissions data."""
        with self.lock:
            return {
                'admins': self.config.get('admins', []).copy(),
                'workers': self.config.get('workers', []).copy()
            }


# Singleton instance
_permissions_manager = None


def get_permissions_manager() -> PermissionsManager:
    """Get singleton instance of PermissionsManager."""
    global _permissions_manager
    if _permissions_manager is None:
        _permissions_manager = PermissionsManager()
    return _permissions_manager
