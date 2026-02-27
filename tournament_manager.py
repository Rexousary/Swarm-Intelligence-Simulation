"""
TournamentManager - Competitive matchmaking and tournaments
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
from web_arena import WebBattleArena

class Match:
    """Represents a single match."""
    
    def __init__(self, match_id: str, player1: str, player2: str):
        self.match_id = match_id
        self.player1 = player1
        self.player2 = player2
        self.winner: Optional[str] = None
        self.score: Tuple[int, int] = (0, 0)
        self.started_at = datetime.now()
        self.ended_at: Optional[datetime] = None
        self.replay_data: Optional[Dict] = None
    
    def complete(self, winner: str, score: Tuple[int, int], replay: Dict):
        """Mark match as complete."""
        self.winner = winner
        self.score = score
        self.ended_at = datetime.now()
        self.replay_data = replay
    
    def to_dict(self) -> Dict:
        return {
            "match_id": self.match_id,
            "player1": self.player1,
            "player2": self.player2,
            "winner": self.winner,
            "score": self.score,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None
        }

class TournamentManager:
    """Manages tournaments and matchmaking."""
    
    def __init__(self):
        self.active_matches: Dict[str, Match] = {}
        self.completed_matches: List[Match] = []
        self.leaderboard: Dict[str, Dict] = {}
        self.queue: List[str] = []
    
    def add_to_queue(self, player_id: str):
        """Add player to matchmaking queue."""
        if player_id not in self.queue:
            self.queue.append(player_id)
    
    def create_match(self) -> Optional[Match]:
        """Create match from queue."""
        if len(self.queue) < 2:
            return None
        
        p1, p2 = self.queue.pop(0), self.queue.pop(0)
        match_id = f"match_{len(self.active_matches)}_{int(datetime.now().timestamp())}"
        match = Match(match_id, p1, p2)
        self.active_matches[match_id] = match
        return match
    
    def complete_match(self, match_id: str, winner: str, score: Tuple[int, int], replay: Dict):
        """Complete and record match."""
        match = self.active_matches.pop(match_id, None)
        if not match:
            return
        
        match.complete(winner, score, replay)
        self.completed_matches.append(match)
        self._update_leaderboard(match)
    
    def _update_leaderboard(self, match: Match):
        """Update player rankings."""
        for player in [match.player1, match.player2]:
            if player not in self.leaderboard:
                self.leaderboard[player] = {"wins": 0, "losses": 0, "rating": 1000}
            
            if player == match.winner:
                self.leaderboard[player]["wins"] += 1
                self.leaderboard[player]["rating"] += 25
            else:
                self.leaderboard[player]["losses"] += 1
                self.leaderboard[player]["rating"] -= 15
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get top players."""
        sorted_players = sorted(
            self.leaderboard.items(),
            key=lambda x: x[1]["rating"],
            reverse=True
        )
        return [
            {"player": p, **stats}
            for p, stats in sorted_players[:limit]
        ]
    
    def get_match_history(self, player_id: str) -> List[Dict]:
        """Get player's match history."""
        return [
            m.to_dict() for m in self.completed_matches
            if m.player1 == player_id or m.player2 == player_id
        ]
    
    def save_replay(self, match_id: str, filepath: str):
        """Save match replay to file."""
        match = next((m for m in self.completed_matches if m.match_id == match_id), None)
        if match and match.replay_data:
            with open(filepath, 'w') as f:
                json.dump(match.replay_data, f, indent=2)

class BracketTournament:
    """Single/double elimination bracket."""
    
    def __init__(self, tournament_id: str, players: List[str]):
        self.tournament_id = tournament_id
        self.players = players
        self.rounds: List[List[Match]] = []
        self.winner: Optional[str] = None
        self._generate_bracket()
    
    def _generate_bracket(self):
        """Generate tournament bracket."""
        current_round = []
        for i in range(0, len(self.players), 2):
            if i + 1 < len(self.players):
                match = Match(f"{self.tournament_id}_r0_m{i//2}", 
                            self.players[i], self.players[i+1])
                current_round.append(match)
        self.rounds.append(current_round)
    
    def advance_winner(self, match_id: str, winner: str):
        """Advance winner to next round."""
        # Find match and advance winner
        for round_idx, round_matches in enumerate(self.rounds):
            for match in round_matches:
                if match.match_id == match_id:
                    match.winner = winner
                    self._create_next_round(round_idx)
                    return
    
    def _create_next_round(self, completed_round: int):
        """Create next bracket round."""
        winners = [m.winner for m in self.rounds[completed_round] if m.winner]
        if len(winners) == 1:
            self.winner = winners[0]
            return
        
        if len(winners) >= 2 and len(self.rounds) == completed_round + 1:
            next_round = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    match = Match(f"{self.tournament_id}_r{completed_round+1}_m{i//2}",
                                winners[i], winners[i+1])
                    next_round.append(match)
            self.rounds.append(next_round)
