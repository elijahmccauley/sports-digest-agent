from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
from services.sport_email_service import SportEmailService
from fastmcp import FastMCP, Context
from config.settings import get_settings

@dataclass
class AppContext:
    sport_email_service: SportEmailService
    settings: object

@asynccontextmanager
async def app_lifespan(mcp: FastMCP):
    """Initialize all services for the newspaper agent."""
    print("🚀 Starting MCP Server")

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    sport_email_service = SportEmailService(
        {
            "server": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
            "username": "emmccauley6@gmail.com",
            "password": os.getenv("MCP_SMTP_PASSWORD", ""),
            "from_email": "emmccauley6@gmail.com",
            "from_name": "Newspaper Creation Agent",
        }
    )

    try:
        yield AppContext(
            sport_email_service=sport_email_service,
            settings=settings,
        )
    finally:
        print("👋 Shutting down MCP Server")
