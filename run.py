"""
run.py
Entry point untuk menjalankan server FastAPI.

Usage:
  python run.py
"""

import uvicorn
from dotenv import load_dotenv
load_dotenv()

from app.config.settings import get_settings
settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info",
    )
