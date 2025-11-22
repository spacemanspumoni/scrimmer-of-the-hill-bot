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
        self.state_message: Optional[discord.Message] = None
        self.scrimmage_channel: Optional[discord.TextChannel] = None
        self.leaderboard_channel: Optional[discord.TextChannel] = None
        self.hackers_channel: Optional[discord.TextChannel] = None
    
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
        self.hackers_channel = discord.utils.get(guild.text_channels, name=config.HACKERS_CHANNEL)
        
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
        king_timed_out = await self.king_manager.check_king_timeout(guild)
        if king_timed_out:
            # Update leaderboard to show no current king
            await self.update_leaderboard_message(guild)
    
    async def recover_leaderboard_state(self, guild: discord.Guild):
        """Recover leaderboard state from pinned state message."""
        if not self.leaderboard_channel:
            return
        
        try:
            # Find our messages
            async for msg in self.leaderboard_channel.pins():
                if msg.author == self.user:
                    # Find leaderboard display message
                    if msg.content.startswith(config.LEADERBOARD_HEADER):
                        print(f'Found existing leaderboard message')
                        self.leaderboard_message = msg
                    
                    # Find state message and recover data from it
                    elif msg.content.startswith(config.STATE_MESSAGE_HEADER):
                        print(f'Found existing state message')
                        self.state_message = msg
                        
                        # Parse state from message
                        recovered = LeaderboardData.from_state_message(msg.content)
                        if recovered:
                            self.leaderboard = recovered
                            # Reinitialize services with recovered data
                            self.king_manager = KingManager(self.leaderboard)
                            self.message_processor = MessageProcessor(self.leaderboard, self.king_manager)
                            print(f'Recovered leaderboard state: King={self.leaderboard.current_king_id}, Streak={self.leaderboard.current_streak}')
            
            if not self.leaderboard_message or not self.state_message:
                print('Missing leaderboard or state message, will create new ones')
        except discord.Forbidden:
            print('Error: Bot lacks permission to read pinned messages')
        except Exception as e:
            print(f'Error recovering leaderboard: {e}')
    
    async def on_message(self, message: discord.Message):
        """Handle new messages."""

        await self.handle_scrimmage_message(message)

        await self.handle_super_mega_hackers_message(message)

        await self.process_commands(message)

    async def handle_super_mega_hackers_message(self, message: discord.Message):
        """Process messages in the super-mega-hackers channel from a specific user with JSON payloads."""
        if message.channel != self.hackers_channel:
            print(f"[super-mega-hackers] Skipping: message.channel ({getattr(message.channel, 'name', None)}) != hackers_channel ({getattr(self.hackers_channel, 'name', None)})")
            return

        # Only process if from a specific super mega hacker
        if str(message.author.id) != "369367182796390401":
            print(f"[super-mega-hackers] Skipping: message.author.id ({message.author.id}) != 369367182796390401")
            return

        # Only process if message starts with an @ mention to the bot
        if not message.content.startswith(f"<@{self.user.id}>") and not message.content.startswith(f"<@!{self.user.id}>"):
            print(f"[super-mega-hackers] Skipping: message does not start with @ mention to bot (content: {message.content[:50]})")
            return

        # Extract JSON blob after the @ mention
        import json
        import re
        # Remove the @ mention (could be <@id> or <@!id>)
        content = re.sub(r"^<@!?" + str(self.user.id) + r">\s*", "", message.content)
        try:
            data = json.loads(content)
        except Exception as e:
            print(f"Error parsing JSON from super-mega-hackers message: {e}")
            return

        # Update leaderboard state from JSON
        from models.leaderboard import LeaderboardData
        recovered = LeaderboardData.from_dict(data)
        if recovered:
            # self.leaderboard = recovered
            # Reinitialize services with recovered data
            # self.king_manager = KingManager(self.leaderboard)
            # self.message_processor = MessageProcessor(self.leaderboard, self.king_manager)
            print(f"[super-mega-hackers] Updated leaderboard state from JSON: King={self.leaderboard.current_king_id}, Streak={self.leaderboard.current_streak}")
            # Update leaderboard display
            # if message.guild:
                # await self.update_leaderboard_message(message.guild)
        else:
            print("[super-mega-hackers] Failed to update leaderboard from JSON")
    
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Handle message edits."""
        # Only process if in scrimmage-results channel
        if after.channel != self.scrimmage_channel:
            return
        
        # Only process if content actually changed
        if before.content != after.content:
            print(f'Message edited in #{after.channel.name}, reprocessing results')
            
            # Remove old reactions if present
            try:
                await after.remove_reaction('✅', self.user)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await after.remove_reaction('❌', self.user)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            
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
        king_timed_out = await self.king_manager.check_king_timeout(message.guild)
        if king_timed_out:
            # Update leaderboard to show no current king
            await self.update_leaderboard_message(message.guild)
        
        # Parse game results
        games = GameResult.parse_from_message(message.content)
        if not games:
            # Invalid format - add X reaction
            try:
                await message.add_reaction('❌')
            except discord.Forbidden:
                print('Error: Bot lacks permission to add reactions')
            except Exception as e:
                print(f'Error adding reaction: {e}')
            return
        
        # Valid format - add checkmark reaction
        try:
            await message.add_reaction('✅')
        except discord.Forbidden:
            print('Error: Bot lacks permission to add reactions')
        except Exception as e:
            print(f'Error adding reaction: {e}')
        
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
        """Update or create the leaderboard display and state messages."""
        if not self.leaderboard_channel:
            print('Error: Leaderboard channel not found')
            return
        
        display_content = self.leaderboard.to_display_message(guild)
        state_content = self.leaderboard.to_state_message()
        
        try:
            # Update or create leaderboard display message
            if self.leaderboard_message:
                await self.leaderboard_message.edit(content=display_content)
                print('Updated leaderboard message')
            else:
                self.leaderboard_message = await self.leaderboard_channel.send(display_content)
                await self.leaderboard_message.pin(reason="Scrim leaderboard")
                print('Created and pinned new leaderboard message')
            
            # Update or create state message
            if self.state_message:
                await self.state_message.edit(content=state_content)
                print('Updated state message')
            else:
                self.state_message = await self.leaderboard_channel.send(state_content)
                await self.state_message.pin(reason="Bot state for recovery")
                print('Created and pinned new state message')
                
        except discord.Forbidden:
            print('Error: Bot lacks permission to edit/pin messages')
        except Exception as e:
            print(f'Error updating leaderboard messages: {e}')


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
