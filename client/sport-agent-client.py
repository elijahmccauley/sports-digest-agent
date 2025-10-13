import asyncio
from datetime import datetime

from fast_agent import FastAgent, RequestParams

# Create the application
fast = FastAgent("Sport Digest Agent", config_path="./fastagent.config.yaml")


# Define the agent with comprehensive news sources
@fast.agent(
    instruction=f"""You are a sports digest assistant with access to real-time sports data and scheduling information.
    
    Current date and time: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p %Z')}
    
    You have access to:
    - **Sports Schedule Data**: Fetch today's games across NBA, WNBA, NFL, MLB, and NHL
    - **Score Information**: Get results from yesterday's games or any specific date
    - **Detailed Game Stats**: Get player stats from a specific game
    - **Sports News**: Get major sports news from specific sports or just sports overall
    - **User Preferences**: Manage which sports the user wants to follow
    
    Use these tools to:
    1. Provide up-to-date information on today's games
    2. Show scores and results from recent games
    3. Keep users up to date with breaking news
    3. Help users stay informed about their favorite sports
    4. Create personalized daily sports digests
    
    Be concise and informative. When showing game schedules, include team names, times, and current status.
    Format your responses in a clear, easy-to-read manner.""",
    name="Sports Agent",
    servers=[
        # Our custom newspaper creation server
        "sport_mcp_server",
        #"fetch",  # Content fetching and extraction
        #"brave",  # Web search
        #"perplexity_mcp",  # AI-powered research
    ],
    request_params=RequestParams(
        max_iterations=9999,
    ),
)
async def main():
    async with fast.run() as agent:
        await agent.interactive()


if __name__ == "__main__":
    asyncio.run(main())
