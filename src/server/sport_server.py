#!/usr/bin/env python3

import os
import dotenv
import requests
import json
from fastmcp import FastMCP, Context
from fastmcp.utilities.logging import get_logger
from mcp.server import Server
import mcp.types as types
from datetime import datetime, timezone, timedelta
#from fastmcp.prompts import UserMessage
from pydantic import BaseModel
from services.sport_email_service import EmailService
from pathlib import Path
from app_context import app_lifespan
from config.settings import get_settings

# Initialize logger for server lifecycle events
logger = get_logger(__name__)

class Confirmation(BaseModel):
    confirmed: bool
    
dotenv.load_dotenv()
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

# ============= MCP SERVER INITIALIZATION =============

# Create FastMCP instance with comprehensive configuration
mcp = FastMCP(
    name="sport_mcp_server",
    instructions="You are a sports analyst",
    lifespan=app_lifespan,
)

PREFERENCES_FILE = 'user_preferences.json'

DEFAULT_PREFERENCES = {
    "sports": {
        "NBA": True,
        "WNBA": True,
        "NFL": True,
        "MLB": True,
        "NHL": True,
        "CFB": True
    },
    "favorite_teams": [],
    "email": "",
    "digest_time": "06:00",
    "include_news": True,
    "news_limit": 15
}

SPORT_ENDPOINTS = {
    "NBA": "basketball/nba",
    "WNBA": 'basketball/wnba',
    "NFL": 'football/nfl',
    "MLB": 'baseball/mlb',
    "NHL": 'hockey/nhl',
    "CFB": 'football/college-football'
}

ODDS_SPORT_KEYS = {
    "NBA": 'basketball_nba',
    "MLB": 'baseball_mlb',
    "NFL": "americanfootball_nfl",
    "NHL": 'icehockey_nhl',
    "CFB": 'americanfootball_ncaa',
}

email_settings = {
    "server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "port": int(os.getenv("SMTP_PORT", "587")),
    "use_tls": True,
    "use_ssl": False,
    "username": os.getenv("SENDER_EMAIL"),
    "password": os.getenv("SENDER_PASSWORD"),
    "from_email": os.getenv("SENDER_EMAIL"),
    "from_name": "Sports Digest Agent"
}

email_service = EmailService(email_settings)

# HELPER FUNCTIONS +++++++++++++++++++++++++++++++++++++++++++++++

def load_preferences():
    """Load preferences from JSON file, create if doesn't exist"""
    if not os.path.exists(PREFERENCES_FILE):
        save_preferences(DEFAULT_PREFERENCES)
        return DEFAULT_PREFERENCES.copy()
    try:
        with open(PREFERENCES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading preferences: {e}")
        return DEFAULT_PREFERENCES.copy()
    
def save_preferences(prefs):
    """Save preferences to JSON file"""
    try:
        with open(PREFERENCES_FILE, 'w') as f:
            json.dump(prefs, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving preferences: {e}")
        return False
    
async def _get_games(sport: str = 'NBA', date: str = "yesterday") -> str:
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
                    if is_completed:
                        result_text += f"• {away_team} {away_score}, {home_team} {home_score} - Final [ID: {game_id}, Sport: {sport}]\n"
                    else:
                        result_text += f"• {away_team} @ {home_team} - {time_str} [ID: {game_id}, Sport: {sport}]\n"
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
    
async def _get_sports_news(sport: str = "NBA", limit: int = 10) -> str:
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
    

async def _get_game_details(game_id: str, sport: str = "NBA") -> str:
    """
    Get detailed information about a specific game including player stats and highlights.
    Args:
        game_id: The ESPN game ID (can be found in game data)
        sport: the sport of the game (NBA, NFL, WNBA, NHL, MLB, CFB)
    """
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported. Choose from: {', '.join(SPORT_ENDPOINTS.keys())}"
    
    endpoint = SPORT_ENDPOINTS[sport]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/summary?event={game_id}"
    
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        header = data.get('header', {})
        competitions = header.get('competitions', [{}])[0]
        competitors = competitions.get('competitors', [])
        
        if len(competitors) < 2:
            return "Unable to fetch game details."
        
        away_team = competitors[1].get('team', {}).get('displayName', 'Away')
        away_score = competitors[1].get('score', '0')
        home_team = competitors[0].get('team', {}).get('displayName', 'Home')
        home_score = competitors[0].get('score', '0')
        
        result_text = f"**{away_team} {away_score} @ {home_team} {home_score}**\n\n"
        
        box_score = data.get('boxscore', {})
        players = box_score.get('players', [])
        
        if players:
            result_text += "**Top Performers:**\n\n"
            
            for team_data in players[:2]:  
                team_name = team_data.get('team', {}).get('displayName', 'Team')
                statistics = team_data.get('statistics', [])
                
                if statistics:
                    result_text += f"*{team_name}:*\n"
                    
                    for stat_group in statistics[:3]:  
                        athletes = stat_group.get('athletes', [])
                        for athlete in athletes[:1]:  
                            name = athlete.get('athlete', {}).get('displayName', 'Unknown')
                            stats_list = athlete.get('stats', [])
                            
                            if len(stats_list) >= 3:
                                pts = stats_list[0] if stats_list[0] != '0' else stats_list[0]
                                reb = stats_list[1] if len(stats_list) > 1 else '0'
                                ast = stats_list[2] if len(stats_list) > 2 else '0'
                                
                                result_text += f"  • {name}: {pts} PTS, {reb} REB, {ast} AST\n"
                    
                    result_text += "\n"
                    
        notes = data.get('notes', [])
        if notes:
            result_text += "**Game Notes:**\n"
            for note in notes[:3]:
                headline = note.get('headline', '')
                if headline:
                    result_text += f"• {headline}\n"
        
        return result_text
    
    except Exception as e:
        return f"Error fetching game details: {str(e)}"
    
    

async def _get_odds(sport: str) -> str:
    """
    Gets betting odds for upcoming games from a specific sport
    Args:
        sport: The sport which you want to get odds for (MLB, NBA, NFL, NHL, CFB)
    Returns a string with the moneyline betting odds for each upcoming game
    """
    base_url = "https://api.the-odds-api.com/v4"
    
    sport_key = ODDS_SPORT_KEYS[sport]
    odds_url = (
        f"{base_url}/sports/{sport_key}/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h&oddsFormat=american"
    )
    try:
        response = requests.get(odds_url)
        response.raise_for_status()
        odds_data = response.json()
        if not odds_data:
            return f"   -> No upcoming games with odds found for {sport}."
        odds_text = f"**Upcoming {sport} Odds:**\n\n"
        for game in odds_data:
            home_team = game['home_team']
            away_team = game['away_team']
            commence_time = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            
            odds_text += f"**{away_team} @ {home_team}**\n"
            odds_text += f"   Start Time: {commence_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"

            bookmaker = next((b for b in game['bookmakers'] if b['key'] == 'fanduel'), game['bookmakers'][0])
            
            odds_text += f"   Odds via {bookmaker['title']}:\n"
            market = bookmaker['markets'][0]
            for outcome in market['outcomes']:
                odds_text += f"     - {outcome['name']}: {outcome['price']}\n"
            odds_text += "\n"
            
        return odds_text
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 422:
            error_message = f"⚠️ No odds available for '{sport_key}'. It may be out of season or not included in your API plan."
        else:
            error_message = f"❌ HTTP error fetching odds for {sport_key}: {http_err}"
        return None, error_message
    
    
# Resources +++++++++++++++++++++++++++++++++++++++++++++++

@mcp.resource("file://preferences.json")
async def get_preferences_resource(ctx: Context = None) -> str:
    """User's sports preferences - teams, sports, digest settings.
    Annotations: High priority, for assistant consumption."""
    prefs = load_preferences()
    content = "# User Sports Preferences\n\n"
    content += f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    enabled = [s for s, e in prefs['sports'].items() if e]
    if enabled:
        content += "## Enabled Sports\n"
        for sport in enabled:
            content += f"- {sport}\n"
        content += "\n"
        
    if prefs.get("favorite_teams"):
        content += "## Favorite Teams\n"
        for team in prefs['favorite_teams']:
            content += f"- {team}\n"
        content += "\n"
        
    content += f"## Digest Settings\n"
    content += f"- Email: {prefs.get('email', 'Not set')}\n"
    content += f"- Digest Time: {prefs.get('digest_time', '08:00')}\n"
    content += f"- Include News: {prefs.get('include_news', True)}\n"
    content += f"- News Limit: {prefs.get('news_limit', 5)} per sport\n"
    
    return content

# Tools ---------------------------------------------------
    
@mcp.tool()
async def get_preferences() -> str:
    """Get your current sports digest preferences"""
    prefs = load_preferences()
    result = "**Your Current Preferences:**\n\n"
    
    enabled_sports = [sport for sport, enabled in prefs['sports'].items() if enabled]
    disabled_sports = [sport for sport, enabled in prefs['sports'].items() if not enabled]
    
    result += "**Enabled Sports:**\n"
    if enabled_sports:
        for sport in enabled_sports:
            result += f"  ✓ {sport}\n"
    else:
        result += "  None\n"
        
    result += "\n**Disabled Sports:**\n"
    if disabled_sports:
        for sport in disabled_sports:
            result += f"  ✗ {sport}\n"
    else:
        result += "  None\n"
    
    # Favorite teams
    result += f"\n**Favorite Teams:**\n"
    if prefs['favorite_teams']:
        for team in prefs['favorite_teams']:
            result += f"  • {team}\n"
    else:
        result += "  None set\n"
    
    # Other settings
    result += f"\n**Email:** {prefs['email'] or 'Not set'}\n"
    result += f"**Digest Time:** {prefs['digest_time']}\n"
    result += f"**Include News:** {'Yes' if prefs['include_news'] else 'No'}\n"
    result += f"**News Articles per Sport:** {prefs['news_limit']}\n"
    
    return result
    
@mcp.tool()
async def toggle_sport(sport: str, enabled: bool, ctx: Context = None) -> str:
    """
    Enable or disable a sport in your daily digest
    
    Args:
        sport: The sport to toggle (NBA, WNBA, NFL, MLB, NHL, CFB)
        enabled: True to enable, False to disable
    """
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' not recognized. Choose from: {', '.join(SPORT_ENDPOINTS.keys())}"
    
    prefs = load_preferences()
    prefs['sports'][sport] = enabled
    
    if save_preferences(prefs):
        status = "enabled" if enabled else "disabled"
        return f"✓ {sport} has been {status} in your daily digest"
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def set_favorite_teams(teams: list) -> str:
    """
    Set your favorite teams to get personalized coverage
    
    Args:
        teams: List of team names (e.g., ["Los Angeles Lakers", "New York Liberty"])
    """
    prefs = load_preferences()
    prefs['favorite_teams'] = teams
    
    if save_preferences(prefs):
        if teams:
            team_list = "\n  • ".join(teams)
            return f"✓ Favorite teams updated:\n  • {team_list}"
        else:
            return "✓ Favorite teams cleared"
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def add_favorite_team(team: str, ctx: Context = None) -> str:
    """
    Add a team to your favorites
    
    Args:
        team: Team name (e.g., "Los Angeles Lakers")
    """
    prefs = load_preferences()
    
    if team in prefs['favorite_teams']:
        return f"{team} is already in your favorites"
    
    prefs['favorite_teams'].append(team)
    
    if save_preferences(prefs):
        return f"✓ Added {team} to your favorite teams"
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def remove_favorite_team(team: str, ctx: Context = None) -> str:
    """
    Remove a team from your favorites
    
    Args:
        team: Team name to remove
    """
    prefs = load_preferences()
    
    if team not in prefs['favorite_teams']:
        return f"{team} is not in your favorites"
    
    prefs['favorite_teams'].remove(team)
    
    if save_preferences(prefs):
        return f"✓ Removed {team} from your favorite teams"
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def set_email(email: str) -> str:
    """
    Set your email address for daily digests
    
    Args:
        email: Your email address
    """
    prefs = load_preferences()
    prefs['email'] = email
    
    if save_preferences(prefs):
        return f"✓ Email set to {email}"
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def set_digest_settings(
    include_news: bool = None,
    news_limit: int = None,
    digest_time: str = None
) -> str:
    """
    Configure digest settings
    
    Args:
        include_news: Whether to include news in digest
        news_limit: Number of news articles per sport
        digest_time: Preferred time for digest (HH:MM format, e.g., "08:00")
    """
    prefs = load_preferences()
    
    changes = []
    
    if include_news is not None:
        prefs['include_news'] = include_news
        changes.append(f"Include news: {include_news}")
    
    if news_limit is not None:
        prefs['news_limit'] = news_limit
        changes.append(f"News limit: {news_limit}")
    
    if digest_time is not None:
        prefs['digest_time'] = digest_time
        changes.append(f"Digest time: {digest_time}")
    
    if not changes:
        return "No changes specified"
    
    if save_preferences(prefs):
        return "✓ Settings updated:\n  • " + "\n  • ".join(changes)
    else:
        return "Error saving preferences"
    
@mcp.tool()
async def reset_preferences(ctx: Context = None) -> str:
    """Reset all preferences to default values"""
    result = await ctx.elicit(
        message="⚠️ **This will reset ALL your preferences to defaults.**\n\nThis includes:\n- Sport selections\n- Favorite teams\n- Email\n- Digest settings\n\nAre you sure?",
        response_type=Confirmation,
    )
    
    if result.action != "accept" or not result.data.confirmed:
        return "❌ **Reset cancelled** - Your preferences are unchanged"
    
    if save_preferences(DEFAULT_PREFERENCES):
        return "✅ **All preferences have been reset to defaults**"
    else:
        return "❌ Error resetting preferences"

    
    
@mcp.tool()
async def get_games(sport: str = 'NBA', date: str = "yesterday") -> str:
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
                    if is_completed:
                        result_text += f"• {away_team} {away_score}, {home_team} {home_score} - Final [ID: {game_id}, Sport: {sport}]\n"
                    else:
                        result_text += f"• {away_team} @ {home_team} - {time_str} [ID: {game_id}, Sport: {sport}]\n"
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
    
@mcp.tool()
async def get_game_details(game_id: str, sport: str = "NBA") -> str:
    """
    Get detailed information about a specific game including player stats and highlights.
    Args:
        game_id: The ESPN game ID (can be found in game data)
        sport: the sport of the game (NBA, NFL, WNBA, NHL, MLB, CFB)
    """
    if sport not in SPORT_ENDPOINTS:
        return f"Sport '{sport}' is not supported. Choose from: {', '.join(SPORT_ENDPOINTS.keys())}"
    
    endpoint = SPORT_ENDPOINTS[sport]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint}/summary?event={game_id}"
    
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        header = data.get('header', {})
        competitions = header.get('competitions', [{}])[0]
        competitors = competitions.get('competitors', [])
        
        if len(competitors) < 2:
            return "Unable to fetch game details."
        
        away_team = competitors[1].get('team', {}).get('displayName', 'Away')
        away_score = competitors[1].get('score', '0')
        home_team = competitors[0].get('team', {}).get('displayName', 'Home')
        home_score = competitors[0].get('score', '0')
        
        result_text = f"**{away_team} {away_score} @ {home_team} {home_score}**\n\n"
        
        box_score = data.get('boxscore', {})
        players = box_score.get('players', [])
        
        if players:
            result_text += "**Top Performers:**\n\n"
            
            for team_data in players[:2]:  
                team_name = team_data.get('team', {}).get('displayName', 'Team')
                statistics = team_data.get('statistics', [])
                
                if statistics:
                    result_text += f"*{team_name}:*\n"
                    
                    for stat_group in statistics[:3]:  
                        athletes = stat_group.get('athletes', [])
                        for athlete in athletes[:1]:  
                            name = athlete.get('athlete', {}).get('displayName', 'Unknown')
                            stats_list = athlete.get('stats', [])
                            
                            if len(stats_list) >= 3:
                                pts = stats_list[0] if stats_list[0] != '0' else stats_list[0]
                                reb = stats_list[1] if len(stats_list) > 1 else '0'
                                ast = stats_list[2] if len(stats_list) > 2 else '0'
                                
                                result_text += f"  • {name}: {pts} PTS, {reb} REB, {ast} AST\n"
                    
                    result_text += "\n"
                    
        notes = data.get('notes', [])
        if notes:
            result_text += "**Game Notes:**\n"
            for note in notes[:3]:
                headline = note.get('headline', '')
                if headline:
                    result_text += f"• {headline}\n"
        
        return result_text
    
    except Exception as e:
        return f"Error fetching game details: {str(e)}"
    
    
@mcp.tool()
async def get_odds(sport: str) -> str:
    """
    Gets betting odds for upcoming games from a specific sport
    Args:
        sport: The sport which you want to get odds for (MLB, NBA, NFL, NHL, CFB)
    Returns a string with the moneyline betting odds for each upcoming game
    """
    base_url = "https://api.the-odds-api.com/v4"
    
    sport_key = ODDS_SPORT_KEYS[sport]
    odds_url = (
        f"{base_url}/sports/{sport_key}/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h&oddsFormat=american"
    )
    try:
        response = requests.get(odds_url)
        response.raise_for_status()
        odds_data = response.json()
        if not odds_data:
            return f"   -> No upcoming games with odds found for {sport}."
        odds_text = f"**Upcoming {sport} Odds:**\n\n"
        for game in odds_data:
            home_team = game['home_team']
            away_team = game['away_team']
            commence_time = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            
            odds_text += f"**{away_team} @ {home_team}**\n"
            odds_text += f"   Start Time: {commence_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"

            bookmaker = next((b for b in game['bookmakers'] if b['key'] == 'fanduel'), game['bookmakers'][0])
            
            odds_text += f"   Odds via {bookmaker['title']}:\n"
            market = bookmaker['markets'][0]
            for outcome in market['outcomes']:
                odds_text += f"     - {outcome['name']}: {outcome['price']}\n"
            odds_text += "\n"
            
        return odds_text
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 422:
            error_message = f"⚠️ No odds available for '{sport_key}'. It may be out of season or not included in your API plan."
        else:
            error_message = f"❌ HTTP error fetching odds for {sport_key}: {http_err}"
        return None, error_message
    
    
    
@mcp.tool()
async def create_daily_digest(
    include_odds: bool = True,
    ctx: Context = None) -> str:
    
    """
    Create a comprehensive daily sports digest based on user preferences
    
    This is a WORKHORSE TOOL that:
    1. Reads preferences automatically
    2. Fetches today's games for enabled sports
    3. Fetches yesterday's scores
    4. Gets latest news (if enabled)
    5. Gets odds (if requested)
    6. Formats everything into email ready html
    7. Returns preview and saves for sending
    
    Args: 
        inculde_odds: Whether to include betting odds
    Returns:
        Preview of digest with stats and option to send
    """
    email_service = EmailService(email_settings)
    prefs = load_preferences()
    enabled_sports = [s for s, e in prefs['sports'].items() if e]
    if not enabled_sports:
        return "❌ No sports enabled. Use toggle_sport() to enable some sports first."
    
    await ctx.info(f"📰 Creating digest for {len(enabled_sports)} sports...")
    
    digest_content = {
        'title': f"Sports Digest - {datetime.now().strftime('%A, %B %d, %Y')}",
        'sports_sections': []
    }
    for i, sport in enumerate(enabled_sports):
        await ctx.report_progress(progress=i, total=len(enabled_sports))
        await ctx.info(f"Processing {sport}...")
        
        section = {
            'sport': sport,
            'todays_games': await _get_games(sport, 'today'),
            'yesterdays_scores': await _get_games(sport, 'yesterday'),
        }
        
        if prefs.get('include_news', True):
            section['news'] = await _get_sports_news(sport, 'yesterday')
            
        if include_odds:
            section['odds'] = await _get_odds(sport)

        digest_content['sports_sections'].append(section)
        
    await ctx.report_progress(progress=len(enabled_sports), total=len(enabled_sports))
    
    digest_id = f"digest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    
    # Save draft
    settings = ctx.request_context.lifespan_context.settings
    drafts_dir = Path(settings.data_dir) / "newspapers"
    drafts_dir.mkdir(exist_ok=True)

    draft_file = drafts_dir / f"{digest_id}.json"
    with open(draft_file, "w") as f:
        json.dump(digest_content, f, indent=2)

    # Save HTML draft
    email_service = ctx.request_context.lifespan_context.email_service
    html_content = email_service._create_html_version(digest_content)
    html_file = drafts_dir / f"{digest_id}.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    stats = {
        'sports_count': len(enabled_sports),
        'games_today': sum(1 for s in digest_content['sports_sections'] 
                          for _ in s.get('todays_games', '')),
        'scores_yesterday': sum(1 for s in digest_content['sports_sections'] 
                               for _ in s.get('yesterdays_scores', '')),
    }
    
    result = f"# ✅ Digest Created: {digest_id}\n\n"
    result += f"**Sports:** {', '.join(enabled_sports)}\n"
    result += f"**Today's Games:** {stats['games_today']}\n"
    result += f"**Yesterday's Scores:** {stats['scores_yesterday']}\n"
    result += f"**Email Ready:** {prefs.get('email', 'Email not set')}\n\n"
    result += "**Use send_digest() to deliver via email**\n"
    
    return result
    
    
    
# Prompts ======================================

@mcp.prompt()
async def setup_preferences() -> str:
    """Help user configure their sports preferences"""
    return """Interactive preference setup

WORKFLOW:
1. get_preferences() → Show current settings
2. Ask user which sports they follow
3. toggle_sport() for each sport
4. list_available_teams() → Show teams
5. add_favorite_team() for their teams
6. set_email() → Configure delivery
7. get_preferences() → Confirm final settings"""

@mcp.prompt()
async def morning_digest_workflow() -> str:
    """Create and send morning sports digest"""
    return """Create morning sports digest (5min workflow)

WORKFLOW:
1. Check preferences resource to see enabled sports
2. create_daily_digest(include_odds=True)
3. validate_digest(digest_id)
4. send_digest(digest_id)

AGENT CONTROLS: Review before sending
USER CONTROLS: Preferences set beforehand"""

    
# ============= SERVER ENTRY POINT =============

if __name__ == "__main__":
    import asyncio
    os.system("lsof -ti:8080 | xargs kill -9 2>/dev/null")
    asyncio.run(mcp.run_async(transport="streamable-http", port=8080))