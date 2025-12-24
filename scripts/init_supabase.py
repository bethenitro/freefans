#!/usr/bin/env python3
"""
Supabase Database Initialization Script
Sets up the database schema for Supabase-only storage
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.config.database import init_database, create_tables, is_database_available
from telegram_bot.managers.cache_factory import SupabaseCacheManager

def main():
    """Initialize Supabase database and verify setup."""
    print("🚀 Supabase Database Initialization")
    print("=" * 50)
    
    # Step 1: Check environment variables
    print("\n1. Checking environment configuration...")
    try:
        from decouple import config
        
        supabase_url = config('SUPABASE_URL', default=None)
        supabase_key = config('SUPABASE_KEY', default=None)
        
        if not supabase_url or not supabase_key:
            print("❌ Missing Supabase configuration!")
            print("Please set SUPABASE_URL and SUPABASE_KEY in your .env file")
            return False
        
        print("✅ Supabase configuration found")
        
    except Exception as e:
        print(f"❌ Error checking configuration: {e}")
        return False
    
    # Step 2: Test database connection
    print("\n2. Testing database connection...")
    if not is_database_available():
        print("❌ Cannot connect to Supabase database")
        print("Please check your SUPABASE_URL and SUPABASE_KEY")
        return False
    
    print("✅ Database connection successful")
    
    # Step 3: Initialize database and create tables
    print("\n3. Initializing database schema...")
    try:
        if init_database():
            if create_tables():
                print("✅ Database schema created successfully")
            else:
                print("❌ Failed to create database tables")
                return False
        else:
            print("❌ Database initialization failed")
            return False
    except Exception as e:
        print(f"❌ Error during database initialization: {e}")
        return False
    
    # Step 4: Test cache manager
    print("\n4. Testing Supabase cache manager...")
    try:
        cache_manager = SupabaseCacheManager()
        
        if cache_manager.supabase_available:
            print("✅ Supabase cache manager initialized successfully")
            
            # Get initial stats
            stats = cache_manager.get_cache_stats()
            print(f"\n📊 Current database statistics:")
            print(f"   - Creators: {stats.get('total_creators', 0)}")
            print(f"   - Content Items: {stats.get('total_content_items', 0)}")
            print(f"   - OnlyFans Users: {stats.get('total_onlyfans_users', 0)}")
            print(f"   - OnlyFans Posts: {stats.get('total_onlyfans_posts', 0)}")
            print(f"   - Storage Type: {stats.get('storage_type', 'Unknown')}")
        else:
            print("❌ Supabase cache manager initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during cache manager setup: {e}")
        return False
    
    # Step 5: Final verification
    print("\n5. Final verification...")
    final_stats = cache_manager.get_cache_stats()
    
    print("✅ Supabase integration setup complete!")
    print("\n📋 Setup Summary:")
    print(f"   - Database: Connected and ready")
    print(f"   - Tables: Created successfully")
    print(f"   - Cache Manager: Supabase-only mode")
    print(f"   - Storage: {final_stats.get('storage_type', 'Supabase only')}")
    
    print("\n🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Your application is now configured to use Supabase-only storage")
    print("2. All cache operations will use PostgreSQL instead of SQLite")
    print("3. Test the integration with your application")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)