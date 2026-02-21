"""
MetaSwarm Engine — AI Swarm Agent Battle System
4v4 Elemental Metahuman MMORPG Battle Backend
"""

import math
import random
import time
import json
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple

# ─────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────

class Element(Enum):
    # Team Alpha
    FIRE    = "fire"
    WATER   = "water"
    THUNDER = "thunder"
    EARTH   = "earth"
    # Team Beta
    GRASS   = "grass"
    SAND    = "sand"
    FLYING  = "flying"
    DARK    = "dark"

class Behaviour(Enum):
    ROAM    = "roam"
    SEARCH  = "search"
    ATTACK  = "attack"
    DEFEND  = "defend"
    RETREAT = "retreat"
    FLANK   = "flank"

class Team(Enum):
    ALPHA = "alpha"   # Fire / Water / Thunder / Earth
    BETA  = "beta"    # Grass / Sand / Flying / Dark

# ─────────────────────────────────────────────
#  ELEMENTAL MATCHUPS  (attacker → {target: multiplier})
# ─────────────────────────────────────────────

ELEMENTAL_CHART: Dict[Element, Dict[Element, float]] = {
    Element.FIRE:    {Element.GRASS: 2.0, Element.EARTH: 1.5, Element.WATER: 0.5, Element.SAND: 0.8},
    Element.WATER:   {Element.FIRE: 2.0,  Element.SAND: 1.5,  Element.THUNDER: 0.7, Element.GRASS: 0.8},
    Element.THUNDER: {Element.WATER: 2.0, Element.FLYING: 2.0, Element.EARTH: 0.5, Element.GRASS: 1.0},
    Element.EARTH:   {Element.THUNDER: 2.0, Element.FIRE: 0.8, Element.GRASS: 0.8, Element.FLYING: 0.3},
    Element.GRASS:   {Element.WATER: 2.0, Element.SAND: 2.0, Element.FIRE: 0.5, Element.FLYING: 0.8},
    Element.SAND:    {Element.THUNDER: 1.5, Element.FIRE: 0.7, Element.WATER: 0.7, Element.GRASS: 0.5},
    Element.FLYING:  {Element.GRASS: 1.5, Element.EARTH: 2.0, Element.THUNDER: 0.5, Element.DARK: 0.8},
    Element.DARK:    {Element.THUNDER: 1.5, Element.FIRE: 1.2, Element.GRASS: 0.9, Element.WATER: 0.9},
}

# ─────────────────────────────────────────────
#  MAP LAYOUT
# ─────────────────────────────────────────────

@dataclass
class MapZone:
    name: str
    x: float; y: float          # centre
    radius: float
    strategic_value: int        # 1-10
    is_highground: bool = False
    is_chokepoint: bool = False

MAP_ZONES = [
    MapZone("Parliament_Core",     400, 300, 60,  10, False, True),
    MapZone("Clock_Tower",         550, 150, 30,   7, True,  False),
    MapZone("North_Stadium",       250, 100, 50,   5, False, False),
    MapZone("South_Stadium",       550, 500, 50,   5, False, False),
    MapZone("East_Road_Network",   700, 300, 40,   4, False, True),
    MapZone("West_Shoreline",      100, 300, 45,   3, False, False),
    MapZone("Alpha_Spawn",          60,  60, 35,   1, False, False),
    MapZone("Beta_Spawn",          740, 540, 35,   1, False, False),
    MapZone("High_Tower_NE",       680, 120, 25,   6, True,  False),
    MapZone("High_Tower_SW",       120, 480, 25,   6, True,  False),
    MapZone("Battle_Ground_West",  200, 400, 55,   8, False, False),
    MapZone("Battle_Ground_East",  600, 200, 55,   8, False, False),
]

MAP_WIDTH  = 800
MAP_HEIGHT = 600

# ─────────────────────────────────────────────
#  ELEMENT ABILITY DEFINITIONS
# ─────────────────────────────────────────────

@dataclass
class Ability:
    name: str
    damage: float
    cooldown: int          # ticks
    range_: float
    aoe_radius: float
    description: str
    buff_self: Dict = field(default_factory=dict)

ELEMENT_ABILITIES: Dict[Element, List[Ability]] = {
    Element.FIRE: [
        Ability("Inferno Burst",  55, 3, 120, 35, "AoE fire explosion",),
        Ability("Flame Dash",     20, 2,  80,  0, "Dash leaving fire trail", {"speed": 1.8}),
        Ability("Magma Prison",   35, 6, 100, 50, "Slow + burn zone"),
    ],
    Element.WATER: [
        Ability("Tidal Wave",     45, 4, 130, 60, "Wide AoE knockback wave"),
        Ability("Hydro Shield",    0, 5,   0,  0, "Absorb 40 damage", {"shield": 40}),
        Ability("Whirlpool",      30, 3,  90, 40, "Pull enemies inward"),
    ],
    Element.THUNDER: [
        Ability("Lightning Strike", 70, 4, 180,  0, "Single target heavy hit"),
        Ability("Storm Field",      25, 3,  80, 55, "AoE slow + damage"),
        Ability("Static Jump",       0, 2, 150,  0, "Teleport to target spot", {"speed": 2.2}),
    ],
    Element.EARTH: [
        Ability("Seismic Slam",   60, 5, 100, 70, "Massive ground shockwave"),
        Ability("Stone Fortress",  0, 7,   0,  0, "Fortify position +50 def", {"defense": 50}),
        Ability("Rock Barrage",   35, 2, 140,  0, "Ranged stone projectile"),
    ],
    Element.GRASS: [
        Ability("Vine Whip",      40, 3, 110, 30, "Root and damage"),
        Ability("Photosynthesis",  0, 6,   0,  0, "Heal 45 HP", {"heal": 45}),
        Ability("Spore Cloud",    15, 4,  80, 65, "Blind + poison AoE"),
    ],
    Element.SAND: [
        Ability("Sand Storm",     35, 4, 120, 75, "Large AoE visibility reduce"),
        Ability("Quicksand Pit",  25, 5, 100, 45, "Immobilise enemies"),
        Ability("Desert Mirage",   0, 8,   0,  0, "Cloak for 3 ticks", {"stealth": 3}),
    ],
    Element.FLYING: [
        Ability("Gale Slash",     50, 3, 160,  0, "High-speed aerial strike"),
        Ability("Cyclone Lift",   30, 5, 100, 40, "Lift + scatter enemies"),
        Ability("Tailwind",        0, 4,   0,  0, "Boost ally speed", {"team_speed": 1.5}),
    ],
    Element.DARK: [
        Ability("Shadow Strike",  65, 4, 130,  0, "Stealth assassin hit"),
        Ability("Void Drain",     30, 3, 100, 35, "Drain HP to self"),
        Ability("Fear Pulse",     15, 6,  80, 80, "Force enemies to flee"),
    ],
}

# ─────────────────────────────────────────────
#  AGENT CLASS
# ─────────────────────────────────────────────

class MetaAgent:
    AGENT_STATS = {
        Element.FIRE:    {"hp": 180, "atk": 90, "def": 50, "spd": 4.2, "role": "Assault"},
        Element.WATER:   {"hp": 220, "atk": 70, "def": 80, "spd": 3.5, "role": "Support-Tank"},
        Element.THUNDER: {"hp": 160, "atk": 100,"def": 45, "spd": 5.0, "role": "Skirmisher"},
        Element.EARTH:   {"hp": 260, "atk": 75, "def": 100,"spd": 2.8, "role": "Tank"},
        Element.GRASS:   {"hp": 200, "atk": 65, "def": 70, "spd": 3.8, "role": "Support"},
        Element.SAND:    {"hp": 170, "atk": 80, "def": 60, "spd": 4.5, "role": "Disruptor"},
        Element.FLYING:  {"hp": 155, "atk": 95, "def": 40, "spd": 5.5, "role": "Flanker"},
        Element.DARK:    {"hp": 175, "atk": 105,"def": 50, "spd": 4.8, "role": "Assassin"},
    }

    def __init__(self, name: str, element: Element, team: Team,
                 x: float, y: float, is_player: bool = False):
        self.name       = name
        self.element    = element
        self.team       = team
        self.x          = x
        self.y          = y
        self.is_player  = is_player

        stats = self.AGENT_STATS[element]
        self.max_hp  = stats["hp"]
        self.hp      = self.max_hp
        self.atk     = stats["atk"]
        self.def_    = stats["def"]
        self.spd     = stats["spd"]
        self.role    = stats["role"]

        self.abilities      = ELEMENT_ABILITIES[element]
        self.cooldowns      = [0] * len(self.abilities)
        self.behaviour      = Behaviour.ROAM
        self.target: Optional['MetaAgent'] = None
        self.current_zone: Optional[MapZone] = None
        self.alive          = True
        self.kills          = 0
        self.damage_dealt   = 0
        self.damage_taken   = 0

        # Temporary buffs
        self.shield         = 0
        self.stealth_ticks  = 0
        self.speed_mult     = 1.0
        self.defense_buff   = 0

        # Swarm memory
        self.threat_memory: Dict[str, float] = {}   # agent_name → threat score
        self.ally_signals: List[str]         = []   # signals from allies
        self.last_known_enemy_pos: Optional[Tuple[float, float]] = None

        # Strategy weights (can evolve)
        self.aggression  = self._base_aggression()
        self.cohesion    = 0.5       # how much to stick near allies
        self.risk_averse = self._base_risk()

    def _base_aggression(self) -> float:
        aggressive = {Element.FIRE, Element.THUNDER, Element.DARK, Element.FLYING}
        return 0.75 if self.element in aggressive else 0.4

    def _base_risk(self) -> float:
        defensive = {Element.EARTH, Element.WATER, Element.GRASS}
        return 0.6 if self.element in defensive else 0.3

    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp

    def distance_to(self, other: 'MetaAgent') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def distance_to_point(self, x: float, y: float) -> float:
        return math.hypot(self.x - x, self.y - y)

    def elemental_multiplier(self, target: 'MetaAgent') -> float:
        table = ELEMENTAL_CHART.get(self.element, {})
        return table.get(target.element, 1.0)

    def compute_damage(self, ability: Ability, target: 'MetaAgent') -> float:
        mult  = self.elemental_multiplier(target)
        base  = ability.damage * (self.atk / 80.0)
        mitig = max(0, target.def_ + target.defense_buff - 20)
        raw   = base * mult - mitig * 0.3
        jitter = random.uniform(0.85, 1.15)
        return max(5.0, raw * jitter)

    def receive_damage(self, amount: float) -> float:
        if self.stealth_ticks > 0:
            amount *= 0.1           # stealth drastically reduces damage
        if self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
        self.hp = max(0, self.hp - amount)
        self.damage_taken += amount
        if self.hp <= 0:
            self.alive = False
        return amount

    def heal(self, amount: float):
        self.hp = min(self.max_hp, self.hp + amount)

    def ready_abilities(self) -> List[Tuple[int, Ability]]:
        return [(i, ab) for i, ab in enumerate(self.abilities) if self.cooldowns[i] == 0 and ab.damage > 0]

    def best_ability_vs(self, target: 'MetaAgent') -> Optional[Tuple[int, Ability]]:
        candidates = self.ready_abilities()
        if not candidates:
            return None
        return max(candidates, key=lambda ia: self.compute_damage(ia[1], target))

    def use_ability(self, idx: int, target: Optional['MetaAgent'] = None) -> Dict:
        ab = self.abilities[idx]
        self.cooldowns[idx] = ab.cooldown
        result = {"caster": self.name, "ability": ab.name, "element": self.element.value}

        # apply buffs to self
        for buff_key, val in ab.buff_self.items():
            if buff_key == "shield":   self.shield += val
            elif buff_key == "heal":   self.heal(val)
            elif buff_key == "speed":  self.speed_mult = val
            elif buff_key == "stealth":self.stealth_ticks = val
            elif buff_key == "defense":self.defense_buff += val
            elif buff_key == "team_speed": result["team_buff"] = {"speed": val}

        # damage
        if target and target.alive and ab.damage > 0:
            dmg = self.compute_damage(ab, target)
            actual = target.receive_damage(dmg)
            self.damage_dealt += actual
            if not target.alive:
                self.kills += 1
            result.update({"target": target.name, "damage": round(actual, 1),
                            "multiplier": self.elemental_multiplier(target),
                            "target_hp_remaining": round(target.hp, 1),
                            "target_alive": target.alive})
        return result

    def tick_cooldowns(self):
        self.cooldowns = [max(0, c - 1) for c in self.cooldowns]
        if self.stealth_ticks > 0: self.stealth_ticks -= 1
        if self.speed_mult > 1.0:  self.speed_mult = max(1.0, self.speed_mult - 0.1)
        if self.defense_buff > 0:  self.defense_buff = max(0, self.defense_buff - 5)

    def to_dict(self) -> Dict:
        return {
            "name": self.name, "element": self.element.value,
            "team": self.team.value, "role": self.role,
            "hp": round(self.hp, 1), "max_hp": self.max_hp,
            "hp_pct": round(self.hp_pct, 2),
            "x": round(self.x, 1), "y": round(self.y, 1),
            "behaviour": self.behaviour.value,
            "alive": self.alive, "kills": self.kills,
            "damage_dealt": round(self.damage_dealt, 1),
            "damage_taken": round(self.damage_taken, 1),
            "shield": round(self.shield, 1),
            "stealth": self.stealth_ticks > 0,
            "target": self.target.name if self.target else None,
            "zone": self.current_zone.name if self.current_zone else None,
        }


# ─────────────────────────────────────────────
#  SWARM INTELLIGENCE
# ─────────────────────────────────────────────

class SwarmBrain:
    """
    Governs an entire team's collective behaviour.
    Implements: Roam → Search → Coordinate Attack → Defend → Retreat
    """

    def __init__(self, team: Team, agents: List[MetaAgent]):
        self.team   = team
        self.agents = agents
        self.tick   = 0
        self.strategy_phase = "early"   # early / mid / late
        self.objective: Optional[MapZone] = None
        self.formation = "spread"       # spread / wedge / pincer / fortify

    @property
    def alive_agents(self) -> List[MetaAgent]:
        return [a for a in self.agents if a.alive]

    def avg_hp_pct(self) -> float:
        alive = self.alive_agents
        if not alive: return 0.0
        return sum(a.hp_pct for a in alive) / len(alive)

    def centroid(self) -> Tuple[float, float]:
        alive = self.alive_agents
        if not alive: return (MAP_WIDTH/2, MAP_HEIGHT/2)
        return (sum(a.x for a in alive)/len(alive), sum(a.y for a in alive)/len(alive))

    def update_phase(self, total_ticks: int):
        if total_ticks < 60:   self.strategy_phase = "early"
        elif total_ticks < 150: self.strategy_phase = "mid"
        else:                  self.strategy_phase = "late"

    def pick_objective(self):
        """Choose a strategic map zone based on phase."""
        if self.strategy_phase == "early":
            # contest high ground or clock tower first
            targets = [z for z in MAP_ZONES if z.is_highground]
        elif self.strategy_phase == "mid":
            # push toward parliament
            targets = [z for z in MAP_ZONES if z.strategic_value >= 8]
        else:
            # all-out parliament siege or defence
            targets = [z for z in MAP_ZONES if z.strategic_value == 10]

        if targets:
            self.objective = random.choice(targets)

    def signal_allies(self, sender: MetaAgent, signal: str):
        for a in self.alive_agents:
            if a is not sender:
                a.ally_signals.append(signal)

    def decide_behaviour(self, agent: MetaAgent, enemies: List[MetaAgent]):
        """Core swarm intelligence per-agent behaviour decision."""
        visible_enemies = [e for e in enemies if e.alive and
                           agent.distance_to(e) < 200 and e.stealth_ticks == 0]

        avg_hp   = self.avg_hp_pct()
        n_alive  = len(self.alive_agents)
        n_enemy  = len([e for e in enemies if e.alive])

        # ── Retreat if critically low ──
        if agent.hp_pct < 0.20:
            agent.behaviour = Behaviour.RETREAT
            agent.target    = None
            self.signal_allies(agent, f"{agent.name}:needs_help")
            return

        # ── Defend if allies signalled need help ──
        if "needs_help" in " ".join(agent.ally_signals) and agent.hp_pct > 0.5:
            weak_allies = [a for a in self.alive_agents if a.hp_pct < 0.3 and a is not agent]
            if weak_allies:
                agent.behaviour = Behaviour.DEFEND
                agent.target    = min(weak_allies, key=lambda a: a.hp_pct)
                agent.ally_signals.clear()
                return

        # ── Swarm number advantage: coordinate attack ──
        if n_alive > n_enemy and visible_enemies:
            # focus-fire weakest enemy
            agent.target    = min(visible_enemies, key=lambda e: e.hp)
            agent.behaviour = Behaviour.ATTACK
            return

        # ── Elemental counter strategy ──
        if visible_enemies:
            # prefer target we have type advantage over
            favored = [e for e in visible_enemies if agent.elemental_multiplier(e) >= 1.5]
            if favored:
                agent.target    = min(favored, key=lambda e: e.hp)
                agent.behaviour = Behaviour.ATTACK
                return

            # general attack closest
            agent.target    = min(visible_enemies, key=agent.distance_to)
            agent.behaviour = Behaviour.ATTACK
            return

        # ── Search using last known position ──
        if agent.last_known_enemy_pos:
            agent.behaviour = Behaviour.SEARCH
            agent.target    = None
            return

        # ── Roam toward objective ──
        agent.behaviour = Behaviour.ROAM
        agent.target    = None
        agent.ally_signals.clear()

    def execute_movement(self, agent: MetaAgent, enemies: List[MetaAgent], dt: float = 1.0):
        """Move agent based on current behaviour."""
        speed = agent.spd * agent.speed_mult * dt

        if agent.behaviour == Behaviour.ATTACK and agent.target and agent.target.alive:
            dist = agent.distance_to(agent.target)
            best_range = max(ab.range_ for ab in agent.abilities)
            if dist > best_range * 0.85:
                self._move_toward(agent, agent.target.x, agent.target.y, speed)

        elif agent.behaviour == Behaviour.RETREAT:
            # move away from nearest enemy
            if enemies:
                nearest = min([e for e in enemies if e.alive], key=agent.distance_to, default=None)
                if nearest:
                    dx = agent.x - nearest.x; dy = agent.y - nearest.y
                    dist = max(1, math.hypot(dx, dy))
                    agent.x = max(0, min(MAP_WIDTH,  agent.x + (dx/dist) * speed * 1.5))
                    agent.y = max(0, min(MAP_HEIGHT, agent.y + (dy/dist) * speed * 1.5))

        elif agent.behaviour == Behaviour.DEFEND and agent.target:
            self._move_toward(agent, agent.target.x, agent.target.y, speed)

        elif agent.behaviour == Behaviour.SEARCH and agent.last_known_enemy_pos:
            tx, ty = agent.last_known_enemy_pos
            if agent.distance_to_point(tx, ty) < 15:
                agent.last_known_enemy_pos = None
            else:
                self._move_toward(agent, tx, ty, speed)

        elif agent.behaviour == Behaviour.ROAM:
            if self.objective:
                self._move_toward(agent, self.objective.x, self.objective.y, speed * 0.7)
            else:
                # wander
                angle = random.uniform(0, 2 * math.pi)
                agent.x = max(0, min(MAP_WIDTH,  agent.x + math.cos(angle) * speed))
                agent.y = max(0, min(MAP_HEIGHT, agent.y + math.sin(angle) * speed))

        # Flying gets slight elevation bonus — modeled as wider map reach
        if agent.element == Element.FLYING and agent.behaviour == Behaviour.ATTACK:
            speed_bonus = 1.3
            # already handled above, conceptually faster approach

        # Update zone awareness
        agent.current_zone = self._nearest_zone(agent)

    def _move_toward(self, agent: MetaAgent, tx: float, ty: float, speed: float):
        dx = tx - agent.x; dy = ty - agent.y
        dist = max(1, math.hypot(dx, dy))
        agent.x = max(0, min(MAP_WIDTH,  agent.x + (dx/dist) * speed))
        agent.y = max(0, min(MAP_HEIGHT, agent.y + (dy/dist) * speed))

    def _nearest_zone(self, agent: MetaAgent) -> Optional[MapZone]:
        best, best_d = None, float('inf')
        for z in MAP_ZONES:
            d = agent.distance_to_point(z.x, z.y)
            if d < z.radius and d < best_d:
                best, best_d = z, d
        return best

    def execute_combat(self, agent: MetaAgent, enemies: List[MetaAgent]) -> Optional[Dict]:
        """Attempt ability use if in range of target."""
        if agent.behaviour not in (Behaviour.ATTACK, Behaviour.DEFEND):
            # try utility ability if low HP
            if agent.hp_pct < 0.4:
                for i, ab in enumerate(agent.abilities):
                    if agent.cooldowns[i] == 0 and "heal" in ab.buff_self:
                        return agent.use_ability(i)
                    if agent.cooldowns[i] == 0 and "shield" in ab.buff_self:
                        return agent.use_ability(i)
            return None

        target = agent.target
        if not target or not target.alive:
            return None

        dist = agent.distance_to(target)
        best = agent.best_ability_vs(target)
        if best:
            idx, ab = best
            if dist <= ab.range_:
                # update last known pos for teammates
                for ally in self.alive_agents:
                    ally.last_known_enemy_pos = (target.x, target.y)
                return agent.use_ability(idx, target)

        # fallback: utility
        for i, ab in enumerate(agent.abilities):
            if agent.cooldowns[i] == 0 and ab.damage == 0:
                return agent.use_ability(i)

        return None


# ─────────────────────────────────────────────
#  MOB AGENTS (AI-Controlled pedestrian metahumans)
# ─────────────────────────────────────────────

class MobAgent:
    def __init__(self, mob_id: int):
        self.mob_id  = mob_id
        self.name    = f"Mob_{mob_id:03d}"
        self.x       = random.uniform(50, MAP_WIDTH - 50)
        self.y       = random.uniform(50, MAP_HEIGHT - 50)
        self.hp      = random.randint(60, 120)
        self.max_hp  = self.hp
        self.atk     = random.randint(15, 35)
        self.spd     = random.uniform(1.5, 3.0)
        self.alive   = True
        self.element = random.choice(list(Element))
        self.aggro_target: Optional[str] = None

    def wander(self):
        angle = random.uniform(0, 2 * math.pi)
        self.x = max(0, min(MAP_WIDTH,  self.x + math.cos(angle) * self.spd))
        self.y = max(0, min(MAP_HEIGHT, self.y + math.sin(angle) * self.spd))

    def aggro_check(self, players: List[MetaAgent]) -> Optional[MetaAgent]:
        """Aggro any player within 80 units."""
        for p in players:
            if p.alive and math.hypot(self.x - p.x, self.y - p.y) < 80:
                return p
        return None

    def to_dict(self):
        return {"name": self.name, "x": round(self.x,1), "y": round(self.y,1),
                "hp": self.hp, "max_hp": self.max_hp, "alive": self.alive,
                "element": self.element.value}


# ─────────────────────────────────────────────
#  BATTLE ARENA
# ─────────────────────────────────────────────

class BattleArena:
    def __init__(self, num_mobs: int = 12):
        self.tick  = 0
        self.log: List[Dict] = []
        self.winner: Optional[str] = None

        # ── Team ALPHA ──
        self.alpha = [
            MetaAgent("Pyro_Rex",   Element.FIRE,    Team.ALPHA, 80,  80),
            MetaAgent("AquaVeil",   Element.WATER,   Team.ALPHA, 60, 100),
            MetaAgent("VoltStrike", Element.THUNDER, Team.ALPHA,100,  60),
            MetaAgent("TerraGuard", Element.EARTH,   Team.ALPHA, 70,  90),
        ]
        self.alpha[0].is_player = True      # PLAYER controls Pyro_Rex

        # ── Team BETA ──
        self.beta = [
            MetaAgent("Verdant",   Element.GRASS,  Team.BETA, 720, 520),
            MetaAgent("DuneRaider",Element.SAND,   Team.BETA, 740, 500),
            MetaAgent("SkyHunter", Element.FLYING, Team.BETA, 700, 540),
            MetaAgent("VoidWraith",Element.DARK,   Team.BETA, 730, 510),
        ]

        # ── Swarm Brains ──
        self.brain_alpha = SwarmBrain(Team.ALPHA, self.alpha)
        self.brain_beta  = SwarmBrain(Team.BETA,  self.beta)

        # ── Mobs ──
        self.mobs: List[MobAgent] = [MobAgent(i) for i in range(num_mobs)]

        # ── Strategy state ──
        self.alpha_score = 0
        self.beta_score  = 0

    @property
    def all_players(self) -> List[MetaAgent]:
        return self.alpha + self.beta

    def zone_control(self) -> Dict[str, Optional[str]]:
        """Which team controls each zone."""
        control = {}
        for zone in MAP_ZONES:
            counts = {Team.ALPHA: 0, Team.BETA: 0}
            for a in self.all_players:
                if a.alive and a.distance_to_point(zone.x, zone.y) < zone.radius:
                    counts[a.team] += 1
            if counts[Team.ALPHA] > counts[Team.BETA]:
                control[zone.name] = "alpha"
                self.alpha_score += zone.strategic_value * 0.1
            elif counts[Team.BETA] > counts[Team.ALPHA]:
                control[zone.name] = "beta"
                self.beta_score += zone.strategic_value * 0.1
            else:
                control[zone.name] = None
        return control

    def tick_battle(self) -> Dict:
        if self.winner:
            return {"winner": self.winner}

        self.tick += 1
        events: List[Dict] = []

        # ── Update strategy phase ──
        self.brain_alpha.update_phase(self.tick)
        self.brain_beta.update_phase(self.tick)

        # ── Pick objectives every 20 ticks ──
        if self.tick % 20 == 1:
            self.brain_alpha.pick_objective()
            self.brain_beta.pick_objective()

        # ── Process each team ──
        for brain, friends, foes in [
            (self.brain_alpha, self.alpha, self.beta),
            (self.brain_beta,  self.beta,  self.alpha),
        ]:
            for agent in brain.alive_agents:
                agent.tick_cooldowns()
                brain.decide_behaviour(agent, foes)
                brain.execute_movement(agent, foes)
                ev = brain.execute_combat(agent, foes)
                if ev:
                    events.append(ev)

        # ── Mob tick ──
        for mob in self.mobs:
            if not mob.alive: continue
            target = mob.aggro_check(self.all_players)
            if target:
                dmg = random.uniform(5, mob.atk)
                target.receive_damage(dmg)
                events.append({"mob_attack": mob.name, "target": target.name,
                                "damage": round(dmg, 1)})
                # mob dies if player retaliates (simplified)
                if random.random() < 0.25:
                    mob.alive = False
            else:
                mob.wander()

        # ── Zone scoring ──
        zone_ctrl = self.zone_control()

        # ── Check win conditions ──
        alpha_alive = [a for a in self.alpha if a.alive]
        beta_alive  = [a for a in self.beta  if a.alive]

        if not alpha_alive:
            self.winner = "BETA"
        elif not beta_alive:
            self.winner = "ALPHA"
        elif self.tick >= 300:
            self.winner = "ALPHA" if self.alpha_score >= self.beta_score else "BETA"

        return {
            "tick":          self.tick,
            "phase":         self.brain_alpha.strategy_phase,
            "alpha_agents":  [a.to_dict() for a in self.alpha],
            "beta_agents":   [a.to_dict() for a in self.beta],
            "mobs":          [m.to_dict() for m in self.mobs if m.alive],
            "events":        events,
            "zone_control":  zone_ctrl,
            "alpha_score":   round(self.alpha_score, 1),
            "beta_score":    round(self.beta_score, 1),
            "winner":        self.winner,
            "alpha_objective": self.brain_alpha.objective.name if self.brain_alpha.objective else None,
            "beta_objective":  self.brain_beta.objective.name  if self.brain_beta.objective  else None,
        }

    def run_full_battle(self, max_ticks: int = 300) -> Dict:
        """Run entire battle and return final report."""
        tick_snapshots = []
        while self.tick < max_ticks and not self.winner:
            state = self.tick_battle()
            if self.tick % 10 == 0 or state.get("events"):
                tick_snapshots.append(state)

        final = {
            "winner": self.winner,
            "total_ticks": self.tick,
            "alpha_score": round(self.alpha_score, 1),
            "beta_score":  round(self.beta_score, 1),
            "agent_stats": {
                a.name: {
                    "kills": a.kills,
                    "damage_dealt": round(a.damage_dealt, 1),
                    "damage_taken": round(a.damage_taken, 1),
                    "survived": a.alive,
                    "hp_remaining": round(a.hp, 1),
                }
                for a in self.all_players
            },
            "snapshots": tick_snapshots[-10:],   # last 10 snapshots
        }
        return final


# ─────────────────────────────────────────────
#  PLAYER COMMAND INTERFACE
# ─────────────────────────────────────────────

class PlayerController:
    """Handles player decisions for Pyro_Rex (or any player-controlled agent)."""

    def __init__(self, arena: BattleArena):
        self.arena  = arena
        self.player = next(a for a in arena.alpha if a.is_player)

    def available_commands(self) -> Dict:
        abilities = [
            {"idx": i, "name": ab.name, "ready": self.player.cooldowns[i] == 0,
             "cooldown_remaining": self.player.cooldowns[i],
             "description": ab.description}
            for i, ab in enumerate(self.player.abilities)
        ]
        enemies_in_sight = [
            a.to_dict() for a in self.arena.beta
            if a.alive and self.player.distance_to(a) < 200
        ]
        return {
            "player": self.player.to_dict(),
            "abilities": abilities,
            "visible_enemies": enemies_in_sight,
            "strategy_phase": self.arena.brain_alpha.strategy_phase,
            "ally_status": [a.to_dict() for a in self.arena.alpha if a is not self.player],
        }

    def move(self, dx: float, dy: float):
        spd = self.player.spd * self.player.speed_mult
        self.player.x = max(0, min(MAP_WIDTH,  self.player.x + dx * spd))
        self.player.y = max(0, min(MAP_HEIGHT, self.player.y + dy * spd))

    def use_ability(self, ability_idx: int, target_name: Optional[str] = None) -> Dict:
        target = None
        if target_name:
            target = next((a for a in self.arena.beta if a.name == target_name and a.alive), None)
        return self.player.use_ability(ability_idx, target)

    def set_behaviour(self, behaviour: str):
        try:
            self.player.behaviour = Behaviour(behaviour)
        except ValueError:
            pass

    def devise_strategy(self, strategy: str) -> str:
        """Player devises a high-level team strategy."""
        strategies = {
            "rush":     {"aggression": 0.9, "cohesion": 0.3, "formation": "wedge"},
            "defend":   {"aggression": 0.2, "cohesion": 0.8, "formation": "fortify"},
            "pincer":   {"aggression": 0.6, "cohesion": 0.4, "formation": "pincer"},
            "spread":   {"aggression": 0.5, "cohesion": 0.2, "formation": "spread"},
            "berserk":  {"aggression": 1.0, "cohesion": 0.1, "formation": "wedge"},
        }
        s = strategies.get(strategy, strategies["spread"])
        for agent in self.arena.alpha:
            agent.aggression = s["aggression"]
            agent.cohesion   = s["cohesion"]
        self.arena.brain_alpha.formation = s["formation"]
        return (f"Strategy [{strategy.upper()}] activated! "
                f"Formation: {s['formation']}, Aggression: {s['aggression']}")


# ─────────────────────────────────────────────
#  DEMO / MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  MetaSwarm Engine — 4v4 Elemental Battle")
    print("=" * 60)

    arena = BattleArena(num_mobs=15)
    player = PlayerController(arena)

    print(f"\n[PLAYER] You control: {player.player.name} ({player.player.element.value.upper()})")
    print(f"[TEAM ALPHA] Fire / Water / Thunder / Earth")
    print(f"[TEAM BETA]  Grass / Sand / Flying / Dark")
    print(f"\nMap: Parliament Complex — {MAP_WIDTH}x{MAP_HEIGHT}")
    print(f"Zones: {len(MAP_ZONES)}, Mobs: {len(arena.mobs)}")

    # Demo: Player sets strategy
    msg = player.devise_strategy("pincer")
    print(f"\n[STRATEGY] {msg}")

    # Run battle
    print("\n[BATTLE START]\n")
    result = arena.run_full_battle(max_ticks=200)

    print(f"Winner: {result['winner']}")
    print(f"Ticks:  {result['total_ticks']}")
    print(f"Score — Alpha: {result['alpha_score']} | Beta: {result['beta_score']}")
    print("\n--- Agent Performance ---")
    for name, stats in result["agent_stats"].items():
        status = "ALIVE" if stats["survived"] else "DEFEATED"
        print(f"  {name:15s} | Kills: {stats['kills']} | "
              f"Dmg Dealt: {stats['damage_dealt']:6.1f} | "
              f"Dmg Taken: {stats['damage_taken']:6.1f} | {status}")

    # Save last battle state to JSON
    with open("/home/claude/metaswarm/battle_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("\n[SAVED] battle_result.json")
