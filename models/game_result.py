"""
Game result parsing and validation.
Handles parsing scrimmage result messages and extracting player information.
"""
from dataclasses import dataclass
from typing import List, Tuple
import config


@dataclass
class GameResult:
    """Represents a single scrimmage game result."""
    player1_id: int
    score1: int
    score2: int
    player2_id: int
    player1_ego: int
    player2_ego: int
    
    @property
    def winner_id(self) -> int:
        """Return the ID of the winning player."""
        return self.player1_id if self.score1 > self.score2 else self.player2_id
    
    @property
    def loser_id(self) -> int:
        """Return the ID of the losing player."""
        return self.player2_id if self.score1 > self.score2 else self.player1_id
    
    @property
    def winner_ego(self) -> int:
        """Return the ego value of the winner."""
        return self.player1_ego if self.score1 > self.score2 else self.player2_ego
    
    @property
    def loser_ego(self) -> int:
        """Return the ego value of the loser."""
        return self.player2_ego if self.score1 > self.score2 else self.player1_ego
    
    @property
    def is_tie(self) -> bool:
        """Check if the game was a tie."""
        return self.score1 == self.score2
    
    def get_sorted_player_ids(self) -> Tuple[int, int]:
        """Return player IDs sorted in ascending order (for consistent result keys)."""
        return tuple(sorted([self.player1_id, self.player2_id]))
    
    @classmethod
    def parse_from_message(cls, content: str) -> List['GameResult']:
        """
        Parse all game results from a message.
        
        Args:
            content: Discord message content to parse
            
        Returns:
            List of GameResult objects (may be empty if no valid results found)
        """
        results = []
        matches = config.RESULT_PATTERN.finditer(content)
        
        for match in matches:
            try:
                player1_id = int(match.group(1))
                score1 = int(match.group(2))
                score2 = int(match.group(3))
                player2_id = int(match.group(4))
                ego_str = match.group(5)
                
                # Parse ego - can be "90" or "80/90" (with optional whitespace)
                if '/' in ego_str:
                    ego_parts = ego_str.split('/')
                    player1_ego = int(ego_parts[0].strip())
                    player2_ego = int(ego_parts[1].strip())
                else:
                    # Same ego for both players
                    player1_ego = player2_ego = int(ego_str.strip())
                
                result = cls(
                    player1_id=player1_id,
                    score1=score1,
                    score2=score2,
                    player2_id=player2_id,
                    player1_ego=player1_ego,
                    player2_ego=player2_ego
                )
                
                # Skip ties
                if not result.is_tie:
                    results.append(result)
                else:
                    print(f'Ignoring tie result: {score1}-{score2}')
                    
            except (ValueError, IndexError) as e:
                print(f'Error parsing game result: {e}')
                continue
        
        return results
