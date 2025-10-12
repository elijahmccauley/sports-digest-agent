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
        date: Either 'yesterday', 'today', 'tomorrow', or a specific date in YYYYMMDD format (e.g. '20240930)
    """
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported, please choose from {', '.join(SPORT_ENDPOINTS.keys())}"
    
    endpoint = SPORT_ENDPOINTS[sport]
    
    if date.lower() == "yesterday":
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        date_label = "Yesterday"
    elif date.lower() == "today":
        target_date = datetime.now().strftime('%Y%m%d')
        date_label = "Today"
    elif date.lower() == "tomorrow":
        target_date = (datetime.now() + timedelta(days=1)).strftime('%Y%m%d')
        date_label = "Tomorrow"
    else:
        target_date = date
        date_label = date
        
    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/scoreboard?dates={target_date}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        events = data.get('events', [])
        
        if not events:
            return f"No {sport} games are scheduled for that day."
        
        result_text = f"**{sport} - {date_label} ({len(events)} games):**\n\n"
        
        for event in events:
            game_id = event.get('id', 'unknown')
            competitions = event.get('competitions', [{}])[0]
            competitors = competitions.get('competitors', [])
            status = event.get('status', {}).get('type', {})
            status_detail = status.get('description', 'Unknown')
            is_completed = status.get('completed', False)
            
            if len(competitors) >= 2:
                away_team = competitors[1].get('team', {}).get('displayName', 'Away')
                away_score = competitors[1].get('score', '0')
                home_team = competitors[0].get('team', {}).get('displayName', 'Home')
                home_score = competitors[0].get('score', '0')
                
                if is_completed:
                    # Show final score
                    result_text += f"• {away_team} {away_score}, {home_team} {home_score} - Final [ID: {game_id}]\n"
                else:
                    # Show scheduled game
                    game_date = event.get('date', '')
                    if game_date:
                        game_time = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                        time_str = game_time.strftime('%I:%M %p')
                    else:
                        time_str = "TBD"
                    
                    result_text += f"• {away_team} @ {home_team} - {time_str} [ID: {game_id}]\n"
                    
        result_text += "\n*Use game ID with get_game_details for more information*"
        
        return result_text
    
    except Exception as e:
        return f"Error fetching scores: {str(e)}"
    
    
@mcp.tool()
async def get_sports_news(sport: str = "NBA", limit: int = 10) -> str:
    """
    Get the latest news headlines for a specific sport.
    
    Args:
        sport: The sport to fetch news for (NBA, WNBA, NFL, MLB, NHL, CFB, or 'all' for general sports)
        limit: Number of news articles to return (default 10)
    """
    if sport.lower() != "all" and sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported. Choose from: {', '.join(SPORT_ENDPOINTS.keys())} or 'all'"
    if sport.lower() == "all":
        url = "https://now.core.api.espn.com/v1/sports/news"
    else:
        endpoint = SPORT_ENDPOINTS[sport]
        url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/news"
        
    try:
        response = requests.get(url, params={'limit': limit})
        response.raise_for_status()
        data = response.json()
        
        articles = data.get('articles', [])
        
        if not articles:
            return f"No news articles found for {sport}."
        
        news_text = f"**{sport} News - latest headlines:**\n\n"
        
        for i, article in enumerate(articles[:limit], 1):
            headline = article.get('headline', 'No headline')
            description = article.get('description', '')
            published = article.get('published', '')
            link = article.get('links', {}).get('web', {}).get('href', '')
            
            if published:
                pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                time_ago = datetime.now(timezone.utc) - pub_date
                if time_ago.days > 0:
                    time_str = f"{time_ago.days}d ago"
                elif time_ago.seconds // 3600 > 0:
                    time_str = f"{time_ago.seconds // 3600}h ago"
                else:
                    time_str = f"{time_ago.seconds // 60}m ago"  
            else:
                time_str = "Recently"
                
            news_text += f"{i}. **{headline}**\n"
            if description:
                news_text += f"   {description}\n"
            news_text += f"   {time_str}"
            if link:
                news_text += f" • [Read more]({link})"
            news_text += "\n\n"
            
        return news_text
    
    except Exception as e:
        return f"Error fetching {sport} news: {str(e)}"
    
    
# ============= SERVER ENTRY POINT =============

if __name__ == "__main__":
    import asyncio
    os.system("lsof -ti:8080 | xargs kill -9 2>/dev/null")
    asyncio.run(mcp.run_async(transport="streamable-http", port=8080))