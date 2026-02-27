"""
WebBattleArena - Web-enabled battle arena with real-time broadcasting
"""
from typing import Dict, List, Optional, Set
import asyncio
from datetime import datetime
from Swarm_engine import BattleArena, MetaAgent, Element, Team

class WebBattleArena(BattleArena):
    """Extended arena with WebSocket support and session management."""
    
    def __init__(self, battle_id: str, num_mobs: int = 12):
        super().__init__(num_mobs)
        self.battle_id = battle_id
        self.connected_clients: Set = set()
        self.paused = False
        self.created_at = datetime.now()
        self.spectator_mode = False
        
    async def broadcast_state(self, state: Dict):
        """Broadcast game state to all connected clients."""
        if not self.connected_clients:
            return
        
        message = {"type": "game_state", "data": state, "battle_id": self.battle_id}
        dead_clients = set()
        
        for client in self.connected_clients:
            try:
                await client.send_json(message)
            except:
                dead_clients.add(client)
        
        self.connected_clients -= dead_clients
    
    def add_client(self, websocket):
        """Register new client connection."""
        self.connected_clients.add(websocket)
    
    def remove_client(self, websocket):
        """Unregister client connection."""
        self.connected_clients.discard(websocket)
    
    def toggle_pause(self) -> bool:
        """Pause/resume battle."""
        self.paused = not self.paused
        return self.paused
    
    def tick_battle(self) -> Dict:
        """Override to respect pause state."""
        if self.paused:
            return {"paused": True, "tick": self.tick}
        return super().tick_battle()
    
    def get_replay_data(self) -> Dict:
        """Generate replay-compatible data."""
        return {
            "battle_id": self.battle_id,
            "created_at": self.created_at.isoformat(),
            "final_state": super().tick_battle(),
            "winner": self.winner,
            "total_ticks": self.tick
        }
