#!/usr/bin/env python3

import os
import requests
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from mcp.server import Server
import mcp.types as types
from datetime import datetime, timezone, timedelta

# Initialize logger for server lifecycle events
logger = get_logger(__name__)


# ============= MCP SERVER INITIALIZATION =============

# Create FastMCP instance with comprehensive configuration
mcp = FastMCP(
    name="sport_mcp_server",
    instructions="You are a sports analyst",
)

SPORT_ENDPOINTS = {
    "NBA": "basketball/nba",
    "WNBA": 'basketball/wnba',
    "NFL": 'football/nfl',
    "MLB": 'baseball/mlb',
    "NHL": 'hockey/nhl',
    "CFB": 'football/college-football'
}
    
    
@mcp.tool()
async def fetch_scores(sport: str = 'NBA', date: str = "yesterday") -> str:
    """
    Get game scores for a specific sport and date.
    Args: 
        sport: The sport to fetch (NBA, WNBA, NFL, NHL, MLB, CFB)
        date: Either 'yesterday', 'today', or a specific date in YYYYMMDD format (e.g. '20240930)
    """
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported, please choose from {', '.join(SPORT_ENDPOINTS.keys())}"
    
    endpoint = SPORT_ENDPOINTS[sport]
    
    if date.lower() == 'yesterday':
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    elif date.lower() == "today":
        target_date = datetime.now().strftime('%Y%m%d')
    else:
        target_date = date
        
    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/scoreboard?dates={target_date}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        events = data.get('events', [])
        
        if not events:
            return f"No {sport} games are scheduled for that day."
        
        scores_text = f"**{sport} Scores ({len(events)} games):**\n\n"
        
        for event in events:
            competitions = event.get('competitions', [{}])[0]
            competitors = competitions.get('competitors', [])
            status = event.get('status', {}).get('type', {}).get('description', 'Unknown')
            
            if len(competitors) >= 2:
                away_team = competitors[1].get('team', {}).get('displayName', 'Away')
                away_score = competitors[1].get('score', '0')
                home_team = competitors[0].get('team', {}).get('displayName', 'Home')
                home_score = competitors[0].get('score', '0')
                
                scores_text += f"• {away_team} {away_score} @ {home_team} {home_score} - {status}\n"
        
        return scores_text
    
    except Exception as e:
        return f"Error fetching scores: {str(e)}"
    
    
# ============= SERVER ENTRY POINT =============

if __name__ == "__main__":
    import asyncio
    os.system("lsof -ti:8080 | xargs kill -9 2>/dev/null")
    asyncio.run(mcp.run_async(transport="streamable-http", port=8080))