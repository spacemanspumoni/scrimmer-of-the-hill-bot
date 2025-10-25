import os
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv

import config
from models.leaderboard import LeaderboardData
from models.game_result import GameResult
from services.king_manager import KingManager
from services.message_processor import MessageProcessor

# Load environment variables
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')


class ScrimBot(commands.Bot):
    """Discord bot for tracking King of the Hill scrimmages."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        # Initialize data and services
        self.leaderboard = LeaderboardData()
        self.king_manager = KingManager(self.leaderboard)
        self.message_processor = MessageProcessor(self.leaderboard, self.king_manager)
        
        # Discord objects
        self.leaderboard_message: Optional[discord.Message] = None
        self.scrimmage_channel: Optional[discord.TextChannel] = None
        self.leaderboard_channel: Optional[discord.TextChannel] = None
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        pass
    
    async def on_ready(self):
        """Called when bot is fully logged in and ready."""
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guild(s)')
        
        # Find channels and initialize each guild
        for guild in self.guilds:
            await self.initialize_guild(guild)
    
    async def initialize_guild(self, guild: discord.Guild):
        """Initialize channels and recover state for a guild."""
        print(f'Initializing for guild: {guild.name}')
        
        # Find channels
        self.scrimmage_channel = discord.utils.get(guild.text_channels, name=config.SCRIMMAGE_CHANNEL)
        self.leaderboard_channel = discord.utils.get(guild.text_channels, name=config.LEADERBOARD_CHANNEL)
        
        if not self.scrimmage_channel:
            print(f'Warning: #{config.SCRIMMAGE_CHANNEL} channel not found in {guild.name}')
        else:
            print(f'Found #{config.SCRIMMAGE_CHANNEL} channel')
        
        if not self.leaderboard_channel:
            print(f'Warning: #{config.LEADERBOARD_CHANNEL} channel not found in {guild.name}')
            return
        else:
            print(f'Found #{config.LEADERBOARD_CHANNEL} channel')
        
        # Recover state from pinned message
        await self.recover_leaderboard_state(guild)
        
        # Check if king has timed out
        await self.king_manager.check_king_timeout(guild)
    
    async def recover_leaderboard_state(self, guild: discord.Guild):
        """Recover leaderboard state from pinned message."""
        if not self.leaderboard_channel:
            return
        
        try:
            pinned_messages = await self.leaderboard_channel.pins()
            
            # Find our leaderboard message
            for msg in pinned_messages:
                if msg.author == self.user and msg.content.startswith(config.LEADERBOARD_HEADER):
                    print(f'Found existing leaderboard message')
                    self.leaderboard_message = msg
                    
                    # Parse state from message
                    recovered = LeaderboardData.from_message(msg.content)
                    if recovered:
                        self.leaderboard = recovered
                        # Reinitialize services with recovered data
                        self.king_manager = KingManager(self.leaderboard)
                        self.message_processor = MessageProcessor(self.leaderboard, self.king_manager)
                        print(f'Recovered leaderboard state: King={self.leaderboard.current_king_id}, Streak={self.leaderboard.current_streak}')
                    break
            
            if not self.leaderboard_message:
                print('No existing leaderboard found, will create new one')
        except discord.Forbidden:
            print('Error: Bot lacks permission to read pinned messages')
        except Exception as e:
            print(f'Error recovering leaderboard: {e}')
    
    async def on_message(self, message: discord.Message):
        """Handle new messages."""
        await self.handle_scrimmage_message(message)
        await self.process_commands(message)
    
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Handle message edits."""
        # Only process if content actually changed
        if before.content != after.content:
            print(f'Message edited in #{after.channel.name}, reprocessing results')
            await self.handle_scrimmage_message(after)
    
    async def on_message_delete(self, message: discord.Message):
        """Handle message deletions."""
        # Ignore if not in scrimmage channel
        if message.channel != self.scrimmage_channel:
            return
        
        # Check if this message had game results
        games = GameResult.parse_from_message(message.content)
        if not games:
            return
        
        # Only recalculate if message was recent enough to matter
        # Check if the deleted message was tracked (implies it was recent)
        if message.id in self.leaderboard.processed_messages:
            print(f'Recent message with results deleted, recalculating...')
            await self.message_processor.recalculate_from_recent(
                message.guild, 
                message.channel
            )
            await self.update_leaderboard_message(message.guild)
        else:
            print(f'Old message deleted or not tracked, no recalculation needed')
    
    async def handle_scrimmage_message(self, message: discord.Message):
        """Process scrimmage results from a message (new or edited)."""
        # Ignore bot's own messages
        if message.author == self.user:
            return
        
        # Only process messages in scrimmage-results channel
        if message.channel != self.scrimmage_channel:
            return
        
        # Check if king has expired before processing new results
        await self.king_manager.check_king_timeout(message.guild)
        
        # Parse game results
        games = GameResult.parse_from_message(message.content)
        if not games:
            return
        
        # Check if any winner changed (needs recalculation)
        if self.message_processor.check_any_winners_changed(message, games):
            is_recent = await self.message_processor.is_message_recent(message, message.channel)
            
            if is_recent:
                print(f'Winner changed in recent message - recalculating from last {config.RECENT_MESSAGE_THRESHOLD} messages')
                await self.message_processor.recalculate_from_recent(message.guild, message.channel)
            else:
                print(f'Winner changed in old message - ignoring edit, beyond threshold')
                return
        else:
            # Process normally
            processed = await self.message_processor.process_message(message, message.guild)
            if not processed:
                return
        
        # Clean up old tracking data
        await self.message_processor.cleanup_old_tracking(message.channel)
        
        # Update leaderboard display
        await self.update_leaderboard_message(message.guild)
    
    async def update_leaderboard_message(self, guild: discord.Guild):
        """Update or create the leaderboard message."""
        if not self.leaderboard_channel:
            print('Error: Leaderboard channel not found')
            return
        
        message_content = self.leaderboard.to_message(guild)
        
        try:
            if self.leaderboard_message:
                # Edit existing message
                await self.leaderboard_message.edit(content=message_content)
                print('Updated leaderboard message')
            else:
                # Create new message and pin it
                self.leaderboard_message = await self.leaderboard_channel.send(message_content)
                await self.leaderboard_message.pin(reason="Scrim leaderboard")
                print('Created and pinned new leaderboard message')
        except discord.Forbidden:
            print('Error: Bot lacks permission to edit/pin messages')
        except Exception as e:
            print(f'Error updating leaderboard message: {e}')


def main():
    """Main entry point."""
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set!")
        print("Please create a .env file with your Discord bot token.")
        print("See .env.example for the required format.")
        return
    
    bot = ScrimBot()
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("Error: Invalid Discord token!")
        print("Please check your DISCORD_TOKEN in the .env file.")
    except Exception as e:
        print(f"Error starting bot: {e}")


if __name__ == "__main__":
    main()
