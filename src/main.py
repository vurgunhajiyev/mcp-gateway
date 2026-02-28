"""
MCP Gateway — Entry point.

Run with:
    uvicorn src.main:app --host 0.0.0.0 --port 8080
    python -m src.main
"""
from __future__ import annotations

import uvicorn

from src.core.app import create_app
from src.core.config import get_settings

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.observability.log_level.lower(),
        access_log=False,  # we handle logging in middleware
        reload=settings.debug,
    )
