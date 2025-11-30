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
