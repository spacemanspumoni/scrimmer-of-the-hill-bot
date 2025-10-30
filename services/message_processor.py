"""
Message processing and result tracking service.
Handles parsing messages, tracking processed results, and recalculation logic.
"""
import hashlib
from typing import List, Set
import discord
import config
from models.leaderboard import LeaderboardData
from models.game_result import GameResult
from services.king_manager import KingManager


class MessageProcessor:
    """Processes scrimmage result messages and manages result tracking."""
    
    def __init__(self, leaderboard: LeaderboardData, king_manager: KingManager):
        self.leaderboard = leaderboard
        self.king_manager = king_manager
    
    def calculate_content_hash(self, content: str) -> str:
        """Calculate SHA256 hash of message content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def create_result_key(self, message_id: int, game: GameResult, timestamp: int) -> str:
        """Create a unique key for a game result."""
        player_ids = game.get_sorted_player_ids()
        return f"{message_id}:{player_ids[0]}:{player_ids[1]}:{timestamp}"
    
    def has_winner_changed(self, result_key: str, current_winner_id: int) -> bool:
        """Check if the winner for a result has changed from what was previously recorded."""
        if not self.leaderboard.is_result_processed(result_key):
            return False
        
        previous_winner = self.leaderboard.get_processed_winner(result_key)
        return previous_winner != 0 and previous_winner != current_winner_id
    
    def check_any_winners_changed(self, message: discord.Message, games: List[GameResult]) -> bool:
        """Check if any game result in the message has a different winner than before."""
        timestamp = int(message.created_at.timestamp())
        
        for game in games:
            result_key = self.create_result_key(message.id, game, timestamp)
            if self.has_winner_changed(result_key, game.winner_id):
                print(f'Winner changed for result {result_key}')
                return True
        
        return False
    
    async def is_message_recent(self, message: discord.Message, channel: discord.TextChannel) -> bool:
        """Check if a message is within the recent message threshold."""
        try:
            recent_count = 0
            async for msg in channel.history(limit=config.RECENT_MESSAGE_THRESHOLD):
                if msg.id == message.id:
                    print(f'Message is recent (position {recent_count + 1} of last {config.RECENT_MESSAGE_THRESHOLD})')
                    return True
                recent_count += 1
            
            print(f'Message is old (not in last {config.RECENT_MESSAGE_THRESHOLD} messages)')
            return False
        except discord.Forbidden:
            print('Error: Bot lacks permission to read message history')
            return False
    
    async def process_message(
        self,
        message: discord.Message,
        guild: discord.Guild
    ) -> bool:
        """
        Process a scrimmage result message.
        
        Returns:
            True if message was processed, False if skipped
        """
        # Calculate content hash
        content_hash = self.calculate_content_hash(message.content)
        
        # Check if already processed with same content
        if self.leaderboard.is_message_unchanged(message.id, content_hash):
            print(f'Message {message.id} already processed with same content, skipping')
            return False
        
        # Parse game results
        games = GameResult.parse_from_message(message.content)
        if not games:
            return False
        
        # Check if any winner changed
        winner_changed = self.check_any_winners_changed(message, games)
        
        if winner_changed:
            is_recent = await self.is_message_recent(message, message.channel)
            
            if is_recent:
                print(f'Winner changed in recent message - recalculating')
                return False  # Signal to trigger recalculation
            else:
                print(f'Winner changed in old message - ignoring edit')
                return False
        
        # Process each game result
        timestamp = int(message.created_at.timestamp())
        for game in games:
            await self.process_single_result(message, game, guild)
        
        # Mark message as processed
        self.leaderboard.mark_message_processed(message.id, content_hash)
        
        return True
    
    async def process_single_result(
        self,
        message: discord.Message,
        game: GameResult,
        guild: discord.Guild
    ) -> None:
        """Process a single game result."""
        timestamp_int = int(message.created_at.timestamp())
        result_key = self.create_result_key(message.id, game, timestamp_int)
        
        # Check if this is a new result (not previously processed)
        is_new_result = not self.leaderboard.is_result_processed(result_key)
        
        if is_new_result:
            print(f'Processing NEW result: Winner={game.winner_id} (ego {game.winner_ego}), Loser={game.loser_id} (ego {game.loser_ego})')
        else:
            print(f'Reprocessing EXISTING result: Winner={game.winner_id} (ego {game.winner_ego})')
        
        # During recalculation, always process results (even if previously seen)
        # to rebuild state from scratch. Use the original message timestamp.
        await self.king_manager.process_game_result(guild, game, message.created_at)
        self.leaderboard.mark_result_processed(result_key, game.winner_id)
    
    async def recalculate_from_recent(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel
    ) -> None:
        """Recalculate all streaks and state from recent messages."""
        print(f'Starting recalculation from last {config.RECENT_MESSAGE_THRESHOLD} messages...')
        
        # Store current king state for comparison
        old_king_id = self.leaderboard.current_king_id
        old_streak = self.leaderboard.current_streak
        old_ego_floor = self.leaderboard.current_king_ego_floor
        
        # Clear tracking data but keep king state for now
        self.leaderboard.clear_tracking()
        
        # Temporarily reset king state for recalculation
        self.leaderboard.reset_king()
        self.leaderboard.last_activity = None
        
        # Fetch and process messages in chronological order
        try:
            messages = []
            async for msg in channel.history(limit=config.RECENT_MESSAGE_THRESHOLD):
                if msg.author.bot:
                    continue
                messages.append(msg)
            
            # Reverse to process oldest first
            messages.reverse()
            
            print(f'Reprocessing {len(messages)} recent messages...')
            
            # Process each message
            for msg in messages:
                games = GameResult.parse_from_message(msg.content)
                if games:
                    for game in games:
                        await self.process_single_result(msg, game, guild)
                    
                    # Mark as processed
                    content_hash = self.calculate_content_hash(msg.content)
                    self.leaderboard.mark_message_processed(msg.id, content_hash)
            
            # Compare results
            new_king_id = self.leaderboard.current_king_id
            new_streak = self.leaderboard.current_streak
            
            # Check if king actually changed
            if old_king_id == new_king_id and old_king_id is not None:
                # Same king - check if we need to sync role
                print(f'Recalculation confirmed: Same king ({new_king_id}), streak: {old_streak} -> {new_streak}')
                role = await self.king_manager.get_king_role(guild)
                if role:
                    king = guild.get_member(new_king_id)
                    if king and role not in king.roles:
                        await king.add_roles(role, reason="Restoring king role after recalculation")
            elif old_king_id != new_king_id:
                # King changed - handle role transitions
                if old_king_id:
                    print(f'King changed during recalculation: {old_king_id} -> {new_king_id}')
                    await self.king_manager.remove_king_role(guild, reason="King changed during recalculation")
                else:
                    print(f'New king after recalculation: {new_king_id}')
            
            print(f'Recalculation complete. King: {self.leaderboard.current_king_id}, Streak: {self.leaderboard.current_streak}')
        
        except discord.Forbidden:
            print('Error: Bot lacks permission to read message history')
        except Exception as e:
            print(f'Error during recalculation: {e}')
    
    async def cleanup_old_tracking(self, channel: discord.TextChannel) -> None:
        """Clean up old tracked messages and results."""
        try:
            # Get recent message IDs
            recent_message_ids: Set[int] = set()
            async for msg in channel.history(limit=config.RECENT_MESSAGE_THRESHOLD):
                recent_message_ids.add(msg.id)
            
            # Find result keys to keep (from recent messages)
            keys_to_keep: Set[str] = set()
            for result_key in list(self.leaderboard.processed_results.keys()):
                msg_id_str = result_key.split(':')[0]
                msg_id = int(msg_id_str)
                if msg_id in recent_message_ids:
                    keys_to_keep.add(result_key)
            
            # Remove old results
            keys_to_remove = set(self.leaderboard.processed_results.keys()) - keys_to_keep
            for key in keys_to_remove:
                del self.leaderboard.processed_results[key]
            
            # Remove old messages
            messages_to_remove = set(self.leaderboard.processed_messages.keys()) - recent_message_ids
            for msg_id in messages_to_remove:
                del self.leaderboard.processed_messages[msg_id]
            
            if keys_to_remove or messages_to_remove:
                print(f'Cleaned up {len(keys_to_remove)} old results and {len(messages_to_remove)} old messages')
        
        except discord.Forbidden:
            print('Error: Bot lacks permission to read message history for cleanup')
        except Exception as e:
            print(f'Error during cleanup: {e}')
