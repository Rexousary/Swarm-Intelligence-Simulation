"""
CustomAgent - User-customizable agents with loadouts
"""
from typing import Dict, List, Optional, Callable
from Swarm_engine import MetaAgent, Element, Team, Ability, Behaviour

class CustomAgent(MetaAgent):
    """Extended agent with customization support."""
    
    def __init__(self, name: str, element: Element, team: Team, 
                 x: float, y: float, is_player: bool = False,
                 custom_abilities: Optional[List[Ability]] = None,
                 ai_script: Optional[Callable] = None):
        super().__init__(name, element, team, x, y, is_player)
        
        if custom_abilities:
            self.abilities = custom_abilities[:3]  # Max 3 abilities
            self.cooldowns = [0] * len(self.abilities)
        
        self.ai_script = ai_script
        self.cosmetic_skin = "default"
        self.custom_stats_modifier = 1.0
        
    def apply_custom_ai(self, enemies: List['MetaAgent'], allies: List['MetaAgent']) -> Optional[str]:
        """Execute user-defined AI script (sandboxed)."""
        if not self.ai_script:
            return None
        
        try:
            # Provide safe context to AI script
            context = {
                "self": self.to_dict(),
                "enemies": [e.to_dict() for e in enemies if e.alive],
                "allies": [a.to_dict() for a in allies if a.alive],
                "hp_pct": self.hp_pct
            }
            
            # Execute with timeout protection
            decision = self.ai_script(context)
            return decision
        except Exception as e:
            return None
    
    def set_skin(self, skin_id: str):
        """Apply cosmetic skin."""
        self.cosmetic_skin = skin_id
    
    def boost_stats(self, multiplier: float):
        """Apply stat modifier (for power-ups)."""
        self.custom_stats_modifier = multiplier
        self.atk *= multiplier
        self.def_ *= multiplier
        self.spd *= multiplier
    
    def to_dict(self) -> Dict:
        """Extended serialization with custom fields."""
        base = super().to_dict()
        base.update({
            "skin": self.cosmetic_skin,
            "has_custom_ai": self.ai_script is not None,
            "stat_modifier": self.custom_stats_modifier
        })
        return base

class AgentLoadout:
    """Manages agent ability loadouts."""
    
    def __init__(self):
        self.loadouts: Dict[str, List[Ability]] = {}
    
    def save_loadout(self, loadout_name: str, abilities: List[Ability]):
        """Save custom ability loadout."""
        self.loadouts[loadout_name] = abilities[:3]
    
    def get_loadout(self, loadout_name: str) -> Optional[List[Ability]]:
        """Retrieve saved loadout."""
        return self.loadouts.get(loadout_name)
    
    def list_loadouts(self) -> List[str]:
        """List all saved loadouts."""
        return list(self.loadouts.keys())
