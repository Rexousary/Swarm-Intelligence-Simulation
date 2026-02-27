"""
WebSwarmBrain - Enhanced AI with custom strategies
"""
from typing import Dict, List, Optional, Callable
from Swarm_engine import SwarmBrain, Team, MetaAgent, MAP_ZONES

class WebSwarmBrain(SwarmBrain):
    """Extended swarm brain with custom strategies."""
    
    def __init__(self, team: Team, agents: List[MetaAgent]):
        super().__init__(team, agents)
        self.custom_strategies: Dict[str, Dict] = {}
        self.strategy_history: List[str] = []
        self.learning_enabled = False
        self.performance_metrics: Dict[str, float] = {}
    
    def register_strategy(self, name: str, config: Dict):
        """Register custom player-defined strategy."""
        self.custom_strategies[name] = {
            "aggression": config.get("aggression", 0.5),
            "cohesion": config.get("cohesion", 0.5),
            "formation": config.get("formation", "spread"),
            "priority": config.get("priority", "balanced"),  # balanced/offensive/defensive
            "custom_logic": config.get("logic", None)
        }
    
    def apply_strategy(self, strategy_name: str):
        """Apply registered strategy to team."""
        if strategy_name not in self.custom_strategies:
            return False
        
        strategy = self.custom_strategies[strategy_name]
        self.formation = strategy["formation"]
        
        for agent in self.agents:
            agent.aggression = strategy["aggression"]
            agent.cohesion = strategy["cohesion"]
        
        self.strategy_history.append(strategy_name)
        return True
    
    def evaluate_strategy_performance(self) -> Dict[str, float]:
        """Evaluate current strategy effectiveness."""
        alive_count = len(self.alive_agents)
        avg_hp = self.avg_hp_pct()
        total_kills = sum(a.kills for a in self.agents)
        total_damage = sum(a.damage_dealt for a in self.agents)
        
        score = (alive_count * 25) + (avg_hp * 30) + (total_kills * 20) + (total_damage * 0.1)
        
        if self.strategy_history:
            current_strategy = self.strategy_history[-1]
            self.performance_metrics[current_strategy] = score
        
        return {
            "score": score,
            "alive": alive_count,
            "avg_hp": avg_hp,
            "kills": total_kills,
            "damage": total_damage
        }
    
    def get_best_strategy(self) -> Optional[str]:
        """Get highest performing strategy."""
        if not self.performance_metrics:
            return None
        return max(self.performance_metrics.items(), key=lambda x: x[1])[0]
    
    def adaptive_strategy_switch(self):
        """Auto-switch strategy based on battle state."""
        if not self.learning_enabled:
            return
        
        avg_hp = self.avg_hp_pct()
        alive_ratio = len(self.alive_agents) / len(self.agents)
        
        # Defensive if low HP
        if avg_hp < 0.3 or alive_ratio < 0.5:
            for agent in self.alive_agents:
                agent.aggression = 0.2
                agent.risk_averse = 0.8
            self.formation = "fortify"
        
        # Aggressive if winning
        elif avg_hp > 0.7 and alive_ratio > 0.75:
            for agent in self.alive_agents:
                agent.aggression = 0.9
                agent.risk_averse = 0.2
            self.formation = "wedge"

class StrategyMarketplace:
    """Share and download community strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, Dict] = {}
        self.ratings: Dict[str, List[int]] = {}
    
    def upload_strategy(self, author: str, name: str, config: Dict):
        """Upload strategy to marketplace."""
        strategy_id = f"{author}_{name}"
        self.strategies[strategy_id] = {
            "author": author,
            "name": name,
            "config": config,
            "downloads": 0
        }
        self.ratings[strategy_id] = []
    
    def download_strategy(self, strategy_id: str) -> Optional[Dict]:
        """Download strategy from marketplace."""
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["downloads"] += 1
            return self.strategies[strategy_id]["config"]
        return None
    
    def rate_strategy(self, strategy_id: str, rating: int):
        """Rate strategy (1-5 stars)."""
        if strategy_id in self.ratings and 1 <= rating <= 5:
            self.ratings[strategy_id].append(rating)
    
    def get_top_strategies(self, limit: int = 10) -> List[Dict]:
        """Get top-rated strategies."""
        ranked = []
        for sid, strategy in self.strategies.items():
            ratings = self.ratings.get(sid, [])
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            ranked.append({
                "id": sid,
                "name": strategy["name"],
                "author": strategy["author"],
                "rating": avg_rating,
                "downloads": strategy["downloads"]
            })
        
        return sorted(ranked, key=lambda x: (x["rating"], x["downloads"]), reverse=True)[:limit]
