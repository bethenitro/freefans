#!/usr/bin/env python3
"""
Run both the Telegram bot and FastAPI landing server
"""

import asyncio
import subprocess
import sys
import time
import signal
import os

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decouple import config

def run_fastapi_server():
    """Run the FastAPI server"""
    host = config('LANDING_HOST', default='0.0.0.0')
    port = int(config('LANDING_PORT', default=8001))
    
    print(f"🚀 Starting FastAPI Landing Server on {host}:{port}")
    
    # Run uvicorn server
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "services.fastapi_server:app",
        "--host", host,
        "--port", str(port),
        "--reload"
    ]
    
    return subprocess.Popen(cmd)

def run_telegram_bot():
    """Run the Telegram bot"""
    print("🤖 Starting Telegram Bot")
    
    cmd = [sys.executable, "bot.py"]
    return subprocess.Popen(cmd)

def main():
    """Main function to run both servers"""
    print("=" * 60)
    print("🎯 FreeFans - Starting Both Servers")
    print("=" * 60)
    
    # Check if landing server is enabled
    landing_enabled = config('LANDING_ENABLED', default='true').lower() == 'true'
    
    processes = []
    
    try:
        if landing_enabled:
            # Start FastAPI server first
            fastapi_process = run_fastapi_server()
            processes.append(('FastAPI Server', fastapi_process))
            
            # Wait a moment for FastAPI to start
            print("⏳ Waiting for FastAPI server to start...")
            time.sleep(3)
        else:
            print("⚠️  Landing server is disabled - bot will provide direct links")
        
        # Start Telegram bot
        bot_process = run_telegram_bot()
        processes.append(('Telegram Bot', bot_process))
        
        print("\n✅ All servers started successfully!")
        print("\n📋 Running Services:")
        for name, process in processes:
            print(f"   • {name} (PID: {process.pid})")
        
        if landing_enabled:
            base_url = config('LANDING_BASE_URL', default='http://localhost:8001')
            print(f"\n🌐 Landing Server: {base_url}")
            
            # Check if using Cloudflare tunnel
            if 'trycloudflare.com' in base_url:
                print("🚇 Using Cloudflare Tunnel - Landing pages accessible from internet!")
                print("💡 Make sure your cloudflared tunnel is running and pointing to port 8001")
            elif 'localhost' in base_url:
                print("🏠 Running locally - Only accessible from this machine")
        
        print("\n💡 Press Ctrl+C to stop all servers")
        print("=" * 60)
        
        # Wait for processes
        while True:
            # Check if any process has died
            for name, process in processes:
                if process.poll() is not None:
                    print(f"❌ {name} has stopped unexpectedly!")
                    return 1
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down servers...")
        
        # Terminate all processes
        for name, process in processes:
            print(f"   Stopping {name}...")
            process.terminate()
            
        # Wait for graceful shutdown
        time.sleep(2)
        
        # Force kill if still running
        for name, process in processes:
            if process.poll() is None:
                print(f"   Force killing {name}...")
                process.kill()
        
        print("✅ All servers stopped")
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())