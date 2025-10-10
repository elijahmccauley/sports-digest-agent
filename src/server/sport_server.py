#!/usr/bin/env python3

import os
import requests
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from mcp.server import Server
import mcp.types as types
from datetime import datetime, timezone

# Initialize logger for server lifecycle events
logger = get_logger(__name__)


# ============= MCP SERVER INITIALIZATION =============

# Create FastMCP instance with comprehensive configuration
mcp = FastMCP(
    name="sport-mcp-server",
    instructions="You are a sports analyst",
)

SPORT_ENDPOINTS = {
    "NBA": "basketball/nba",
    "WNBA": 'basketball/wnba',
    "NFL": 'football/nfl',
    "MLB": 'baseball/mlb',
    "NHL": 'hockey/nhl'
}

# Tool 1: test mock up
@mcp.tool()
async def fetch_todays_game(sport: str = "NBA") -> str:
    """Get today's scheduled games for a specific sport (NBA, WNBA, NFL, MLB, NHL)"""
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported, please choose from {', '.join(SPORT_ENDPOINTS.keys())}"
    
    endpoint = SPORT_ENDPOINTS[sport]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/scoreboard"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        events = data.get('events', [])
        
        if not events:
            return f"No {sport} games are scheduled for today."
        
        games_text = f"**{sport} Games Today ({len(events)} games):**\n\n"
        
        for event in events:
            name = event.get('name', 'Unknown Matchup')
            status = event.get('status', {}).get('type', {}).get('description', "Unknown Status")
            date = event.get('date', '')
            
            if date:
                game_time = datetime.fromisoformat(date.replace('Z', '+00:00'))
                time_str = game_time.strftime('%I:%M %p %Z')
            else:
                time_str = "TBD"
            
            games_text += f"• {name} - {time_str} ({status})\n"
            
        return games_text
    except Exception as e:
        return f"Error fetching {sport} games: {str(e)}"
    
    
    
    
# ============= SERVER ENTRY POINT =============

if __name__ == "__main__":
    import asyncio
    os.system("lsof -ti:8080 | xargs kill -9 2>/dev/null")
    asyncio.run(mcp.run_async(transport="streamable-http", port=8080))