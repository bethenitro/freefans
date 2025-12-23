# Supabase Integration Setup Guide

This guide will help you set up Supabase (remote PostgreSQL database) integration alongside your existing local SQLite database.

## Overview

The dual cache system provides:
- **Local Storage**: Fast SQLite database for immediate access
- **Remote Storage**: Supabase PostgreSQL for data persistence and sharing
- **Automatic Sync**: Data is stored in both locations automatically
- **Fallback Support**: If local data is missing, it's retrieved from Supabase
- **Backward Compatibility**: Existing functionality remains unchanged

## Prerequisites

1. **Supabase Account**: Sign up at [supabase.com](https://supabase.com)
2. **Python Dependencies**: Install required packages
3. **Database Credentials**: Get your Supabase connection details

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies added:
- `sqlalchemy>=2.0.0` - ORM for database operations
- `psycopg2-binary` - PostgreSQL adapter
- `python-dotenv` - Environment variable management

## Step 2: Get Supabase Credentials

1. Create a new project in Supabase
2. Go to **Settings** → **Database**
3. Find your connection details:
   - Host: `db.xxxxxxxxxx.supabase.co`
   - Database: `postgres`
   - Port: `5432`
   - User: `postgres`
   - Password: `[your-password]`

## Step 3: Configure Environment Variables

Add these variables to your `.env` files:

### Main `.env` file:
```env
# Supabase Database Configuration
SUPABASE_DATABASE_URL=postgresql+psycopg2://postgres:[YOUR_PASSWORD]@db.[YOUR_PROJECT_ID].supabase.co:5432/postgres
ENABLE_SUPABASE=true
```

### `telegram_bot/.env` file:
```env
# Add the same Supabase configuration
SUPABASE_DATABASE_URL=postgresql+psycopg2://postgres:[YOUR_PASSWORD]@db.[YOUR_PROJECT_ID].supabase.co:5432/postgres
ENABLE_SUPABASE=true
```

**Important**: Replace `[YOUR_PASSWORD]` and `[YOUR_PROJECT_ID]` with your actual Supabase credentials.

## Step 4: Initialize Database

Run the initialization script:

```bash
python scripts/init_supabase.py
```

This script will:
1. Connect to your Supabase database
2. Create the required tables
3. Optionally migrate existing SQLite data
4. Verify the setup

## Step 5: Update Your Code (If Needed)

If you're upgrading from an existing installation, run the migration script:

```bash
# Check what would be changed (dry run)
python scripts/migrate_to_dual_cache.py --dry-run

# Apply the changes
python scripts/migrate_to_dual_cache.py
```

## Step 6: Test the Integration

1. Start your bot normally
2. Check the `/cache_stats` command - it should show Supabase status
3. Perform some operations (search creators, cache content)
4. Verify data appears in both local SQLite and Supabase

## Database Schema

The following tables are created in Supabase:

### `creators` table
- `id` (Primary Key)
- `name` (Creator name, indexed)
- `content` (JSON content data)
- `created_at`, `updated_at` (Timestamps)
- `post_count` (Number of posts)
- `last_scraped` (Last scrape timestamp)

### `onlyfans_users` table
- `id` (Primary Key)
- `username` (Unique username)
- `display_name` (Display name)
- `created_at`, `updated_at` (Timestamps)

### `onlyfans_posts` table
- `id` (Primary Key)
- `username` (Foreign reference)
- `post_id` (Post identifier)
- `content` (JSON post data)
- `created_at`, `updated_at` (Timestamps)

## How It Works

### Data Flow
1. **Write Operations**: Data is saved to SQLite first, then synced to Supabase
2. **Read Operations**: Data is read from SQLite first, falls back to Supabase if not found
3. **Cache Warming**: Data retrieved from Supabase is cached locally for faster future access

### Benefits
- **Performance**: Local SQLite provides fast access
- **Reliability**: Supabase provides persistent, backed-up storage
- **Scalability**: Multiple bot instances can share the same Supabase database
- **Data Safety**: Your data is stored in multiple locations

## Troubleshooting

### Connection Issues
```
❌ Failed to connect to Supabase database
```
- Check your `SUPABASE_DATABASE_URL` format
- Verify your Supabase project is active
- Ensure your password is correct
- Check network connectivity

### Import Errors
```
ModuleNotFoundError: No module named 'sqlalchemy'
```
- Run `pip install -r requirements.txt`
- Ensure you're using the correct Python environment

### Permission Issues
```
❌ Failed to create database tables
```
- Verify your Supabase user has table creation permissions
- Check if tables already exist in Supabase dashboard

### Data Sync Issues
- Check logs for specific error messages
- Verify both SQLite and Supabase are accessible
- Use the force sync feature: `cache_manager.force_sync_to_supabase()`

## Advanced Configuration

### Disable Supabase Temporarily
Set `ENABLE_SUPABASE=false` in your `.env` file to disable Supabase integration without changing code.

### Connection Pool Settings
The database connection uses these default settings:
- Pool size: 5 connections
- Max overflow: 10 connections
- Connection recycling: 1 hour
- Pre-ping: Enabled (verifies connections before use)

### Manual Data Migration
```python
from managers.dual_cache_manager import DualCacheManager

cache_manager = DualCacheManager()
result = cache_manager.force_sync_to_supabase()
print(f"Synced: {result}")
```

## Security Notes

- Never commit your `.env` files to version control
- Use strong passwords for your Supabase database
- Consider enabling Row Level Security (RLS) in Supabase for additional protection
- Regularly backup your Supabase database

## Support

If you encounter issues:
1. Check the logs for detailed error messages
2. Verify your environment variables are correct
3. Test the connection using the initialization script
4. Check the Supabase dashboard for database status

The integration is designed to be non-breaking - if Supabase is unavailable, the bot will continue working with local SQLite storage only.