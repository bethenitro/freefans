# Telegram Bot Dockerfile
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv

# Create virtualenv and set PATH
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy and install requirements
COPY telegram_bot/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Copy shared and app
COPY shared /app/shared
COPY telegram_bot /app/telegram_bot

# Create non-root user and set ownership
RUN groupadd -r app && useradd -r -g app -d /home/app -s /sbin/nologin app \
    && mkdir -p /home/app \
    && chown -R app:app /app /home/app

# Set working directory
WORKDIR /app/telegram_bot

# Create necessary directories (app will also create if needed)
RUN mkdir -p /app/telegram_bot/data/cache

# Print build completion message
RUN echo "✅ telegram-bot image build complete"

# Use non-root user
USER app

# Run the bot
CMD ["python", "bot.py"]
