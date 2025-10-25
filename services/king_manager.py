"""
King role and streak management service.
Handles Discord role assignments and streak tracking logic.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import discord
import config
from models.leaderboard import LeaderboardData
from models.game_result import GameResult


class KingManager:
    """Manages king role assignments and streak tracking."""
    
    def __init__(self, leaderboard: LeaderboardData):
        self.leaderboard = leaderboard
    
    async def get_or_create_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Get the king role, creating it if it doesn't exist."""
        role = discord.utils.get(guild.roles, name=config.ROLE_NAME)
        
        if not role:
            try:
                role = await guild.create_role(
                    name=config.ROLE_NAME,
                    reason="Auto-created by Scrim Bot"
                )
                print(f'Created role: {config.ROLE_NAME}')
            except discord.Forbidden:
                print(f'Error: Bot lacks permission to create role "{config.ROLE_NAME}"')
                return None
        
        return role
    
    def get_current_king_member(self, guild: discord.Guild, role: discord.Role) -> Optional[discord.Member]:
        """Find the member who currently has the king role (according to leaderboard state)."""
        # Check leaderboard state first - this is the source of truth
        if not self.leaderboard.current_king_id:
            return None
        
        # Get the member who should be king according to our data
        member = guild.get_member(self.leaderboard.current_king_id)
        
        # If member not found (left server), clear king state
        if not member:
            print(f'King member {self.leaderboard.current_king_id} not found in guild, resetting king state')
            self.leaderboard.reset_king()
            return None
        
        return member
    
    async def process_game_result(
        self,
        guild: discord.Guild,
        game: GameResult,
        timestamp: datetime
    ) -> None:
        """
        Process a game result and update king/streaks accordingly.
        
        Args:
            guild: Discord guild where the game occurred
            game: GameResult object with game details
            timestamp: When the game occurred
        """
        role = await self.get_or_create_role(guild)
        if not role:
            return
        
        # Get member objects
        winner = guild.get_member(game.winner_id)
        loser = guild.get_member(game.loser_id)
        
        if not winner or not loser:
            print(f'Error: Could not find members (winner={game.winner_id}, loser={game.loser_id})')
            return
        
        # Find current king
        current_king = self.get_current_king_member(guild, role)
        
        # Update king and streaks
        await self._update_king_and_streaks(role, winner, loser, current_king, timestamp, game.winner_ego)
    
    async def _update_king_and_streaks(
        self,
        role: discord.Role,
        winner: discord.Member,
        loser: discord.Member,
        current_king: Optional[discord.Member],
        timestamp: datetime,
        winner_ego: int
    ) -> None:
        """Internal method to handle king role changes and streak updates."""
        
        # Case 1: No king exists
        if not current_king:
            print(f'No king exists, crowning {winner.name} with ego {winner_ego}')
            await winner.add_roles(role, reason="Won game, became king")
            self.leaderboard.set_king(winner.id, ego=winner_ego, streak=1)
            self.leaderboard.last_activity = timestamp
            self.leaderboard.update_best_streak(winner.id, 1, winner_ego)
        
        # Case 2: Winner is already king
        elif winner == current_king:
            print(f'{winner.name} defended as king with ego {winner_ego}')
            self.leaderboard.increment_streak()
            self.leaderboard.update_current_king_ego_floor(winner_ego)  # Only updates if lower
            self.leaderboard.last_activity = timestamp
            
            # Update best streak if this is a new record
            current_ego_floor = self.leaderboard.current_king_ego_floor
            if self.leaderboard.current_streak > self.leaderboard.best_streaks.get(winner.id, 0):
                self.leaderboard.update_best_streak(winner.id, self.leaderboard.current_streak, current_ego_floor)
                print(f'New best streak for {winner.name}: {self.leaderboard.current_streak} wins (ego floor: {current_ego_floor})')
        
        # Case 3: Loser is king (king was defeated)
        elif loser == current_king:
            print(f'{winner.name} defeated king {loser.name}, new king ego: {winner_ego}')
            await loser.remove_roles(role, reason="Lost game as king")
            await winner.add_roles(role, reason="Defeated the king")
            
            # Before resetting, check if the old king achieved a new best
            old_king_id = self.leaderboard.current_king_id
            old_streak = self.leaderboard.current_streak
            old_ego_floor = self.leaderboard.current_king_ego_floor
            
            if old_streak > self.leaderboard.best_streaks.get(old_king_id, 0):
                self.leaderboard.update_best_streak(old_king_id, old_streak, old_ego_floor)
                print(f'Final best streak for {loser.name}: {old_streak} wins (ego floor: {old_ego_floor})')
            
            # Set new king
            self.leaderboard.set_king(winner.id, ego=winner_ego, streak=1)
            self.leaderboard.last_activity = timestamp
            
            # Check if new king already has a best streak
            if winner.id not in self.leaderboard.best_streaks:
                self.leaderboard.update_best_streak(winner.id, 1, winner_ego)
        
        # Case 4: Neither is king (just update best streaks if applicable)
        else:
            print(f'Non-king game: {winner.name} beat {loser.name}')
            # No role changes needed
    
    async def check_king_timeout(self, guild: discord.Guild) -> bool:
        """
        Check if the king has timed out due to inactivity.
        
        Returns:
            True if king was timed out, False otherwise
        """
        if not self.leaderboard.current_king_id or not self.leaderboard.last_activity:
            return False
        
        time_since_activity = datetime.now(timezone.utc) - self.leaderboard.last_activity
        
        if time_since_activity > timedelta(days=config.KING_TIMEOUT_DAYS):
            print(f'King {self.leaderboard.current_king_id} has timed out after {time_since_activity.days} days')
            await self.expire_king(guild)
            return True
        
        return False
    
    async def expire_king(self, guild: discord.Guild) -> None:
        """Remove king role and reset streak due to timeout."""
        if not self.leaderboard.current_king_id:
            return
        
        role = discord.utils.get(guild.roles, name=config.ROLE_NAME)
        if not role:
            print(f'Error: Role "{config.ROLE_NAME}" not found')
            return
        
        # Find and remove role from king
        king = guild.get_member(self.leaderboard.current_king_id)
        if king and role in king.roles:
            try:
                await king.remove_roles(role, reason="King expired after 3 days of inactivity")
                print(f'Removed king role from {king.name}')
            except discord.Forbidden:
                print('Error: Bot lacks permission to remove role')
        
        # Reset state
        self.leaderboard.reset_king()
    
    async def remove_king_role(self, guild: discord.Guild, reason: str = "Recalculating") -> None:
        """Remove the king role from whoever currently has it."""
        if not self.leaderboard.current_king_id:
            return
        
        role = discord.utils.get(guild.roles, name=config.ROLE_NAME)
        if not role:
            return
        
        king = guild.get_member(self.leaderboard.current_king_id)
        if king and role in king.roles:
            try:
                await king.remove_roles(role, reason=reason)
                print(f'Removed king role from {king.name} - {reason}')
            except discord.Forbidden:
                print('Error: Bot lacks permission to remove role')
