"""
Configuration settings for the Scrim Bot.
Centralized location for all constants and settings.
"""
import re

# Discord Bot Settings
ROLE_NAME = "Scrimmer of The Hill"
BOT_ROLE_NAME = "Scrimmer of The Hill Bot"
SCRIMMAGE_CHANNEL = "scrimmage-results"
HACKERS_CHANNEL = "super-mega-hackers"
LEADERBOARD_CHANNEL = "scrimmer-of-the-hill"
LEADERBOARD_HEADER = "🏆 Scrim Leaderboard"
STATE_MESSAGE_HEADER = "📊 Bot State"

# Timing Settings
KING_TIMEOUT_DAYS = 3

# Message Processing Settings
RECENT_MESSAGE_THRESHOLD = 5  # Messages within this count are considered "recent"
LEADERBOARD_TOP_N = 10  # Number of players to show on leaderboard

# Regex Pattern for parsing scrimmage results
# Format: @Player1 Score1-Score2 @Player2 (Ego)
# Example: @User1 5-3 @User2 (90) or @User1 5-3 @User2 (80/90)
RESULT_PATTERN = re.compile(
    r'<@!?(\d+)>\s*(\d+)\s*-\s*(\d+)\s*<@!?(\d+)>\s*\(\s*(\d+(?:\s*/\s*\d+)?)\s*\)'
)
