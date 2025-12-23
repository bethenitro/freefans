# Landing Server Service

## Overview
This is the FastAPI landing page server for FreeFans. It generates and serves landing pages for content links, allowing for better link previews and access control.

## Directory Structure
```
landing_server/
├── services/
│   ├── fastapi_server.py   # Main FastAPI application
│   └── landing_service.py  # Landing page generation logic
├── static/
│   └── style.css           # CSS styling
├── templates/
│   ├── base.html
│   ├── content_landing.html
│   └── home.html
├── requirements.txt        # Server-specific dependencies
└── .env                    # Environment variables
```

## Setup

### 1. Install Dependencies
```bash
cd landing_server
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create/edit `.env` file:
```env
# Server Configuration
LANDING_HOST=0.0.0.0
LANDING_PORT=8001
LANDING_BASE_URL=https://your-domain.com
LANDING_SECRET_KEY=your-secret-key-change-this

# Optional
LANDING_ENABLED=true
```

## Running the Server

### Development
```bash
# Using uvicorn directly
uvicorn services.fastapi_server:app --host 0.0.0.0 --port 8001 --reload

# Or using Python
python services/fastapi_server.py
```

### Production (with systemd)
Create `/etc/systemd/system/freefans-landing.service`:
```ini
[Unit]
Description=FreeFans Landing Server
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/landing_server
Environment="PATH=/path/to/landing_server/env/bin"
ExecStart=/path/to/landing_server/env/bin/uvicorn services.fastapi_server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable freefans-landing
sudo systemctl start freefans-landing
sudo systemctl status freefans-landing
```

### Production (with Nginx reverse proxy)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /path/to/landing_server/static;
    }
}
```

With SSL (recommended):
```bash
# Using certbot
sudo certbot --nginx -d your-domain.com
```

## API Endpoints

### POST `/api/generate-link`
Generate a landing page URL for content.

**Request:**
```json
{
  "creator_name": "Creator Name",
  "content_title": "Video Title",
  "content_type": "🎬 Video",
  "original_url": "https://original-content-url.com",
  "preview_url": "https://preview-image.com/preview.jpg",
  "thumbnail_url": "https://thumbnail.com/thumb.jpg",
  "expires_at": "2025-12-24T00:00:00",
  "short_id": "abc123xy"
}
```

**Response:**
```json
{
  "landing_url": "https://your-domain.com/c/abc123xy",
  "short_id": "abc123xy",
  "expires_at": "2025-12-24T00:00:00"
}
```

### GET `/c/{short_id}`
Access landing page for content.

Returns HTML landing page with:
- Content preview
- Creator information
- Access button to original URL
- Expiration information

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANDING_HOST` | No | `0.0.0.0` | Server bind address |
| `LANDING_PORT` | No | `8001` | Server port |
| `LANDING_BASE_URL` | Yes | - | Public URL of server |
| `LANDING_SECRET_KEY` | Yes | - | Secret key for security |
| `LANDING_ENABLED` | No | `true` | Enable/disable landing pages |

## Deployment Notes

### Separate Servers Setup
1. **Deploy Server**: Copy `landing_server/` to your server
2. **Configure Domain**: Point your domain to server IP
3. **Setup Nginx**: Use reverse proxy for SSL termination
4. **Update Bot Config**: Set `LANDING_BASE_URL` in bot's `.env`

### Using Cloudflare Tunnel (Free SSL & Public Access)
```bash
# Install cloudflared
# https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/

# Run tunnel
cloudflared tunnel --url http://localhost:8001

# Get public URL (e.g., https://random-name.trycloudflare.com)
# Update LANDING_BASE_URL in .env with this URL
```

### Network Requirements
- Inbound HTTP/HTTPS (80/443)
- Must be accessible from Telegram servers (for link previews)
- Must be accessible from bot server

### Resource Requirements
- **RAM**: 256MB minimum, 512MB recommended
- **CPU**: 1 core minimum
- **Disk**: 1GB minimum
- **Network**: 100Mbps recommended

## Performance

### Caching
Landing URLs are cached in memory for quick access:
```python
# Automatic expiration after 24 hours (configurable)
# LRU cache for frequent URLs
```

### Optimization
- Use CDN for static assets
- Enable gzip compression in Nginx
- Use connection pooling
- Implement rate limiting if needed

## Monitoring

### Health Check
```bash
curl http://localhost:8001/
# Should return: {"status": "active", ...}
```

### Logs
```bash
# Development
uvicorn services.fastapi_server:app --log-level info

# Production (systemd)
sudo journalctl -u freefans-landing -f

# Access logs (Nginx)
tail -f /var/log/nginx/access.log
```

## Security

### Best Practices
1. **Use HTTPS**: Always use SSL in production
2. **Rate Limiting**: Implement rate limiting in Nginx
3. **CORS**: Configure CORS if needed
4. **Secret Key**: Use strong random secret key
5. **Firewall**: Only allow necessary ports

### Example Nginx Security Headers
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
```

## Troubleshooting

### Server won't start
```bash
# Check if port is in use
sudo lsof -i :8001

# Check logs
sudo journalctl -u freefans-landing -n 50

# Test configuration
uvicorn services.fastapi_server:app --host 127.0.0.1 --port 8001
```

### 404 errors for landing pages
```bash
# Check if short_id exists in memory
# Landing URLs expire after 24 hours
# Telegram may be caching 404 responses

# Check server logs for requests
tail -f /var/log/nginx/access.log | grep "/c/"
```

### Bot can't reach server
```bash
# Test from bot server
curl https://your-domain.com/

# Check firewall
sudo ufw status

# Check DNS
nslookup your-domain.com
```

## Scaling

### Horizontal Scaling
- Use load balancer (Nginx, HAProxy)
- Share URL cache via Redis
- Use database for persistence

### Vertical Scaling
- Increase workers: `--workers 4`
- Optimize static file serving
- Use CDN for assets

## Support

For issues, check:
1. Server logs
2. Nginx logs (if using)
3. Network connectivity
4. SSL certificate validity
