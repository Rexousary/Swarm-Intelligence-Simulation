"""
MultiplayerController - Handles multiple human players
"""
from typing import Dict, Optional, List
from Swarm_engine import PlayerController, BattleArena, MetaAgent, Behaviour
from web_arena import WebBattleArena

class MultiplayerController(PlayerController):
    """Extended controller for multiplayer sessions."""
    
    def __init__(self, arena: WebBattleArena, player_id: str, agent: MetaAgent):
        self.arena = arena
        self.player = agent
        self.player_id = player_id
        self.command_queue: List[Dict] = []
        self.last_command_tick = 0
        
    def validate_command(self, command: Dict) -> bool:
        """Validate player command to prevent cheating."""
        cmd_type = command.get("type")
        
        # Rate limiting: 1 command per tick
        if self.arena.tick == self.last_command_tick:
            return False
        
        if cmd_type == "move":
            dx, dy = command.get("dx", 0), command.get("dy", 0)
            return abs(dx) <= 1 and abs(dy) <= 1
        
        elif cmd_type == "ability":
            idx = command.get("ability_idx")
            return idx is not None and 0 <= idx < len(self.player.abilities)
        
        elif cmd_type == "behaviour":
            return command.get("behaviour") in [b.value for b in Behaviour]
        
        return False
    
    def execute_command(self, command: Dict) -> Dict:
        """Execute validated player command."""
        if not self.validate_command(command):
            return {"error": "Invalid command"}
        
        self.last_command_tick = self.arena.tick
        cmd_type = command["type"]
        
        if cmd_type == "move":
            self.move(command["dx"], command["dy"])
            return {"success": True, "action": "move"}
        
        elif cmd_type == "ability":
            result = self.use_ability(command["ability_idx"], command.get("target"))
            return {"success": True, "action": "ability", "result": result}
        
        elif cmd_type == "behaviour":
            self.set_behaviour(command["behaviour"])
            return {"success": True, "action": "behaviour"}
        
        elif cmd_type == "strategy":
            msg = self.devise_strategy(command["strategy"])
            return {"success": True, "action": "strategy", "message": msg}
        
        return {"error": "Unknown command"}

class SessionManager:
    """Manages multiple player sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, MultiplayerController] = {}
    
    def create_session(self, arena: WebBattleArena, player_id: str, agent: MetaAgent) -> MultiplayerController:
        """Create new player session."""
        controller = MultiplayerController(arena, player_id, agent)
        self.sessions[player_id] = controller
        return controller
    
    def get_session(self, player_id: str) -> Optional[MultiplayerController]:
        """Retrieve player session."""
        return self.sessions.get(player_id)
    
    def remove_session(self, player_id: str):
        """Remove player session."""
        self.sessions.pop(player_id, None)
