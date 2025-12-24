# Telegram Bot Service

## Overview
This is the Telegram bot component of FreeFans. It handles user interactions, content search, admin/worker management, and communicates with the landing server for content delivery.

## Directory Structure
```
telegram_bot/
├── bot.py                  # Main bot entry point
├── requirements.txt        # Bot-specific dependencies
├── .env                    # Environment variables (bot token, etc.)
├── bot/                    # Bot handlers
├── core/                   # Core business logic
├── managers/               # Data managers
├── scrapers/               # Web scraping
├── utils/                  # Utilities
└── scripts/                # Management scripts
```

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

# Optional: Pre-populate cache
python scripts/manual_cache.py
```

## Running the Bot

### Development
```bash
python bot.py
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
ExecStart=/path/to/telegram_bot/env/bin/python bot.py
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
| `LANDING_BASE_URL` | No | `http://localhost:8001` | Landing server URL |
| `LANDING_SECRET_KEY` | No | `your-secret-key` | Secret key for landing server auth |
| `LANDING_ENABLED` | No | `true` | Enable/disable landing pages |

## Management Scripts

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
│   └── permissions_config.json
└── data/
    ├── onlyfans_models.csv
    ├── requests/
    │   ├── creator_requests.csv
    │   └── content_requests.csv
    └── title_submissions/
        ├── pending_titles.csv
        ├── approved_titles.csv
        └── rejected_titles.csv
```

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
- **RAM**: 512MB minimum, 1GB recommended
- **CPU**: 1 core minimum
- **Disk**: 5GB minimum (depends on cache size)
- **Network**: 100Mbps recommended

## Logs

Logs are written to:
- Console (stdout/stderr)
- `logs.txt` (if configured)

View logs:
```bash
# Development
python bot.py

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
