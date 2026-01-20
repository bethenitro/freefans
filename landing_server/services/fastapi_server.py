"""
FastAPI Landing Page Server
Serves landing pages with content previews and ads before redirecting to original content
"""

import os
import hashlib
import base64
import secrets
import string
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
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

# Add project root to path for shared imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import video preview extractor
from services.video_preview_extractor import video_preview_extractor

# Initialize logger with timestamp format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="FreeFans Landing Server", version="1.0.0")

# Get base directory for templates and static files
BASE_DIR = Path(__file__).parent.parent

# In-memory storage for short URLs (in production, use Redis or database)
url_storage: Dict[str, Dict[str, Any]] = {}

# Global DB availability flag (set during startup)
db_initialized = False

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

@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool on startup (no preloading for scalability)"""
    global db_initialized
    try:
        from shared.config.database import init_database, create_tables
        
        # Initialize database connection pool only
        if not init_database():
            print("⚠️ Database initialization failed - landing server will work with new pages only")
            db_initialized = False
            return
        
        if not create_tables():
            print("⚠️ Database table creation failed - landing server will work with new pages only")
            db_initialized = False
            return
        
        db_initialized = True
        print("✅ Database connection pool ready - using on-demand queries (no preloading)")
        
    except Exception as e:
        print(f"⚠️ Startup error: {e}")
        db_initialized = False

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    try:
        from services.image_cache_service import video_preview_cache_service
        await video_preview_cache_service.stop()
        print("✅ Video preview cache service stopped")
    except Exception as e:
        print(f"⚠️ Error during shutdown: {e}")
    
    # Close video preview extractor
    try:
        await video_preview_extractor.close()
        print("✅ Video preview extractor closed")
    except Exception as e:
        print(f"⚠️ Error closing video preview extractor: {e}")
    
    print("✅ Landing server shutdown complete")

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
        # First check in-memory storage
        data_dict = url_storage.get(short_id)
        if data_dict:
            # Check expiration
            expires_at = datetime.fromisoformat(data_dict['expires'])
            if datetime.now() > expires_at:
                # Clean up expired link
                del url_storage[short_id]
                return None
            return data_dict
        
        # If not in memory, try to load from Supabase
        try:
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                landing_page = crud.get_landing_page(db, short_id)
                if landing_page and landing_page.expires_at > datetime.utcnow():
                    # Load into memory for faster future access
                    data_dict = {
                        'creator': landing_page.creator,
                        'title': landing_page.title,
                        'type': landing_page.content_type,
                        'url': landing_page.original_url,
                        'preview': landing_page.preview_url,
                        'thumbnail': landing_page.thumbnail_url,
                        'expires': landing_page.expires_at.isoformat()
                    }
                    url_storage[short_id] = data_dict
                    return data_dict
            finally:
                db.close()
        except Exception as e:
            print(f"Failed to load from Supabase: {e}")
        
        return None
        
    except Exception as e:
        print(f"Error in verify_short_url: {e}")
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
    """Health check endpoint with detailed status"""
    try:
        from shared.config.database import get_db_session_sync
        from shared.data import crud
        
        # Check database connection
        db_status = "unknown"
        landing_pages_count = 0
        try:
            db = get_db_session_sync()
            try:
                # Try a simple query
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                recent_pages = crud.get_recent_landing_pages(db, cutoff_time)
                landing_pages_count = len(recent_pages)
                db_status = "connected"
            finally:
                db.close()
        except Exception as e:
            db_status = f"error: {str(e)[:50]}"
        
        return {
            "status": "healthy", 
            "timestamp": datetime.now().isoformat(),
            "stored_urls_memory": len(url_storage),
            "stored_urls_db": landing_pages_count,
            "database_status": db_status,
            "base_url": config('LANDING_BASE_URL', default='http://localhost:8001')
        }
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "stored_urls_memory": len(url_storage)
        }

# API endpoint for the bot to generate landing page URLs with preview extraction
@app.post("/api/generate-link")
async def generate_landing_link(content_data: ContentLink):
    """Generate a landing page URL for content with automatic preview extraction and caching"""
    import time
    start_time = time.time()
    
    # Use provided short_id or generate a new one
    short_id = content_data.short_id or generate_short_id(8)
    
    logger.info(f"🔗 Generating landing link for: {content_data.content_title} (type: {content_data.content_type})")
    
    # Calculate expiration
    if isinstance(content_data.expires_at, str):
        expires_at = datetime.fromisoformat(content_data.expires_at)
    else:
        expires_at = content_data.expires_at
    
    preview_url_to_use = content_data.preview_url
    
    # For videos, check cache and extract preview if needed BEFORE responding
    if content_data.content_type and '🎬' in content_data.content_type and not preview_url_to_use:
        try:
            # First check if we have a cached preview in Supabase
            from shared.config.database import get_db_session_sync, init_database, create_tables
            from shared.data import crud
            
            cached_preview = None
            if init_database() and create_tables():
                db = get_db_session_sync()
                try:
                    from shared.data.models import LandingPage
                    # Look for existing landing page with this video URL and cached preview
                    existing = db.query(LandingPage).filter(
                        LandingPage.original_url == content_data.original_url,
                        LandingPage.preview_url.isnot(None),
                        LandingPage.expires_at > datetime.utcnow()
                    ).order_by(LandingPage.created_at.desc()).first()
                    
                    if existing and existing.preview_url:
                        cached_preview = existing.preview_url
                        logger.info(f"✅ Using cached preview from Supabase for {short_id}")
                finally:
                    db.close()
            
            if cached_preview:
                preview_url_to_use = cached_preview
            else:
                # Extract preview URL asynchronously (parallel with other requests)
                logger.info(f"🔍 Extracting preview for {short_id} (parallel)")
                extract_start = time.time()
                try:
                    # Remove wait_for to allow parallel extraction
                    # The semaphore in video_preview_extractor limits concurrency
                    preview_url_to_use = await video_preview_extractor.extract_preview_async(content_data.original_url)
                    extract_time = time.time() - extract_start
                    if preview_url_to_use:
                        logger.info(f"✅ Extracted preview in {extract_time:.2f}s for {short_id}")
                    else:
                        logger.info(f"ℹ️ No preview found in {extract_time:.2f}s for {short_id}")
                except Exception as e:
                    extract_time = time.time() - extract_start
                    logger.error(f"❌ Failed to extract preview for {short_id} in {extract_time:.2f}s: {e}")
        except Exception as e:
            logger.error(f"❌ Error in preview extraction process for {short_id}: {e}")
    
    # Store the content data with the short ID in memory (immediate)
    url_storage[short_id] = {
        'creator': content_data.creator_name,
        'title': content_data.content_title,
        'type': content_data.content_type,
        'url': content_data.original_url,
        'preview': preview_url_to_use,
        'thumbnail': content_data.thumbnail_url,
        'expires': expires_at.isoformat()
    }
    
    # Return URL immediately with preview
    base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
    full_url = f"{base_url}/c/{short_id}"
    
    # Start background task to cache the preview image and store in Supabase
    asyncio.create_task(_background_cache_and_store(short_id, content_data, expires_at, preview_url_to_use))
    
    elapsed_time = time.time() - start_time
    logger.info(f"✅ Landing link generated in {elapsed_time:.3f}s: {full_url}")
    
    return {
        "landing_url": full_url,
        "short_id": short_id,
        "preview_url": preview_url_to_use,  # Include preview URL in response
        "expires_at": expires_at.isoformat()
    }

async def _background_cache_and_store(short_id: str, content_data: ContentLink, expires_at: datetime, preview_url: Optional[str] = None):
    """Background task to cache preview image and store in Supabase"""
    import time
    bg_start_time = time.time()
    
    try:
        from shared.config.database import get_db_session_sync, init_database, create_tables
        from shared.data import crud
        
        preview_url_to_store = preview_url
        
        # Cache the preview image if we have one for videos
        if content_data.content_type and '🎬' in content_data.content_type and preview_url_to_store:
            try:
                logger.info(f"💾 Background: Caching preview image for {short_id}")
                cache_start = time.time()
                from services.image_cache_service import video_preview_cache_service
                # Use asyncio.wait_for to add timeout protection
                cached_path = await asyncio.wait_for(
                    video_preview_cache_service.cache_video_preview(preview_url_to_store),
                    timeout=15.0  # 15 second timeout for downloading/caching
                )
                cache_time = time.time() - cache_start
                if cached_path:
                    # Update preview URL to use cached version
                    base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
                    preview_url_to_store = f"{base_url}{cached_path}"
                    logger.info(f"✅ Background: Cached preview in {cache_time:.2f}s for {short_id}")
                else:
                    logger.info(f"ℹ️ Background: Preview already cached or failed in {cache_time:.2f}s for {short_id}")
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Background: Timeout caching preview for {short_id}")
            except Exception as e:
                logger.error(f"❌ Background: Failed to cache preview for {short_id}: {e}")
        
        # Store in Supabase with potentially updated preview URL (use global DB flag)
        if db_initialized:
            from shared.config.database import get_db_session_sync
            from shared.data import crud
            
            db = get_db_session_sync()
            try:
                crud.create_landing_page(
                    db=db,
                    short_id=short_id,
                    creator=content_data.creator_name,
                    title=content_data.content_title,
                    content_type=content_data.content_type,
                    original_url=content_data.original_url,
                    preview_url=preview_url_to_store,
                    thumbnail_url=content_data.thumbnail_url,
                    expires_at=expires_at
                )
                total_time = time.time() - bg_start_time
                logger.info(f"✅ Background: Stored {short_id} in Supabase (total: {total_time:.2f}s)")
            finally:
                db.close()
        else:
            logger.warning(f"⚠️ Background: DB not available, skipping Supabase storage for {short_id}")
            
    except Exception as e:
        total_time = time.time() - bg_start_time
        logger.error(f"❌ Background: Task failed for {short_id} after {total_time:.2f}s: {e}")

# Batch endpoint for efficient bulk URL generation with parallel preview extraction
@app.post("/api/generate-batch-links")
async def generate_batch_landing_links(content_items: List[ContentLink]):
    """
    Generate multiple landing page URLs efficiently with parallel preview extraction.
    Handles multiple users concurrently without deadlocks.
    """
    import time
    batch_start = time.time()
    logger.info(f"� Received batch request: Processing {len(content_items)} items")
    
    # Step 1: Prepare all items and generate short IDs
    prepared_items = []
    for content_data in content_items:
        short_id = content_data.short_id or generate_short_id(8)
        
        if isinstance(content_data.expires_at, str):
            expires_at = datetime.fromisoformat(content_data.expires_at)
        else:
            expires_at = content_data.expires_at
        
        prepared_items.append({
            'short_id': short_id,
            'content_data': content_data,
            'expires_at': expires_at
        })
    
    # Step 2: Extract all video previews in parallel (non-blocking for different users)
    # Use global DB availability flag (already initialized at startup)
    from shared.config.database import get_db_session_sync
    from shared.data.models import LandingPage
    
    async def extract_preview_for_item(item: dict) -> dict:
        """Extract preview for a single item if it's a video"""
        content_data = item['content_data']
        preview_url = content_data.preview_url
        
        # Only extract for videos
        if content_data.content_type and '🎬' in content_data.content_type:
            try:
                # Check Supabase cache first (use global DB availability flag)
                cached_preview = None
                if db_initialized:
                    db = get_db_session_sync()
                    try:
                        existing = db.query(LandingPage).filter(
                            LandingPage.original_url == content_data.original_url,
                            LandingPage.preview_url.isnot(None),
                            LandingPage.expires_at > datetime.utcnow()
                        ).order_by(LandingPage.created_at.desc()).first()
                        
                        if existing and existing.preview_url:
                            cached_preview = existing.preview_url
                            logger.debug(f"✅ Cached preview for {item['short_id']}")
                    finally:
                        db.close()
                
                if cached_preview:
                    preview_url = cached_preview
                else:
                    # Extract preview (semaphore ensures no deadlock across users)
                    logger.debug(f"🔍 Extracting preview for {item['short_id']}")
                    preview_url = await video_preview_extractor.extract_preview_async(content_data.original_url)
                    if preview_url:
                        logger.debug(f"✅ Extracted preview for {item['short_id']}")
            except Exception as e:
                logger.error(f"❌ Preview extraction failed for {item['short_id']}: {e}")
        
        return {
            'short_id': item['short_id'],
            'content_data': item['content_data'],
            'expires_at': item['expires_at'],
            'preview_url': preview_url
        }
    
    # Extract all previews in parallel (semaphore in VideoPreviewExtractor prevents overload)
    logger.info(f"🚀 Extracting previews for {len(prepared_items)} items in parallel")
    extract_start = time.time()
    items_with_previews = await asyncio.gather(
        *[extract_preview_for_item(item) for item in prepared_items],
        return_exceptions=True
    )
    extract_time = time.time() - extract_start
    logger.info(f"⏱️ Preview extraction completed in {extract_time:.2f}s")
    
    # Step 3: Store all items in memory and prepare responses
    logger.info(f"💾 Storing {len(items_with_previews)} items in memory")
    store_start = time.time()
    results = []
    base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
    
    for item in items_with_previews:
        # Handle exceptions from gather
        if isinstance(item, Exception):
            logger.error(f"❌ Item processing failed: {item}")
            continue
        
        short_id = item['short_id']
        content_data = item['content_data']
        expires_at = item['expires_at']
        preview_url = item['preview_url']
        
        # Store in memory
        url_storage[short_id] = {
            'creator': content_data.creator_name,
            'title': content_data.content_title,
            'type': content_data.content_type,
            'url': content_data.original_url,
            'preview': preview_url,
            'thumbnail': content_data.thumbnail_url,
            'expires': expires_at.isoformat()
        }
        
        full_url = f"{base_url}/c/{short_id}"
        results.append({
            "landing_url": full_url,
            "short_id": short_id,
            "expires_at": expires_at.isoformat()
        })
    
    store_time = time.time() - store_start
    logger.info(f"⏱️ Memory storage completed in {store_time:.2f}s")
    
    # Step 4: Dispatch background tasks to Celery (only for videos, not images)
    video_items = [item for item in items_with_previews 
                   if not isinstance(item, Exception) 
                   and item['content_data'].content_type 
                   and '🎬' in item['content_data'].content_type]
    
    if video_items:
        logger.info(f"🔄 Dispatching {len(video_items)} video tasks to Celery queue (skipping {len(results) - len(video_items)} images)")
    else:
        logger.info(f"ℹ️ No video tasks to dispatch (all {len(results)} items are images or other content)")
    
    try:
        from services.celery_tasks import cache_and_store_task
        
        for item in video_items:
            # Convert content_data to dict for Celery serialization
            content_dict = {
                'creator_name': item['content_data'].creator_name,
                'content_title': item['content_data'].content_title,
                'content_type': item['content_data'].content_type,
                'original_url': item['content_data'].original_url,
                'thumbnail_url': item['content_data'].thumbnail_url,
            }
            
            # Dispatch task to Celery (async, queued in RabbitMQ)
            cache_and_store_task.delay(
                short_id=item['short_id'],
                content_data=content_dict,
                expires_at=item['expires_at'].isoformat(),
                preview_url=item['preview_url']
            )
        
        if video_items:
            logger.info(f"✅ Dispatched {len(video_items)} video tasks to Celery")
    except Exception as e:
        logger.error(f"❌ Failed to dispatch Celery tasks: {e}")
        # Fallback: tasks will be lost, but API response still works
    
    total_time = time.time() - batch_start
    logger.info(f"✅ Batch completed: {len(results)}/{len(content_items)} items in {total_time:.2f}s")
    
    return {
        "results": results,
        "count": len(results)
    }

# New endpoint for video preview extraction
@app.post("/api/extract-video-preview")
async def extract_video_preview(request: Request):
    """Extract video preview/thumbnail URL from video hosting services
    
    Request body:
        {
            "video_url": "https://bunkr.site/v/video-file-name",
            "creator_name": "Creator Name" (optional),
            "content_title": "Video Title" (optional)
        }
    
    Response:
        {
            "preview_url": "https://...", 
            "cached": false,
            "source": "extracted"
        }
    """
    import time
    start_time = time.time()
    
    try:
        body = await request.json()
        video_url = body.get('video_url')
        creator_name = body.get('creator_name', 'Unknown')
        content_title = body.get('content_title', 'Video')
        
        if not video_url:
            raise HTTPException(status_code=400, detail="video_url is required")
        
        logger.info(f"🎬 Extracting preview for: {content_title} ({video_url[:50]}...)")
        
        # Try to extract preview URL
        preview_url = await video_preview_extractor.extract_preview_async(video_url)
        
        elapsed_time = time.time() - start_time
        
        if not preview_url:
            logger.info(f"ℹ️ No preview found in {elapsed_time:.3f}s")
            return {
                "preview_url": None,
                "cached": False,
                "source": "not_found",
                "message": "No preview image found for this video"
            }
        
        logger.info(f"✅ Preview extracted in {elapsed_time:.3f}s: {preview_url[:50]}...")
        
        # Optionally cache the preview image in background
        asyncio.create_task(_cache_preview_in_background(preview_url))
        
        return {
            "preview_url": preview_url,
            "cached": False,  # Will be cached in background
            "source": "extracted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"❌ Error extracting video preview after {elapsed_time:.3f}s: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract preview: {str(e)}")

async def _cache_preview_in_background(preview_url: str):
    """Background task to cache a video preview image"""
    try:
        from services.image_cache_service import video_preview_cache_service
        cached_path = await video_preview_cache_service.cache_video_preview(preview_url)
        if cached_path:
            logger.info(f"✅ Cached video preview in background: {cached_path}")
    except Exception as e:
        logger.error(f"⚠️ Failed to cache preview in background: {e}")

if __name__ == "__main__":
    # Get configuration
    host = config('LANDING_HOST', default='0.0.0.0')
    port = int(config('LANDING_PORT', default=8001))
    
    print(f"🚀 Starting FastAPI Landing Server on {host}:{port}")
    print(f"📄 Landing pages will be served at http://{host}:{port}")
    print(f"🔗 Base URL configured as: {config('LANDING_BASE_URL', default='http://localhost:8001')}")
    
    uvicorn.run(app, host=host, port=port)