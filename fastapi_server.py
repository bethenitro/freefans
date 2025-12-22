"""
FastAPI Landing Page Server
Serves landing pages with content previews and ads before redirecting to original content
"""

import os
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import quote, unquote

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from decouple import config

from cache_manager import CacheManager

app = FastAPI(title="FreeFans Landing Server", version="1.0.0")

# Add CORS middleware for Cloudflare tunnel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize cache manager for content lookup
cache_manager = CacheManager()

# Secret key for URL signing (should be in .env)
SECRET_KEY = config('LANDING_SECRET_KEY', default='your-secret-key-change-this')

class ContentLink(BaseModel):
    """Model for content link data"""
    creator_name: str
    content_title: str
    content_type: str
    original_url: str
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    expires_at: datetime

def generate_signed_url(content_data: Dict[str, Any], expires_hours: int = 24) -> str:
    """Generate a signed URL for content access"""
    # Create expiration timestamp
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    
    # Prepare data to sign
    data_to_sign = {
        'creator': content_data['creator_name'],
        'title': content_data['content_title'],
        'type': content_data['content_type'],
        'url': content_data['original_url'],
        'preview': content_data.get('preview_url'),
        'thumbnail': content_data.get('thumbnail_url'),
        'expires': expires_at.isoformat()
    }
    
    # Convert to string and encode
    data_string = str(sorted(data_to_sign.items()))
    signature = hashlib.sha256(f"{data_string}{SECRET_KEY}".encode()).hexdigest()
    
    # Encode the data
    encoded_data = base64.urlsafe_b64encode(str(data_to_sign).encode()).decode()
    
    return f"/content/{encoded_data}/{signature}"

def verify_signed_url(encoded_data: str, signature: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a signed URL"""
    try:
        # Decode the data
        decoded_data = base64.urlsafe_b64decode(encoded_data.encode()).decode()
        data_dict = eval(decoded_data)  # Note: In production, use json.loads with proper encoding
        
        # Verify signature
        data_string = str(sorted(data_dict.items()))
        expected_signature = hashlib.sha256(f"{data_string}{SECRET_KEY}".encode()).hexdigest()
        
        if signature != expected_signature:
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(data_dict['expires'])
        if datetime.now() > expires_at:
            return None
        
        return data_dict
        
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/content/{encoded_data}/{signature}", response_class=HTMLResponse)
async def content_landing(
    request: Request,
    encoded_data: str,
    signature: str
):
    """Content landing page with preview and ads"""
    
    # Verify the signed URL
    content_data = verify_signed_url(encoded_data, signature)
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
    
    # Generate access URL (another signed URL for the redirect)
    access_data = {
        'url': original_url,
        'accessed_at': datetime.now().isoformat()
    }
    access_string = str(sorted(access_data.items()))
    access_signature = hashlib.sha256(f"{access_string}{SECRET_KEY}".encode()).hexdigest()
    access_encoded = base64.urlsafe_b64encode(str(access_data).encode()).decode()
    access_url = f"/access/{access_encoded}/{access_signature}"
    
    return templates.TemplateResponse("content_landing.html", {
        "request": request,
        "creator_name": creator_name,
        "content_title": content_title,
        "content_type": content_type,
        "is_video": is_video,
        "is_photo": is_photo,
        "preview_url": preview_url,
        "thumbnail_url": thumbnail_url,
        "access_url": access_url,
        "original_domain": original_url.split('/')[2] if '://' in original_url else 'Unknown'
    })

@app.get("/access/{encoded_data}/{signature}")
async def access_content(encoded_data: str, signature: str):
    """Redirect to original content after showing landing page"""
    
    try:
        # Decode and verify access data
        decoded_data = base64.urlsafe_b64decode(encoded_data.encode()).decode()
        access_data = eval(decoded_data)  # Note: In production, use json.loads
        
        # Verify signature
        access_string = str(sorted(access_data.items()))
        expected_signature = hashlib.sha256(f"{access_string}{SECRET_KEY}".encode()).hexdigest()
        
        if signature != expected_signature:
            raise HTTPException(status_code=404, detail="Invalid access link")
        
        original_url = access_data['url']
        
        # Log the access (optional)
        print(f"Content accessed: {original_url} at {access_data['accessed_at']}")
        
        # Redirect to original content
        return RedirectResponse(url=original_url, status_code=302)
        
    except Exception as e:
        raise HTTPException(status_code=404, detail="Invalid access link")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# API endpoint for the bot to generate landing page URLs
@app.post("/api/generate-link")
async def generate_landing_link(content_data: ContentLink):
    """Generate a landing page URL for content"""
    
    # Convert Pydantic model to dict
    data_dict = {
        'creator_name': content_data.creator_name,
        'content_title': content_data.content_title,
        'content_type': content_data.content_type,
        'original_url': content_data.original_url,
        'preview_url': content_data.preview_url,
        'thumbnail_url': content_data.thumbnail_url
    }
    
    # Generate signed URL
    signed_url = generate_signed_url(data_dict)
    
    # Return full URL (you'll need to configure your domain)
    base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
    full_url = f"{base_url}{signed_url}"
    
    return {
        "landing_url": full_url,
        "expires_at": content_data.expires_at.isoformat()
    }

if __name__ == "__main__":
    # Get configuration
    host = config('LANDING_HOST', default='0.0.0.0')
    port = int(config('LANDING_PORT', default=8001))
    
    print(f"🚀 Starting FastAPI Landing Server on {host}:{port}")
    print(f"📄 Landing pages will be served at http://{host}:{port}")
    
    uvicorn.run(app, host=host, port=port)