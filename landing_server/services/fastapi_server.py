"""
FastAPI Landing Page Server
Serves landing pages with content previews and ads before redirecting to original content
"""

import os
import hashlib
import base64
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import quote, unquote
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from decouple import config

app = FastAPI(title="FreeFans Landing Server", version="1.0.0")

# Get base directory for templates and static files
BASE_DIR = Path(__file__).parent.parent

# In-memory storage for short URLs (in production, use Redis or database)
url_storage: Dict[str, Dict[str, Any]] = {}

# Add CORS middleware for Cloudflare tunnel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize templates and static files with absolute paths
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Secret key for URL signing (should be in .env)
SECRET_KEY = config('LANDING_SECRET_KEY', default='your-secret-key-change-this')

def generate_short_id(length: int = 8) -> str:
    """Generate a short random ID for URLs"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class ContentLink(BaseModel):
    """Model for content link data"""
    creator_name: str
    content_title: str
    content_type: str
    original_url: str
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    expires_at: datetime
    short_id: Optional[str] = None  # Allow bot to provide its own short_id

def generate_signed_url(content_data: Dict[str, Any], expires_hours: int = 24) -> str:
    """Generate a short signed URL for content access"""
    # Create expiration timestamp
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    
    # Generate a short unique ID
    short_id = generate_short_id(8)
    
    # Store the content data with the short ID
    url_storage[short_id] = {
        'creator': content_data['creator_name'],
        'title': content_data['content_title'],
        'type': content_data['content_type'],
        'url': content_data['original_url'],
        'preview': content_data.get('preview_url'),
        'thumbnail': content_data.get('thumbnail_url'),
        'expires': expires_at.isoformat()
    }
    
    return f"/c/{short_id}"

def verify_short_url(short_id: str) -> Optional[Dict[str, Any]]:
    """Verify and retrieve data for a short URL"""
    try:
        # Get data from storage
        data_dict = url_storage.get(short_id)
        if not data_dict:
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(data_dict['expires'])
        if datetime.now() > expires_at:
            # Clean up expired link
            del url_storage[short_id]
            return None
        
        return data_dict
        
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/c/{short_id}", response_class=HTMLResponse)
async def content_landing(
    request: Request,
    short_id: str
):
    """Content landing page with preview - now with short URLs"""
    
    # Verify the short URL and get content data
    content_data = verify_short_url(short_id)
    if not content_data:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    
    # Extract content information
    creator_name = content_data['creator']
    content_title = content_data['title']
    content_type = content_data['type']
    original_url = content_data['url']
    preview_url = content_data.get('preview')
    thumbnail_url = content_data.get('thumbnail')
    
    # Determine content category for styling
    is_video = 'video' in content_type.lower() or '🎬' in content_type
    is_photo = 'photo' in content_type.lower() or '📷' in content_type or '🖼️' in content_type
    
    # Use preview or thumbnail for Open Graph
    og_image = preview_url or thumbnail_url or ""
    
    return templates.TemplateResponse("content_landing.html", {
        "request": request,
        "creator_name": creator_name,
        "content_title": content_title,
        "content_type": content_type,
        "is_video": is_video,
        "is_photo": is_photo,
        "preview_url": preview_url,
        "thumbnail_url": thumbnail_url,
        "original_url": original_url,
        "og_image": og_image,
        "og_title": f"{content_title} - {creator_name}",
        "og_description": f"View {content_type} from {creator_name}"
    })

# Keep old endpoint for backward compatibility
@app.get("/content/{encoded_data}/{signature}", response_class=HTMLResponse)
async def content_landing_legacy(
    request: Request,
    encoded_data: str,
    signature: str
):
    """Legacy content landing page - redirects to home"""
    raise HTTPException(status_code=404, detail="This link format is deprecated. Please request a new link.")

@app.get("/access/{encoded_data}/{signature}")
async def access_content(encoded_data: str, signature: str):
    """Legacy access endpoint - deprecated"""
    raise HTTPException(status_code=404, detail="This link format is deprecated.")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "stored_urls": len(url_storage)
    }

# API endpoint for the bot to generate landing page URLs
@app.post("/api/generate-link")
async def generate_landing_link(content_data: ContentLink):
    """Generate a landing page URL for content"""
    
    # Use provided short_id or generate a new one
    short_id = content_data.short_id or generate_short_id(8)
    
    # Calculate expiration
    if isinstance(content_data.expires_at, str):
        expires_at = datetime.fromisoformat(content_data.expires_at)
    else:
        expires_at = content_data.expires_at
    
    # Store the content data with the short ID
    url_storage[short_id] = {
        'creator': content_data.creator_name,
        'title': content_data.content_title,
        'type': content_data.content_type,
        'url': content_data.original_url,
        'preview': content_data.preview_url,
        'thumbnail': content_data.thumbnail_url,
        'expires': expires_at.isoformat()
    }
    
    # Return full URL
    base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
    full_url = f"{base_url}/c/{short_id}"
    
    return {
        "landing_url": full_url,
        "short_id": short_id,
        "expires_at": expires_at.isoformat()
    }

if __name__ == "__main__":
    # Get configuration
    host = config('LANDING_HOST', default='0.0.0.0')
    port = int(config('LANDING_PORT', default=8001))
    
    print(f"🚀 Starting FastAPI Landing Server on {host}:{port}")
    print(f"📄 Landing pages will be served at http://{host}:{port}")
    
    uvicorn.run(app, host=host, port=port)