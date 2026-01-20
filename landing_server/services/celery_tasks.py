"""
Celery tasks for background processing
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from decouple import config

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def cache_and_store_task(self, short_id: str, content_data: dict, expires_at: str, preview_url: Optional[str] = None):
    """
    Background task to cache preview image and store in Supabase.
    
    Args:
        short_id: Short ID for the landing page
        content_data: Content data dictionary
        expires_at: Expiration timestamp (ISO format)
        preview_url: Preview URL to cache (if any)
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"📦 Celery: Processing task for {short_id}")
        
        preview_url_to_store = preview_url
        
        # Cache the preview image if we have one for videos
        if content_data.get('content_type') and '🎬' in content_data['content_type'] and preview_url_to_store:
            try:
                logger.info(f"💾 Celery: Caching preview image for {short_id}")
                cache_start = time.time()
                
                # Import here to avoid circular imports
                from services.image_cache_service import video_preview_cache_service
                
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    cached_path = loop.run_until_complete(
                        asyncio.wait_for(
                            video_preview_cache_service.cache_video_preview(preview_url_to_store),
                            timeout=15.0
                        )
                    )
                    cache_time = time.time() - cache_start
                    
                    if cached_path:
                        # Update preview URL to use cached version
                        base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
                        preview_url_to_store = f"{base_url}{cached_path}"
                        logger.info(f"✅ Celery: Cached preview in {cache_time:.2f}s for {short_id}")
                    else:
                        logger.info(f"ℹ️ Celery: Preview already cached in {cache_time:.2f}s for {short_id}")
                finally:
                    loop.close()
                    
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Celery: Timeout caching preview for {short_id}")
            except Exception as e:
                logger.error(f"❌ Celery: Failed to cache preview for {short_id}: {e}")
        
        # Store in Supabase
        try:
            from shared.config.database import get_db_session_sync, init_database, create_tables
            from shared.data import crud
            
            if init_database() and create_tables():
                db = get_db_session_sync()
                try:
                    expires_dt = datetime.fromisoformat(expires_at)
                    crud.upsert_landing_page(
                        db=db,
                        short_id=short_id,
                        creator=content_data.get('creator_name', 'Unknown'),
                        title=content_data.get('content_title', 'Untitled'),
                        content_type=content_data.get('content_type', ''),
                        original_url=content_data.get('original_url', ''),
                        preview_url=preview_url_to_store,
                        thumbnail_url=content_data.get('thumbnail_url'),
                        expires_at=expires_dt
                    )
                    total_time = time.time() - start_time
                    logger.info(f"✅ Celery: Stored {short_id} in Supabase (total: {total_time:.2f}s)")
                finally:
                    db.close()
            else:
                logger.error(f"❌ Celery: Database not available for {short_id}")
                # Retry the task
                raise self.retry(exc=Exception("Database not available"))
                
        except Exception as e:
            logger.error(f"❌ Celery: Failed to store {short_id} in Supabase: {e}")
            # Retry the task (up to max_retries)
            raise self.retry(exc=e)
            
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"❌ Celery: Task failed for {short_id} after {total_time:.2f}s: {e}")
        # Don't retry on unknown errors after max retries
        if self.request.retries >= self.max_retries:
            logger.error(f"❌ Celery: Max retries reached for {short_id}, giving up")
        else:
            raise
