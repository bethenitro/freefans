# Telegram Bot Service

## Overview
This is the Telegram bot component of FreeFans. It handles user interactions, content search, admin/worker management, community pooling system with dynamic pricing, and communicates with the landing server for content delivery.

## Directory Structure
```
telegram_bot/
├── main_bot.py             # Main bot entry point (renamed from bot.py)
├── coordinator_bot.py      # Coordinator bot (distributed mode)
├── worker_bot.py          # Worker bot (distributed mode)
├── requirements.txt        # Bot-specific dependencies
├── .env                    # Environment variables (bot token, etc.)
├── bot/                    # Bot handlers
│   ├── pool_handlers.py    # Community pooling handlers
│   ├── admin_pool_handlers.py # Admin pool management
│   ├── channel_handlers.py # Channel membership management
│   ├── channel_middleware.py # Channel membership middleware
│   └── ...
├── core/                   # Core business logic
├── managers/               # Data managers
│   ├── pool_manager.py     # Pool management with dynamic pricing
│   ├── payment_manager.py  # Telegram Stars payment processing
│   ├── channel_manager.py  # Channel membership management
│   └── ...
├── scrapers/               # Web scraping
├── utils/                  # Utilities
├── config/                 # Configuration files
│   └── required_channels.json # Required channels configuration
└── scripts/                # Management scripts
    └── setup_pools.py      # Initialize pooling system database
```

## Bot Commands

### 🔍 **User Commands (Everyone)**

#### Basic Navigation
- `/start` - Start the bot and show welcome message
- `/help` - Show help information and available commands
- `/cancel` - Cancel current operation

#### Content & Search
- `/pools` - View active community pools with dynamic pricing
- `/balance` - Check your Telegram Stars balance and transaction history
- `🔍 Search Creator` - Search for a specific creator's content (menu button)
- `🎲 Random Creator` - Get a random creator with lots of content (menu button)
- `🏊‍♀️ Community Pools` - Browse and join community pools (menu button)

#### Requests
- `📝 Request Creator` - Request a new creator to be added (menu button)
- `🎯 Request Content` - Request specific content from a creator (menu button)

**Note:** Users must join all required channels (configured by admins) before they can use the bot's features.

### 📢 **Channel Membership System**

The bot includes a channel membership verification system that requires users to join specific channels before accessing bot features.

#### How It Works
1. **Admin Configuration**: Admins add required channels using `/addrequiredchannel`
2. **User Verification**: When users try to use the bot, membership is automatically checked
3. **Join Prompts**: Users who haven't joined all channels see join buttons and instructions
4. **Bypass Options**: Admins can configure bypass rules for admins/workers

#### Channel Management Features
- **Multiple Channels**: Support for multiple required channels
- **Auto-Detection**: Bot automatically detects channel names and creates join links
- **Custom Messages**: Customizable welcome and membership check messages
- **Bypass Rules**: Configurable bypass for admins and workers
- **Real-time Checking**: Membership verified in real-time when users interact with bot

### 👑 **Main Admin Commands**

#### User Management
- `/addadmin <user_id>` - Add a sub-admin
- `/removeadmin <user_id>` - Remove a sub-admin
- `/addworker <user_id>` - Add a worker
- `/removeworker <user_id>` - Remove a worker
- `/listadmins` - List all admins
- `/listworkers` - List all workers

#### System Management
- `/requests` - View pending user requests
- `/titles` - View pending title submissions from workers
- `/adminstats` - View system statistics
- `/cache` - View cache statistics

#### Title Management
- `/approve <submission_id>` - Approve a worker's title submission
- `/reject <submission_id>` - Reject a worker's title submission
- `/bulkapprove` - Bulk approve multiple title submissions
- `/bulkreject` - Bulk reject multiple title submissions
- `/deletions` - View pending video deletion requests
- `/approvedelete <request_id>` - Approve video deletion
- `/rejectdelete <request_id>` - Reject video deletion

#### Admin Setup
- `/setupmainadmin` - Set up main admin (first time only)
- `/removemainadmin` - Remove main admin status
- `/confirmmainadminremoval` - Confirm main admin removal

#### Community Pooling System
- `/poolrequests` - View pending requests that can become pools
- `/poolstats` - View pool system statistics and metrics
- `/createpool request <request_id> <total_cost>` - Create pool from existing request
- `/createpool manual <creator> <title> <type> <total_cost> [description]` - Create manual pool
- `/completepool <pool_id> <content_url>` - Mark pool as completed and deliver content
- `/cancelpool <pool_id> [reason]` - Cancel pool and refund all contributors

#### Channel Management System
- `/addrequiredchannel <channel_id> <channel_name> [channel_link]` - Add required channel
- `/removerequiredchannel <channel_id>` - Remove required channel
- `/listrequiredchannels` - List all required channels
- `/channelsettings` - Configure channel membership settings
- `/setwelcomemessage <text>` - Set custom welcome message
- `/setmembershipmessage <text>` - Set custom membership check message
- `/channeldiagnostics` - Diagnose channel configuration issues
- `/testchannels <user_id>` - Test specific user's channel membership

### 🔧 **Sub-Admin Commands**

Sub-admins have access to the same commands as main admins except:
- Cannot add/remove other admins (`/addadmin`, `/removeadmin`)
- Cannot use admin setup commands (`/setupmainadmin`, `/removemainadmin`, `/confirmmainadminremoval`)

All other commands are available including:
- Worker management, content management, title management, pooling system

### 👷 **Worker Commands**

#### Worker Features
- `/mystats` - View your worker statistics (submissions, approvals, etc.)
- `/workerhelp` - Show worker-specific help and guidelines

#### Title Submissions
- Reply to video messages with suggested titles (interactive feature)
- Submit video deletion requests for inappropriate content (interactive feature)

## Community Pooling System

### 🎯 **How Dynamic Pricing Works**

The community pooling system uses dynamic pricing where the cost per user decreases as more people join:

**Example: 100 Star Pool (Max 50 Contributors)**
- 1st person: ~25 Stars (early adopter price)
- 5th person: ~15 Stars (price dropping)
- 10th person: ~8 Stars (getting cheaper)
- 25th person: ~4 Stars (much cheaper)
- 50th person: ~2 Stars (minimum price)

### 📋 **Pool Creation Workflow**

1. **User requests content** via existing request system
2. **Admin views requests**: `/poolrequests`
3. **Admin creates pool**: `/createpool request CR-123456789 100`
4. **Users join pool** at current dynamic price via `/pools`
5. **Price decreases** automatically as more people join
6. **Pool completes** when total cost is reached
7. **Admin delivers content**: `/completepool POOL-123 https://content-url`
8. **All contributors get access** to the unlocked content

### 💰 **Pool Management Examples**

```bash
# View pending requests that can become pools
/poolrequests

# Create pool from existing request (100 Stars total)
/createpool request CR-20240115120000-123456789 100

# Create manual pool
/createpool manual bella_thorne "Beach Photos" photo_set 150 "Exclusive content"

# Check pool statistics
/poolstats

# Complete a pool with content
/completepool POOL-20240115120000-ABC123 https://example.com/content/123

# Cancel a pool (refunds all contributors)
/cancelpool POOL-20240115120000-ABC123 Content no longer available
```

### 🏊‍♀️ **User Pool Interaction**

Users interact with pools through:
- **Menu Button**: `🏊‍♀️ Community Pools`
- **Command**: `/pools`
- **Balance Check**: `/balance`

Each pool shows:
- Current price per person (dynamic)
- How price decreases with more contributors
- Progress toward completion
- Time remaining before expiration

## Setup

### 1. Install Dependencies
```bash
cd telegram_bot
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create/edit `.env` file:
```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Landing Server URL (if on different server)
LANDING_BASE_URL=https://your-landing-server.com
LANDING_SECRET_KEY=your-secret-key

# Optional
LANDING_ENABLED=true
```

### 3. Configure Shared Resources
The bot needs access to the `shared/` directory for:
- `shared/config/` - Configuration files
- `shared/data/` - Database and CSV files

**Option A: Same Server**
```bash
# shared/ directory should be at ../shared/ relative to telegram_bot/
```

**Option B: Different Servers**
```bash
# Sync shared directory to bot server
rsync -av ../shared/ /path/to/telegram_bot/shared/

# Or mount as network drive/volume
```

### 4. Initialize Data
```bash
# Create admin users
python scripts/manage_permissions.py add-admin YOUR_TELEGRAM_USER_ID

# Initialize community pooling system (creates new database tables)
python scripts/setup_pools.py

# Optional: Pre-populate cache
python scripts/manual_cache.py
```

### 5. Environment Variables for Pooling
Add to your `.env` file:
```env
# Existing variables...
TELEGRAM_BOT_TOKEN=your_bot_token_here
LANDING_BASE_URL=https://your-landing-server.com

# Supabase Database (required for pooling system)
SUPABASE_DATABASE_URL=postgresql://user:password@host:port/database

# Admin Setup Password (for first-time main admin setup)
ADMIN_SETUP_PASSWORD=your_secure_password_here
```

### 6. Set Up Channel Requirements (Optional)

The bot includes a channel membership verification system. To require users to join specific channels:

#### Step 1: Add the Bot to Your Channels
1. Add your bot as an **administrator** to each channel you want to require
2. Give the bot permission to see members (needed to check membership)

#### Step 2: Configure Required Channels
```bash
# Add a public channel
/addrequiredchannel @yourchannel "Your Channel Name"

# Add a private channel (get channel ID from @userinfobot)
/addrequiredchannel -1001234567890 "Private Channel" https://t.me/+InviteLink

# List all required channels
/listrequiredchannels

# Configure settings
/channelsettings
```

#### Step 3: Customize Messages (Optional)
```bash
# Set welcome message
/setwelcomemessage Welcome! Join our channels to access exclusive content.

# Set membership check message
/setmembershipmessage Please join these channels to use the bot:
```

#### Channel Management Features
- **Bypass Rules**: Configure if admins/workers can bypass channel requirements
- **Multiple Channels**: Users must join ALL required channels
- **Real-time Verification**: Membership checked every time user interacts with bot
- **Custom Messages**: Personalize welcome and membership messages
- **Auto-detection**: Bot automatically gets channel names and creates join buttons

#### Example Setup
```bash
# Add main channel
/addrequiredchannel @freefanschannel "FreeFans Updates"

# Add VIP channel  
/addrequiredchannel @freefansvip "FreeFans VIP" https://t.me/+VipInviteLink

# Configure to allow admins to bypass
/channelsettings
# Use buttons to toggle "Admin Bypass: ON"

# Set custom welcome
/setwelcomemessage 🔥 Welcome to FreeFans! Join our channels for exclusive access to premium content.
```

## Running the Bot

### Development
```bash
python main_bot.py
```

### Production (with systemd)
Create `/etc/systemd/system/freefans-bot.service`:
```ini
[Unit]
Description=FreeFans Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/telegram_bot
Environment="PATH=/path/to/telegram_bot/env/bin"
ExecStart=/path/to/telegram_bot/env/bin/python main_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable freefans-bot
sudo systemctl start freefans-bot
sudo systemctl status freefans-bot
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Your Telegram Bot API token |
| `SUPABASE_DATABASE_URL` | Yes | - | PostgreSQL connection string for pooling system |
| `LANDING_BASE_URL` | No | `http://localhost:8001` | Landing server URL |
| `LANDING_SECRET_KEY` | No | `your-secret-key` | Secret key for landing server auth |
| `LANDING_ENABLED` | No | `true` | Enable/disable landing pages |

## Management Scripts

### Initialize Pooling System
```bash
# Set up database tables for community pooling
python scripts/setup_pools.py
```

### Add Admin/Worker
```bash
python scripts/manage_permissions.py add-admin <user_id>
python scripts/manage_permissions.py add-worker <user_id>
python scripts/manage_permissions.py list
```

### Manual Cache Population
```bash
python scripts/manual_cache.py
```

## Shared Directory Structure

The bot requires access to:
```
../shared/
├── config/
│   ├── curl_config.txt
│   ├── content_domains.txt
│   ├── video_domains.txt
│   ├── permissions_config.json
│   └── database.py              # Database configuration
└── data/
    ├── onlyfans_models.csv
    ├── requests/
    │   ├── creator_requests.csv  # Used for pool creation
    │   └── content_requests.csv  # Used for pool creation
    ├── title_submissions/
    │   ├── pending_titles.csv
    │   ├── approved_titles.csv
    │   └── rejected_titles.csv
    └── models.py                 # Database models including pooling tables
```

### Database Tables (Supabase PostgreSQL)

The pooling system adds these tables:
- `user_profiles` - User payment data and Star balances
- `content_pools` - Community pools with dynamic pricing
- `pool_contributions` - Individual user contributions
- `transactions` - Complete payment history

## Deployment Notes

### Separate Servers Setup
1. **Bot Server**: Deploy `telegram_bot/` directory
2. **Shared Data**: 
   - Option A: Use shared network storage (NFS, S3, etc.)
   - Option B: Sync periodically with rsync/cron
   - Option C: Use database for shared state (requires code changes)

### Network Requirements
- Outbound HTTPS to Telegram API
- Outbound HTTP/HTTPS to landing server (if separate)
- Outbound HTTP/HTTPS to scraped websites

### Resource Requirements
- **RAM**: 1GB minimum, 2GB recommended (increased for pooling system)
- **CPU**: 1 core minimum, 2 cores recommended
- **Disk**: 10GB minimum (depends on cache size and database)
- **Network**: 100Mbps recommended
- **Database**: PostgreSQL (Supabase) for pooling system

## Logs

Logs are written to:
- Console (stdout/stderr)
- `logs.txt` (if configured)

View logs:
```bash
# Development
python main_bot.py

# Production (systemd)
sudo journalctl -u freefans-bot -f
```

## Troubleshooting

### Bot not responding
```bash
# Check if bot is running
ps aux | grep bot.py

# Check logs
tail -f logs.txt

# Restart
sudo systemctl restart freefans-bot
```

### Database connection issues
```bash
# Test database connection
python -c "from shared.config.database import init_database; print(init_database())"

# Check environment variables
echo $SUPABASE_DATABASE_URL

# Verify tables exist
python scripts/setup_pools.py
```

### Pooling system issues
```bash
# Check pool statistics
# Use /poolstats command in bot

# Verify database tables
python -c "from shared.data.models import ContentPool; print('Tables OK')"

# Reset pooling system (if needed)
python scripts/setup_pools.py
```

### Import errors
```bash
# Ensure shared directory is accessible
ls -la ../shared/config/
ls -la ../shared/data/

# Check Python path
python -c "import sys; print(sys.path)"
```

### Permission errors
```bash
# Check file permissions
chmod +x bot.py
chown -R your_user:your_group .

# Check data directory permissions
ls -la ../shared/data/
```

## Security

- Keep `.env` file secure (add to `.gitignore`)
- Never commit `TELEGRAM_BOT_TOKEN`
- Limit file permissions: `chmod 600 .env`
- Use HTTPS for landing server communication
- Regularly update dependencies: `pip install -r requirements.txt --upgrade`

## Support

For issues, check:
1. Bot logs
2. Telegram API status
3. Landing server connectivity
4. Shared directory access
