"""
Leaderboard data management and serialization.
Handles storing and formatting leaderboard state.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Optional
import discord
import config


class LeaderboardData:
    """Manages leaderboard state and serialization."""
    
    def __init__(self):
        self.best_streaks: Dict[int, int] = {}  # user_id -> best_streak
        self.best_streak_egos: Dict[int, int] = {}  # user_id -> ego_floor for their best streak
        self.current_king_id: Optional[int] = None
        self.current_streak: int = 0
        self.current_king_ego_floor: Optional[int] = None  # ego floor for current king's active streak
        self.last_activity: Optional[datetime] = None
        self.processed_messages: Dict[int, str] = {}  # message_id -> content_hash
        self.processed_results: Dict[str, int] = {}  # result_key (msg_id:p1:p2:ts) -> winner_id
    
    def update_best_streak(self, user_id: int, streak: int, ego_floor: int) -> None:
        """Update a player's best streak if the new streak is higher."""
        if user_id not in self.best_streaks or self.best_streaks[user_id] < streak:
            self.best_streaks[user_id] = streak
            self.best_streak_egos[user_id] = ego_floor
    
    def update_current_king_ego_floor(self, ego: int) -> None:
        """Update the current king's ego floor (only if lower or not set)."""
        if self.current_king_ego_floor is None or ego < self.current_king_ego_floor:
            self.current_king_ego_floor = ego
    
    def reset_king(self) -> None:
        """Reset king state (used on timeout or defeat)."""
        self.current_king_id = None
        self.current_streak = 0
        self.current_king_ego_floor = None
    
    def set_king(self, user_id: int, ego: int, streak: int = 1) -> None:
        """Set a new king with the given streak and initialize ego floor."""
        self.current_king_id = user_id
        self.current_streak = streak
        self.current_king_ego_floor = ego
    
    def increment_streak(self) -> None:
        """Increment the current king's streak."""
        self.current_streak += 1
    
    def mark_result_processed(self, result_key: str, winner_id: int) -> None:
        """Mark a game result as processed."""
        self.processed_results[result_key] = winner_id
    
    def is_result_processed(self, result_key: str) -> bool:
        """Check if a result has been processed."""
        return result_key in self.processed_results
    
    def get_processed_winner(self, result_key: str) -> Optional[int]:
        """Get the winner ID for a previously processed result."""
        return self.processed_results.get(result_key)
    
    def mark_message_processed(self, message_id: int, content_hash: str) -> None:
        """Mark a message as processed with its content hash."""
        self.processed_messages[message_id] = content_hash
    
    def is_message_unchanged(self, message_id: int, content_hash: str) -> bool:
        """Check if a message has been processed with the same content."""
        return self.processed_messages.get(message_id) == content_hash
    
    def clear_tracking(self) -> None:
        """Clear all message and result tracking (used during recalculation)."""
        self.processed_messages.clear()
        self.processed_results.clear()
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            'best_streaks': {str(k): v for k, v in self.best_streaks.items()},
            'best_streak_egos': {str(k): v for k, v in self.best_streak_egos.items()},
            'current_king_id': self.current_king_id,
            'current_streak': self.current_streak,
            'current_king_ego_floor': self.current_king_ego_floor,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'processed_messages': {str(k): v for k, v in self.processed_messages.items()},
            'processed_results': {k: v for k, v in self.processed_results.items()}
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LeaderboardData':
        """Deserialize from dictionary."""
        leaderboard = cls()
        leaderboard.best_streaks = {int(k): v for k, v in data.get('best_streaks', {}).items()}
        leaderboard.best_streak_egos = {int(k): v for k, v in data.get('best_streak_egos', {}).items()}
        leaderboard.current_king_id = data.get('current_king_id')
        leaderboard.current_streak = data.get('current_streak', 0)
        leaderboard.current_king_ego_floor = data.get('current_king_ego_floor')
        leaderboard.processed_messages = {int(k): v for k, v in data.get('processed_messages', {}).items()}
        leaderboard.processed_results = {k: int(v) for k, v in data.get('processed_results', {}).items()}
        
        last_activity_str = data.get('last_activity')
        if last_activity_str:
            dt = datetime.fromisoformat(last_activity_str)
            # Ensure timezone-aware datetime
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            leaderboard.last_activity = dt
        
        return leaderboard
    
    def to_display_message(self, guild: discord.Guild) -> str:
        """Format leaderboard as a Discord message (display only, no state)."""
        lines = [config.LEADERBOARD_HEADER, ""]
        
        # Show current king section
        if self.current_king_id and self.current_streak > 0:
            lines.append("**Current King** 👑")
            ego_info = f" (Ego: {self.current_king_ego_floor})" if self.current_king_ego_floor is not None else ""
            lines.append(f"<@{self.current_king_id}> - {self.current_streak} wins{ego_info}")
            lines.append("")
        
        # Show historical best streaks
        lines.append("**Best Streaks**")
        
        # Sort by best streak descending
        sorted_users = sorted(
            self.best_streaks.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:config.LEADERBOARD_TOP_N]
        
        if not sorted_users:
            lines.append("No games recorded yet!")
        else:
            for rank, (user_id, streak) in enumerate(sorted_users, 1):
                ego_info = f" (Ego: {self.best_streak_egos[user_id]})" if user_id in self.best_streak_egos else ""
                lines.append(f"{rank}. <@{user_id}> - {streak} wins{ego_info}")
        
        lines.append("")
        if self.last_activity:
            timestamp = int(self.last_activity.timestamp())
            lines.append(f"Last game: <t:{timestamp}:R>")
            
            # Show when current king's streak will expire
            if self.current_king_id:
                from datetime import timedelta
                expiry_time = self.last_activity + timedelta(days=config.KING_TIMEOUT_DAYS)
                expiry_timestamp = int(expiry_time.timestamp())
                lines.append(f"King expires: <t:{expiry_timestamp}:R>")
        
        return "\n".join(lines)
    
    def to_state_message(self) -> str:
        """Format app state as a collapsible spoiler message."""
        return f"{config.STATE_MESSAGE_HEADER}\n\n||```text\n{json.dumps(self.to_dict(), separators=(',', ':'))}\n```||"
    
    @classmethod
    def from_state_message(cls, content: str) -> Optional['LeaderboardData']:
        """Extract leaderboard data from state message content."""
        import re
        try:
            # Find JSON block in spoiler tags (text format)
            match = re.search(r'\|\|```text\n(.+?)\n```\|\|', content, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return cls.from_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing state message: {e}")
        return None
