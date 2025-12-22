"""
Bot Utilities - Helper functions for message sending and error handling
"""

import asyncio
import logging
from telegram.error import TimedOut, NetworkError, RetryAfter

logger = logging.getLogger(__name__)


async def send_message_with_retry(send_func, *args, max_retries=3, **kwargs):
    """Send a message with retry logic for network errors."""
    for attempt in range(max_retries):
        try:
            # Clean message text to prevent entity parsing errors
            if args and isinstance(args[0], str):
                # Clean the message text
                cleaned_text = _clean_message_text(args[0])
                args = (cleaned_text,) + args[1:]
            
            return await send_func(*args, **kwargs)
        except TimedOut:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Request timed out, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Request timed out after {max_retries} attempts")
                raise
        except NetworkError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Network error: {e}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Network error after {max_retries} attempts: {e}")
                raise
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(f"Rate limited, waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
            # Don't count rate limit against retry attempts
            continue
        except Exception as e:
            # Handle entity parsing errors specifically
            if "can't parse entities" in str(e).lower():
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Entity parsing error: {e}, retrying with cleaned text in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    # Try with parse_mode=None to disable parsing
                    kwargs['parse_mode'] = None
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Entity parsing error after {max_retries} attempts: {e}")
                    raise
            else:
                raise


def _clean_message_text(text: str) -> str:
    """Clean message text to prevent entity parsing errors."""
    if not text:
        return text
    
    # Remove or escape problematic characters that can cause entity parsing errors
    import re
    
    # Remove any malformed HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    
    # Clean up multiple spaces (but preserve single spaces)
    text = re.sub(r'  +', ' ', text)
    
    # Clean up excessive newlines (more than 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Ensure text doesn't end with incomplete entities
    text = text.strip()
    
    return text
    
    return text
