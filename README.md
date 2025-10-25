# Scrimmer of the Hill Discord Bot

A Discord bot that automatically tracks and crowns a "King of the Hill" based on scrimmage results posted in a designated channel.

## Features

- 🏆 **Automatic Role Management**: Assigns "Scrimmer of the Hill" role to the current king
- 📊 **Streak Tracking**: Records best win streaks for each player
- ⏰ **Auto-Expiration**: Removes king status after 3 days of inactivity
- 💾 **State Persistence**: Recovers leaderboard from pinned messages on restart
- 📈 **Live Leaderboard**: Maintains a top 10 leaderboard in real-time

## Setup

### Prerequisites

- Python 3.8 or higher
- A Discord bot token ([create one here](https://discord.com/developers/applications))

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd scrim_of_the_hill
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```

4. Edit `.env` and add your Discord bot token:
```
DISCORD_TOKEN=your_actual_bot_token_here
```

### Discord Bot Configuration

Your bot needs the following permissions:
- **Read Message History** - To monitor scrimmage results
- **Send Messages** - To post leaderboard updates
- **Manage Roles** - To assign/remove the king role
- **Manage Messages** - To pin leaderboard messages

**OAuth2 URL Generator** settings:
- Scopes: `bot`

### Server Setup

Create these channels in your Discord server:
1. `#scrimmage-results` - Where users post game results
2. `#scrimmer-of-the-hill` - Where the bot posts the leaderboard

The bot will automatically create the "Scrimmer of the Hill" role if it doesn't exist.

## Running the Bot

### Local Development

```bash
python bot.py
```

You should see:
```
<BotName> has connected to Discord!
Bot is in 1 guild(s)
Initializing for guild: <YourServer>
Found #scrimmage-results channel
Found #scrimmer-of-the-hill channel
```