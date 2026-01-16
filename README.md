# FreeFans - Multi-Server Architecture

## Overview
FreeFans is a Telegram bot for accessing creator content with a separate landing page server. The application is split into two independently deployable services:

1. **Telegram Bot** - Handles user interactions, content search, admin/worker management
2. **Landing Server** - Serves landing pages for content links with previews

## Project Structure


```
FreeFans/
├── telegram_bot/          # Telegram bot application
│   ├── bot.py            # Main bot entry point
│   ├── bot/              # Bot handlers
│   ├── core/             # Core business logic
│   ├── managers/         # Data managers
│   ├── scrapers/         # Web scraping
│   ├── utils/            # Utilities
│   ├── scripts/          # Management scripts
│   ├── requirements.txt  # Bot dependencies
│   ├── .env             # Bot configuration
│   └── README.md        # Bot documentation
│
├── landing_server/       # Landing page server
│   ├── services/        # FastAPI application
│   ├── static/          # CSS, JS, images
│   ├── templates/       # HTML templates
│   ├── requirements.txt # Server dependencies
│   ├── .env            # Server configuration
│   └── README.md       # Server documentation
│
└── shared/              # Shared resources
    ├── config/          # Configuration files
    │   ├── curl_config.txt
    │   ├── content_domains.txt
    │   ├── video_domains.txt
    │   └── permissions_config.json
    └── data/            # CSV data files
        ├── onlyfans_models.csv
        ├── requests/
        │   ├── creator_requests.csv
        │   └── content_requests.csv
        └── title_submissions/
            ├── pending_titles.csv
            ├── approved_titles.csv
            └── rejected_titles.csv
```

## 🗄️ Storage Architecture

The project uses **Supabase (PostgreSQL)** for all data storage:

- **Creator Content Cache**: Stores scraped content metadata
- **OnlyFans Posts**: Caches OnlyFans feed data  
- **User Permissions**: Admin and worker user management
- **Landing Page Data**: Short URL mappings
- **Scraper Checkpoints**: Progress tracking for scrapers

### Key Benefits
- ☁️ **Cloud-native**: No local database files
- 🔄 **Real-time sync**: Instant data consistency
- 📈 **Scalable**: PostgreSQL performance
- 🔒 **Secure**: Supabase authentication and RLS
```

## Deployment Architectures

### Architecture 1: Single Server (Development/Small Scale)
```
┌─────────────────────────────┐
│     Single Server           │
│                             │
│  ┌────────────────────┐    │
│  │  Telegram Bot      │    │
│  │  Port: -           │    │
│  └────────┬───────────┘    │
│           │                 │
│  ┌────────▼───────────┐    │
│  │  Landing Server    │    │
│  │  Port: 8001        │    │
│  └────────────────────┘    │
│           │                 │
│  ┌────────▼───────────┐    │
│  │  Supabase DB       │    │
│  │  (Cloud)           │    │
│  └────────────────────┘    │
└─────────────────────────────┘
```

**Setup:**
```bash
# Clone repo
git clone <repo-url> FreeFans
cd FreeFans

# Setup bot
cd telegram_bot
python -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your tokens

# Setup landing server (new terminal)
cd ../landing_server
python -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with server config

# Run both services
# Terminal 1:
cd telegram_bot && python bot.py

# Terminal 2:
cd landing_server && uvicorn services.fastapi_server:app --host 0.0.0.0 --port 8001
```

### Architecture 2: Separate Servers (Production/High Availability)
```
┌──────────────────┐         ┌──────────────────┐
│  Bot Server      │         │  Landing Server  │
│                  │         │                  │
│  Telegram Bot    │         │  FastAPI + Nginx │
│  Port: -         │◄────────┤  Port: 443/HTTPS │
│                  │  HTTP   │  (Public)        │
└────────┬─────────┘         └──────────────────┘
         │                            ▲
         │                            │
         │                     Telegram Servers
         │                     (Link Previews)
         │
         ▼
┌──────────────────┐
│  Supabase DB     │
│  (Cloud)         │
│  PostgreSQL      │
└──────────────────┘
```

**Bot Server Setup:**
```bash
# On bot server
git clone <repo-url> FreeFans
cd FreeFans/telegram_bot

python -m venv env
source env/bin/activate
pip install -r requirements.txt

# Configure for remote landing server and Supabase
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token
LANDING_BASE_URL=https://landing.yourdomain.com
LANDING_SECRET_KEY=shared_secret_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
EOF

# Run bot
python bot.py
python bot.py
```

**Landing Server Setup:**
```bash
# On landing server
git clone <repo-url> FreeFans
cd FreeFans/landing_server

python -m venv env
source env/bin/activate
pip install -r requirements.txt

# Configure
cat > .env << EOF
LANDING_HOST=0.0.0.0
LANDING_PORT=8001
LANDING_BASE_URL=https://landing.yourdomain.com
LANDING_SECRET_KEY=shared_secret_key
EOF

# Setup Nginx reverse proxy
sudo apt install nginx certbot python3-certbot-nginx

# Configure Nginx (see landing_server/README.md)
# Setup SSL with Let's Encrypt
sudo certbot --nginx -d landing.yourdomain.com

# Run server
uvicorn services.fastapi_server:app --host 0.0.0.0 --port 8001 --workers 4
```

### Architecture 3: Cloud/Docker (Scalable)
```
┌────────────────────────────────────┐
│         Load Balancer              │
│         (Nginx / Cloud LB)         │
└──────┬────────────────────┬────────┘
       │                    │
┌──────▼──────┐      ┌──────▼──────┐
│  Bot Pod 1  │      │  Landing 1  │
│  (Docker)   │      │  (Docker)   │
└──────┬──────┘      └──────┬──────┘
       │                    │
┌──────▼──────┐      ┌──────▼──────┐
│  Bot Pod 2  │      │  Landing 2  │
│  (Docker)   │      │  (Docker)   │
└──────┬──────┘      └──────┬──────┘
       │                    │
       └──────┬─────────────┘
              │
        ┌─────▼──────┐
        │  Redis     │
        │  Database  │
        │  S3        │
        └────────────┘
```

*Docker setup guide coming soon*

## Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- Telegram Bot Token (get from @BotFather)
- Domain name (for landing server if deploying separately)

### 2. Environment Configuration

**Telegram Bot (.env):**
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
LANDING_BASE_URL=http://localhost:8001  # Or your landing server URL
LANDING_SECRET_KEY=change-this-secret-key
LANDING_ENABLED=true
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
```

**Landing Server (.env):**
```env
LANDING_HOST=0.0.0.0
LANDING_PORT=8001
LANDING_BASE_URL=http://localhost:8001  # Or your public domain
LANDING_SECRET_KEY=change-this-secret-key
LANDING_ENABLED=true
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
```

### 3. Initialize Supabase Database

```bash
cd telegram_bot

# Initialize Supabase database schema
python ../scripts/init_supabase.py
```

### 4. Initialize Data

```bash
cd telegram_bot

# Add yourself as admin
python scripts/manage_permissions.py add-admin YOUR_TELEGRAM_USER_ID
```

### 5. Start Services

**Development (same server):**
```bash
# Terminal 1: Bot
cd telegram_bot
source env/bin/activate
python bot.py

# Terminal 2: Landing Server
cd landing_server
source env/bin/activate
uvicorn services.fastapi_server:app --reload
```

**Production (systemd):**
```bash
# See telegram_bot/README.md and landing_server/README.md
# for systemd service configurations
```

## Features

### User Features
- 🔍 Creator search with fuzzy matching
- 📁 Content browsing (images & videos)
- 🌐 Social links display
- 📱 Mobile-friendly interface
- ⏰ Request new creators/content

### Admin Features
- 👥 User request management (`/requests`)
- ✅ Title approval system (`/titles`, `/approve`, `/reject`)
- 📊 System statistics (`/adminstats`)
- 👷 Worker management
- 🔄 Bulk operations

### Worker Features
- 📝 Submit video titles by replying
- 📈 View submission stats (`/mystats`)
- ✍️ Title submission guidelines

## Management

### Add Admins/Workers
```bash
cd telegram_bot
python scripts/manage_permissions.py add-admin <telegram_user_id>
python scripts/manage_permissions.py add-worker <telegram_user_id>
```

### Get User ID
Users can send `/myid` to the bot (if implemented) or use @userinfobot on Telegram.

### View Requests
```bash
# Via bot
/requests  # View pending user requests
/titles    # View pending title submissions

# Via CSV
cat shared/data/requests/creator_requests.csv
cat shared/data/title_submissions/pending_titles.csv
```

## Security Checklist

- [ ] Change default `LANDING_SECRET_KEY`
- [ ] Never commit `.env` files
- [ ] Use HTTPS for landing server
- [ ] Keep `permissions_config.json` secure
- [ ] Regularly update dependencies
- [ ] Use firewall to restrict access
- [ ] Enable rate limiting on landing server
- [ ] Regular backups of `shared/data/`

## Monitoring

### Bot Health
```bash
# Check if running
ps aux | grep bot.py

# View logs
tail -f telegram_bot/logs.txt

# Systemd
sudo systemctl status freefans-bot
sudo journalctl -u freefans-bot -f
```

### Landing Server Health
```bash
# Check endpoint
curl http://localhost:8001/

# View logs
sudo journalctl -u freefans-landing -f

# Check Nginx (if used)
sudo nginx -t
sudo systemctl status nginx
```

## Backup Strategy

### Critical Data
```bash
# Backup shared directory
tar -czf backup-$(date +%Y%m%d).tar.gz shared/

# Automated daily backup (cron)
0 2 * * * tar -czf /backups/freefans-$(date +\%Y\%m\%d).tar.gz /path/to/FreeFans/shared/
```

### Database
```bash
# Supabase backup (via Supabase Dashboard)
# 1. Go to your Supabase project dashboard
# 2. Navigate to Settings > Database
# 3. Use the backup/restore functionality
# 4. Or use pg_dump for manual backups:

pg_dump "postgresql://user:pass@host:port/dbname" > backup.sql
```

## Troubleshooting

### Bot not responding
1. Check bot is running: `ps aux | grep bot.py`
2. Check Telegram API status
3. Verify `TELEGRAM_BOT_TOKEN`
4. Check logs for errors

### Landing pages returning 404
1. Check landing server is running
2. Verify `LANDING_BASE_URL` matches actual URL
3. Check URL expiration (24 hours default)
4. Verify network connectivity between bot and server

### Import/Module errors
1. Ensure virtual environment is activated
2. Install dependencies: `pip install -r requirements.txt`
3. Check Python version: `python --version` (3.10+ required)
4. Verify shared directory is accessible

## Development

### Project Structure
- See `telegram_bot/README.md` for bot architecture
- See `landing_server/README.md` for server architecture

### Adding Features
1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

## License

[Your License Here]

## Support

- Documentation: See README files in each service directory
- Issues: [GitHub Issues]
- Contact: [Your Contact Info]
