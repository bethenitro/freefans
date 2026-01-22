"""
Permissions Manager - Manages admin and worker permissions
"""

import json
import os
import logging
from typing import List, Optional, Dict
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class PermissionsManager:
    """Manages admin and worker user IDs."""
    
    def __init__(self, config_path: str = None):
        """Initialize permissions manager."""
        if config_path is None:
            # Default to shared directory
            base_dir = Path(__file__).parent.parent.parent
            config_path = str(base_dir / 'shared' / 'config' / 'permissions_config.json')
        self.config_path = config_path
        self.lock = threading.Lock()
        logger.info(f"🔧 PermissionsManager initializing with config: {self.config_path}")
        logger.info(f"📁 Config file exists: {os.path.exists(self.config_path)}")
        self._load_config()
    
    def _load_config(self):
        """Load permissions configuration from file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"✅ Loaded permissions config from {self.config_path}")
                logger.info(f"📊 Main admin: {self.config.get('main_admin')}")
                logger.info(f"📊 Admins: {self.config.get('admins', [])}")
                logger.info(f"📊 Workers: {self.config.get('workers', [])}")
            except Exception as e:
                logger.error(f"❌ Error loading permissions config: {e}")
                self._init_default_config()
        else:
            logger.warning(f"⚠️ Permissions config not found at {self.config_path} - creating default")
            self._init_default_config()
    
    def _init_default_config(self):
        """Initialize default configuration."""
        self.config = {
            'main_admin': None,
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
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"💾 Saved permissions config to {self.config_path}")
            logger.info(f"📊 Saved - Main admin: {self.config.get('main_admin')}")
            logger.info(f"📊 Saved - Admins: {self.config.get('admins', [])}")
        except Exception as e:
            logger.error(f"❌ Error saving permissions config to {self.config_path}: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin (includes main admin)."""
        with self.lock:
            # Main admin is also an admin
            if user_id == self.config.get('main_admin'):
                return True
            return user_id in self.config.get('admins', [])
    
    def is_main_admin(self, user_id: int) -> bool:
        """Check if user is the main admin."""
        with self.lock:
            return user_id == self.config.get('main_admin')
    
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
                'main_admin': self.config.get('main_admin'),
                'admins': self.config.get('admins', []).copy(),
                'workers': self.config.get('workers', []).copy()
            }
    
    def has_main_admin(self) -> bool:
        """Check if a main admin is configured."""
        with self.lock:
            return self.config.get('main_admin') is not None
    
    def set_main_admin(self, user_id: int) -> bool:
        """Set a user as the main admin. Returns True if successful."""
        with self.lock:
            if self.config.get('main_admin') is not None:
                logger.warning(f"⚠️ Attempted to set main admin {user_id} when one already exists: {self.config.get('main_admin')}")
                return False
            self.config['main_admin'] = user_id
            logger.info(f"👑 Setting main admin to {user_id}")
            self._save_config()
            logger.info(f"✅ Main admin set successfully: {user_id}")
            return True
    
    def remove_main_admin(self) -> bool:
        """Remove the current main admin. Returns True if successful."""
        with self.lock:
            if self.config.get('main_admin') is None:
                return False
            old_admin = self.config['main_admin']
            self.config['main_admin'] = None
            self._save_config()
            logger.info(f"Removed main admin: {old_admin}")
            return True
    
    def get_main_admin(self) -> Optional[int]:
        """Get the main admin user ID."""
        with self.lock:
            return self.config.get('main_admin')


# Singleton instance
_permissions_manager = None


def get_permissions_manager() -> PermissionsManager:
    """Get singleton instance of PermissionsManager."""
    global _permissions_manager
    if _permissions_manager is None:
        _permissions_manager = PermissionsManager()
    return _permissions_manager
