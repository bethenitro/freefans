#!/usr/bin/env python3
"""
Main entry point for the FastAPI Landing Server
"""

import uvicorn
from decouple import config
from services.fastapi_server import app

if __name__ == "__main__":
    # Get configuration
    host = config('LANDING_HOST', default='0.0.0.0')
    port = int(config('LANDING_PORT', default=8001))

    print(f"🚀 Starting FastAPI Landing Server on {host}:{port}")
    print(f"📄 Landing pages will be served at http://{host}:{port}")
    print(f"🔗 Base URL configured as: {config('LANDING_BASE_URL', default='http://localhost:8001')}")

    uvicorn.run(app, host=host, port=port)