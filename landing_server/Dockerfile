# Landing Server Dockerfile
FROM python:3.10-slim

# Install system dependencies needed for some Python packages
RUN apt-get update \
     && apt-get install -y --no-install-recommends \
         build-essential \
         gcc \
         g++ \
         libpq-dev \
     && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv

# Create a virtual environment and put it on PATH
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy requirements (explicit path relative to build context root)
COPY landing_server/requirements.txt /tmp/requirements.txt

# Upgrade pip and install requirements into the venv
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Copy shared directory (required for database and config)
COPY shared /app/shared

# Copy landing server application
COPY landing_server /app/landing_server

RUN groupadd -r app && useradd -r -g app -d /home/app -s /sbin/nologin app \
    && mkdir -p /home/app \
    && chown -R app:app /app /home/app

# Set working directory to landing_server
WORKDIR /app/landing_server

# Expose port
EXPOSE 8001

# Print a build-time message so the builder logs show completion
RUN echo "✅ landing-server image build complete"

# Run as non-root user
USER app

# Run the FastAPI server
CMD ["uvicorn", "services.fastapi_server:app", "--host", "0.0.0.0", "--port", "8001"]
