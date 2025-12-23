#!/usr/bin/env python3
"""
Supabase Database Initialization Script
Sets up the database schema and optionally migrates existing SQLite data
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'telegram_bot'))

import sys
from pathlib import Path

# Add telegram_bot to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'telegram_bot'))

from shared.config.database import init_database, create_tables, is_database_available
from managers.dual_cache_manager import DualCacheManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Initialize Supabase database and optionally migrate data."""
    print("🚀 Initializing Supabase Database...")
    print("=" * 50)
    
    # Step 1: Initialize database connection
    print("1. Connecting to Supabase...")
    if not init_database():
        print("❌ Failed to connect to Supabase database")
        print("   Please check your SUPABASE_DATABASE_URL and ENABLE_SUPABASE settings")
        return False
    
    print("✅ Connected to Supabase successfully")
    
    # Step 2: Create tables
    print("\n2. Creating database tables...")
    if not create_tables():
        print("❌ Failed to create database tables")
        return False
    
    print("✅ Database tables created successfully")
    
    # Step 3: Verify connection
    print("\n3. Verifying database setup...")
    if not is_database_available():
        print("❌ Database verification failed")
        return False
    
    print("✅ Database setup verified")
    
    # Step 4: Optional data migration
    print("\n4. Checking for existing SQLite data...")
    try:
        cache_manager = DualCacheManager()
        
        if cache_manager.is_supabase_available():
            print("✅ Dual cache manager initialized successfully")
            
            # Check if there's existing SQLite data to migrate
            sqlite_stats = cache_manager.get_cache_stats()
            
            if sqlite_stats.get('total_creators', 0) > 0 or sqlite_stats.get('total_onlyfans_users', 0) > 0:
                print(f"\n📊 Found existing SQLite data:")
                print(f"   - Creators: {sqlite_stats.get('total_creators', 0)}")
                print(f"   - OnlyFans Users: {sqlite_stats.get('total_onlyfans_users', 0)}")
                print(f"   - OnlyFans Posts: {sqlite_stats.get('total_onlyfans_posts', 0)}")
                
                migrate = input("\n🔄 Would you like to migrate this data to Supabase? (y/N): ").lower().strip()
                
                if migrate in ['y', 'yes']:
                    print("\n🔄 Starting data migration...")
                    
                    # Ask if user wants to clear existing Supabase data first
                    clear_first = input("🗑️  Clear existing Supabase data first? (recommended for clean sync) (Y/n): ").lower().strip()
                    
                    if clear_first in ['', 'y', 'yes']:
                        print("🗑️  Clearing existing Supabase data and performing clean sync...")
                        result = cache_manager.clear_supabase_and_resync()
                    else:
                        print("🔄 Performing incremental sync...")
                        result = cache_manager.force_sync_to_supabase()
                    
                    if 'error' in result:
                        print(f"❌ Migration failed: {result['error']}")
                    else:
                        print("✅ Migration completed successfully!")
                        print(f"   - Migrated creators: {result.get('synced_creators', 0)}")
                        print(f"   - Migrated posts: {result.get('synced_posts', 0)}")
                        if result.get('errors', 0) > 0:
                            print(f"   - Errors: {result.get('errors', 0)}")
                        if result.get('skipped_empty', 0) > 0:
                            print(f"   - Skipped empty creators: {result.get('skipped_empty', 0)}")
                else:
                    print("⏭️  Skipping data migration")
            else:
                print("ℹ️  No existing SQLite data found to migrate")
        else:
            print("❌ Dual cache manager initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during cache manager setup: {e}")
        return False
    
    # Step 5: Final verification
    print("\n5. Final verification...")
    final_stats = cache_manager.get_cache_stats()
    
    print("✅ Supabase integration setup complete!")
    print("\n📊 Current database status:")
    print(f"   - Storage type: {final_stats.get('storage_type', 'Unknown')}")
    print(f"   - Supabase enabled: {final_stats.get('supabase_enabled', False)}")
    
    if final_stats.get('supabase_enabled'):
        print(f"   - Supabase creators: {final_stats.get('supabase_creators', 0)}")
        print(f"   - Supabase OnlyFans users: {final_stats.get('supabase_onlyfans_users', 0)}")
        print(f"   - Supabase OnlyFans posts: {final_stats.get('supabase_onlyfans_posts', 0)}")
    
    print("\n🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Update your application to use DualCacheManager instead of CacheManager")
    print("2. Set your Supabase credentials in the .env file")
    print("3. Test the integration with your application")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)