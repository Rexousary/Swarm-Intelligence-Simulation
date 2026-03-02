"""
╔══════════════════════════════════════════════════════════════════════════╗
║       BACKEND 5 — ENEMY MOB NAVIGATION & RADAR SENSOR                  ║
║  Mini-Radar · Boss Mobs · Island Grandmasters · First Strike System     ║
║  Shared Threat Map · Both Teams + Mobs Can Access                       ║
╚══════════════════════════════════════════════════════════════════════════╝

Features:
  - RADAR SENSOR: mini-radar per zone showing possible targets
      * Scans radius around each registered radar node
      * Both teams AND boss mobs can read the radar
      * Shows blip strength (distance-based) — not exact coords, only zone/direction
      * First team/mob to reach the blip location gets FIRST STRIKE bonus (+25% dmg)

  - BOSS MOB SYSTEM:
      * 3 tiers: Rogue (street-level) | Elite (zone-boss) | Grand Master (map-boss)
      * Grand Masters roam the map and generate large radar signatures
      * Island Grand Masters hold key landmarks and must be defeated to capture them
      * Bosses have radar awareness — they MOVE TOWARD detected players

  - THREAT MAP:
      * Shared tactical overlay showing danger zones
      * Each team sees all RADAR BLIPS (not exact positions, just blip zones)
      * Blip fades over time if not refreshed (stale intel)

  - FIRST STRIKE SYSTEM:
      * When a blip is detected on the map, the race begins
      * First team/boss to reach within 12 units of the blip = FIRST STRIKE
      * First Strike: +25% damage first attack, +10% speed for 3 ticks

  - RADAR JAMMER: Sand/Dark agents can deploy jammers to hide from radar
"""

import math
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
from collections import defaultdict, deque

# ─────────────────────────────────────────────────────────────────────
#  SHARED MAP DATA
# ─────────────────────────────────────────────────────────────────────

MAP_W = 200
MAP_H = 200

LANDMARKS = {
    "Parliament_Hall":  (100, 100), "Clock_Tower":      (100,  60),
    "North_Stadium":    (100,  30), "South_Stadium":    (100, 170),
    "East_Tower":       (160, 100), "West_Tower":       ( 40, 100),
    "North_Shore":      ( 50,  10), "South_Shore":      (150, 190),
    "Battle_Ground_A":  ( 60,  60), "Battle_Ground_B":  (140, 140),
    "Road_Junction_N":  (100,  75), "Road_Junction_S":  (100, 125),
    "Road_Junction_E":  (130, 100), "Road_Junction_W":  ( 70, 100),
    "Alpha_Spawn":      ( 22,  22), "Omega_Spawn":      (178, 178),
}

def dist(a, b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2)
def move_toward(pos, tgt, spd):
    d = dist(pos, tgt)
    if d < 0.5: return tgt
    r = min(spd/d, 1.0)
    return (round(pos[0]+(tgt[0]-pos[0])*r,2), round(pos[1]+(tgt[1]-pos[1])*r,2))
def clamp(pos): return (max(0.0,min(float(MAP_W),pos[0])), max(0.0,min(float(MAP_H),pos[1])))
def angle_deg(a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    return math.degrees(math.atan2(dy, dx)) % 360

def compass(angle: float) -> str:
    dirs = ["N","NE","E","SE","S","SW","W","NW","N"]
    return dirs[int((angle+22.5)//45)]

# ─────────────────────────────────────────────────────────────────────
#  RADAR CONSTANTS
# ─────────────────────────────────────────────────────────────────────

RADAR_SCAN_RADIUS   = 55.0   # range of each radar node
RADAR_BLIP_TTL      = 12     # ticks before blip goes stale
FIRST_STRIKE_RANGE  = 12.0   # distance to claim first strike
FIRST_STRIKE_BONUS  = 0.25   # +25% dmg
FIRST_STRIKE_SPEED  = 0.10   # +10% speed for 3 ticks
JAMMER_RADIUS       = 18.0   # radar jammer suppression radius
BOSS_RADAR_SIG      = 2.5    # boss signature multiplier on radar

# Radar node positions (fixed sensors across the map)
RADAR_NODES: Dict[str, Tuple[float,float]] = {
    "Radar_Parliament": (100,100),
    "Radar_North":      (100, 40),
    "Radar_South":      (100,160),
    "Radar_East":       (155,100),
    "Radar_West":       ( 45,100),
    "Radar_NW":         ( 50, 50),
    "Radar_SE":         (150,150),
}

# ─────────────────────────────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────────────────────────────

class MobTier(Enum):
    ROGUE        = "Rogue"          # Tier 1 — random street level
    ELITE        = "Elite"          # Tier 2 — zone boss
    GRAND_MASTER = "Grand Master"   # Tier 3 — holds key landmarks

class MobBehaviour(Enum):
    PATROL   = "PATROL"
    HUNT     = "HUNT"         # chasing radar blip
    GUARD    = "GUARD"        # holding a landmark
    RAMPAGE  = "RAMPAGE"      # all-out attack when HP triggered
    RETREAT  = "RETREAT"

class BlipCategory(Enum):
    PLAYER_TEAM  = "Player Team"
    ENEMY_TEAM   = "Enemy Team"
    BOSS_MOB     = "Boss Mob"
    GRANDMASTER  = "Grand Master"

# ─────────────────────────────────────────────────────────────────────
#  RADAR BLIP
# ─────────────────────────────────────────────────────────────────────

@dataclass
class RadarBlip:
    blip_id:      str
    source_id:    str
    category:     BlipCategory
    detected_pos: Tuple[float,float]   # approximate zone center, NOT exact
    exact_pos:    Tuple[float,float]   # actual position (used internally)
    radar_node:   str
    detected_tick: int
    signal_strength: float             # 0.0–1.0 (1.0 = very close to radar node)
    direction:    str                  # compass direction from radar node
    is_stale:     bool = False
    first_strike_claimed: Optional[str] = None  # team/mob that claimed it

    def age(self, current_tick: int) -> int:
        return current_tick - self.detected_tick

    def is_active(self, current_tick: int) -> bool:
        return self.age(current_tick) < RADAR_BLIP_TTL and not self.is_stale

    def strength_label(self) -> str:
        if self.signal_strength > 0.8: return "🔴 STRONG"
        if self.signal_strength > 0.5: return "🟡 MEDIUM"
        if self.signal_strength > 0.2: return "🟢 WEAK"
        return "⚪ FAINT"

    def render(self, current_tick: int) -> str:
        age   = self.age(current_tick)
        ttl   = max(0, RADAR_BLIP_TTL - age)
        stale = "⚠️ STALE" if self.is_stale else f"TTL:{ttl}t"
        fs    = f"⚡FS:{self.first_strike_claimed}" if self.first_strike_claimed else ""
        cat_icon = {
            BlipCategory.PLAYER_TEAM: "🔶",
            BlipCategory.ENEMY_TEAM:  "🔷",
            BlipCategory.BOSS_MOB:    "👹",
            BlipCategory.GRANDMASTER: "👑",
        }.get(self.category, "❓")
        return (f"  {cat_icon} [{self.blip_id}] {self.category.value:<14} "
                f"Node:[{self.radar_node:<20}] "
                f"Dir:{self.direction:<3} Zone:({self.detected_pos[0]:.0f},{self.detected_pos[1]:.0f})  "
                f"{self.strength_label():<14} {stale} {fs}")

# ─────────────────────────────────────────────────────────────────────
#  RADAR JAMMER
# ─────────────────────────────────────────────────────────────────────

@dataclass
class RadarJammer:
    jammer_id:   str
    owner_id:    str
    team:        str
    position:    Tuple[float,float]
    deployed_tick: int
    duration:    int = 15   # ticks
    radius:      float = JAMMER_RADIUS

    def is_active(self, tick: int) -> bool:
        return (tick - self.deployed_tick) < self.duration

    def suppresses(self, pos: Tuple[float,float]) -> bool:
        return dist(self.position, pos) <= self.radius

# ─────────────────────────────────────────────────────────────────────
#  BOSS MOB
# ─────────────────────────────────────────────────────────────────────

BOSS_TEMPLATES = {
    MobTier.ROGUE: {
        "hp": 200, "atk": 55, "def": 30, "spd": 6.0,
        "radar_sig": 1.0, "vision": 35.0, "hunt_range": 45.0,
        "elements": ["Fire","Water","Earth","Grass","Dark","Thunder"],
    },
    MobTier.ELITE: {
        "hp": 450, "atk": 85, "def": 60, "spd": 5.0,
        "radar_sig": 1.8, "vision": 50.0, "hunt_range": 65.0,
        "elements": ["Shadow","Magma","Storm","Void"],
    },
    MobTier.GRAND_MASTER: {
        "hp": 900, "atk": 130,"def": 90, "spd": 3.5,
        "radar_sig": BOSS_RADAR_SIG, "vision": 70.0, "hunt_range": 90.0,
        "elements": ["Chaos","Nexus","Primal"],
    },
}

@dataclass
class BossMob:
    mob_id:    str
    tier:      MobTier
    element:   str
    position:  Tuple[float, float]
    guard_point: Optional[str] = None   # landmark name if GUARD type

    hp:        float = 0.0
    max_hp:    float = 0.0
    atk:       float = 0.0
    defense:   float = 0.0
    speed:     float = 0.0
    radar_sig: float = 0.0
    vision:    float = 0.0
    hunt_range:float = 0.0

    behaviour: MobBehaviour = MobBehaviour.PATROL
    target_pos: Tuple[float,float] = field(default_factory=lambda: (100.0,100.0))
    waypoints: List[Tuple[float,float]] = field(default_factory=list)
    wp_idx:    int = 0
    kills:     int = 0
    first_strikes_won: int = 0
    jammed:    bool = False   # true if inside a jammer radius
    pos_history: deque = field(default_factory=lambda: deque(maxlen=6))

    def __post_init__(self):
        tmpl = BOSS_TEMPLATES[self.tier]
        self.max_hp     = tmpl["hp"]
        self.hp         = tmpl["hp"]
        self.atk        = tmpl["atk"]
        self.defense    = tmpl["def"]
        self.speed      = tmpl["spd"]
        self.radar_sig  = tmpl["radar_sig"]
        self.vision     = tmpl["vision"]
        self.hunt_range = tmpl["hunt_range"]

    @property
    def alive(self): return self.hp > 0

    def tier_icon(self):
        return {"Rogue":"👾","Elite":"👹","Grand Master":"👑"}.get(self.tier.value, "?")

    def hp_bar(self, width=12) -> str:
        f = round((self.hp/self.max_hp)*width)
        return "█"*f + "░"*(width-f)

    def tick(self, all_players: List[dict], radar: 'RadarSystem',
             jammers: List[RadarJammer], tick: int, log: List[str]):
        """Boss AI tick: scan radar, hunt, guard, rampage."""
        self.pos_history.append(self.position)

        # Check if jammed
        self.jammed = any(j.is_active(tick) and j.suppresses(self.position)
                          for j in jammers)

        # HP-based behaviour transitions
        if self.hp < self.max_hp * 0.25:
            self.behaviour = MobBehaviour.RAMPAGE
        elif self.hp < self.max_hp * 0.5 and self.tier == MobTier.GRAND_MASTER:
            self.behaviour = MobBehaviour.RETREAT

        # Radar-based hunting
        if not self.jammed and self.behaviour not in (MobBehaviour.GUARD,
                                                      MobBehaviour.RETREAT):
            visible_blips = radar.get_blips_near(self.position, self.vision)
            player_blips  = [b for b in visible_blips
                             if b.category in (BlipCategory.PLAYER_TEAM,
                                               BlipCategory.ENEMY_TEAM)]
            if player_blips:
                strongest = max(player_blips, key=lambda b: b.signal_strength)
                self.behaviour = MobBehaviour.HUNT
                self.target_pos = strongest.exact_pos
                log.append(f"  {self.tier_icon()} [{self.mob_id}] "
                            f"HUNTING blip [{strongest.blip_id}] "
                            f"dir {strongest.direction} "
                            f"strength {strongest.strength_label()}")

        # Movement
        if self.behaviour == MobBehaviour.GUARD and self.guard_point:
            guard_pos = LANDMARKS.get(self.guard_point, self.position)
            if dist(self.position, guard_pos) > 8:
                self.position = clamp(move_toward(self.position, guard_pos, self.speed*0.6))
            else:
                # At guard point — scan and wait
                pass

        elif self.behaviour == MobBehaviour.HUNT:
            self.position = clamp(move_toward(self.position, self.target_pos, self.speed*1.2))

        elif self.behaviour == MobBehaviour.RAMPAGE:
            # Charge nearest player
            if all_players:
                nearest_p = min(all_players, key=lambda p: dist(self.position, p["pos"]))
                self.position = clamp(move_toward(self.position, nearest_p["pos"],
                                                  self.speed * 1.5))
                log.append(f"  {self.tier_icon()} [{self.mob_id}] "
                           f"🔥RAMPAGE — charging {nearest_p['id']}!")

        elif self.behaviour == MobBehaviour.PATROL:
            # Random patrol drift
            if random.random() < 0.3:
                lm = random.choice(list(LANDMARKS.values()))
                self.target_pos = lm
            self.position = clamp(move_toward(self.position, self.target_pos, self.speed*0.5))

        elif self.behaviour == MobBehaviour.RETREAT:
            # Back to spawn or edge
            edge = (random.choice([0.0, 200.0]), random.uniform(0, 200))
            self.position = clamp(move_toward(self.position, edge, self.speed*0.8))

        # Emit radar signature (if not jammed)
        if not self.jammed:
            radar.register_signature(
                source_id  = self.mob_id,
                category   = (BlipCategory.GRANDMASTER
                              if self.tier == MobTier.GRAND_MASTER
                              else BlipCategory.BOSS_MOB),
                position   = self.position,
                multiplier = self.radar_sig,
                tick       = tick,
            )

    def render_status(self) -> str:
        jam = "📵JAMMED" if self.jammed else ""
        return (f"  {self.tier_icon()} {self.mob_id:<22} [{self.element:<10}] "
                f"HP:{self.hp_bar()}({self.hp:.0f}/{self.max_hp:.0f})  "
                f"{self.behaviour.value:<10} "
                f"Pos:({self.position[0]:.0f},{self.position[1]:.0f})  "
                f"Kills:{self.kills}  FS:{self.first_strikes_won}  {jam}")

# ─────────────────────────────────────────────────────────────────────
#  FIRST STRIKE TRACKER
# ─────────────────────────────────────────────────────────────────────

@dataclass
class FirstStrikeEvent:
    blip_id:    str
    claimer_id: str
    team:       str
    tick:       int
    location:   Tuple[float, float]
    dmg_bonus:  float = FIRST_STRIKE_BONUS
    spd_bonus:  float = FIRST_STRIKE_SPEED

    def render(self) -> str:
        return (f"  ⚡ FIRST STRIKE → [{self.claimer_id}] ({self.team}) "
                f"on blip [{self.blip_id}] @ "
                f"({self.location[0]:.0f},{self.location[1]:.0f}) "
                f"| +{self.dmg_bonus*100:.0f}% dmg | +{self.spd_bonus*100:.0f}% spd")

# ─────────────────────────────────────────────────────────────────────
#  RADAR SYSTEM  (the core of this backend)
# ─────────────────────────────────────────────────────────────────────

class RadarSystem:
    """
    The global radar that both teams AND boss mobs can read.
    Generates blips from radar nodes when entities pass within range.
    First team/mob to physically reach a blip claims First Strike.
    """
    def __init__(self):
        self.blips:         List[RadarBlip] = []
        self.blip_seq:      int = 0
        self.jammers:       List[RadarJammer] = []
        self.jammer_seq:    int = 0
        self.first_strikes: List[FirstStrikeEvent] = []
        self.fs_seq:        int = 0
        self.tick:          int = 0
        self.log:           List[str] = []

        # Stats per team
        self.detections:    Dict[str, int] = defaultdict(int)
        self.first_strike_board: Dict[str, int] = defaultdict(int)

    def register_signature(self, source_id: str, category: BlipCategory,
                           position: Tuple[float,float], multiplier: float,
                           tick: int):
        """
        Called by entities that move through the map.
        Each radar node within range creates a blip.
        """
        for node_name, node_pos in RADAR_NODES.items():
            d = dist(position, node_pos)
            if d <= RADAR_SCAN_RADIUS * multiplier:
                # Check jammer suppression
                if any(j.is_active(tick) and j.suppresses(position)
                       for j in self.jammers):
                    continue

                # Deduplicate: if same source already has recent blip from this node
                existing = next((b for b in self.blips
                                 if b.source_id == source_id and
                                    b.radar_node == node_name and
                                    b.age(tick) < 4), None)
                if existing:
                    # Refresh
                    existing.detected_tick = tick
                    existing.is_stale      = False
                    existing.signal_strength = 1.0 - (d / (RADAR_SCAN_RADIUS * multiplier))
                    continue

                # New blip
                self.blip_seq += 1
                angle    = angle_deg(node_pos, position)
                # Approximate position = snap to 10-unit grid (imprecise on purpose)
                approx_x = round(position[0] / 10) * 10
                approx_y = round(position[1] / 10) * 10
                sig      = 1.0 - (d / (RADAR_SCAN_RADIUS * multiplier))
                blip     = RadarBlip(
                    blip_id        = f"BLP{self.blip_seq:04d}",
                    source_id      = source_id,
                    category       = category,
                    detected_pos   = (float(approx_x), float(approx_y)),
                    exact_pos      = position,
                    radar_node     = node_name,
                    detected_tick  = tick,
                    signal_strength= max(0.1, sig),
                    direction      = compass(angle),
                )
                self.blips.append(blip)
                self.detections[category.value] += 1

    def scan_all(self, entities: List[dict], tick: int):
        """
        Main scan: register signatures for all entities.
        entity dict: {"id": str, "team": str, "pos": (x,y),
                       "is_boss": bool, "radar_sig": float}
        """
        self.tick = tick
        for ent in entities:
            cat = (BlipCategory.BOSS_MOB     if ent.get("is_boss") and not ent.get("is_gm") else
                   BlipCategory.GRANDMASTER  if ent.get("is_gm") else
                   BlipCategory.PLAYER_TEAM  if ent["team"] == "ALPHA" else
                   BlipCategory.ENEMY_TEAM)
            self.register_signature(
                ent["id"], cat, ent["pos"],
                ent.get("radar_sig", 1.0), tick
            )

        # Mark stale blips
        for blip in self.blips:
            if blip.age(tick) >= RADAR_BLIP_TTL - 2:
                blip.is_stale = True

        # Purge very old blips
        self.blips = [b for b in self.blips if b.age(tick) < RADAR_BLIP_TTL + 2]

    def check_first_strike(self, claimer_id: str, team: str,
                           position: Tuple[float,float], tick: int) -> Optional[FirstStrikeEvent]:
        """Check if this entity is first to reach any active blip."""
        for blip in self.blips:
            if (blip.is_active(tick) and
                    blip.first_strike_claimed is None and
                    blip.source_id != claimer_id and   # can't claim your own blip
                    dist(position, blip.exact_pos) <= FIRST_STRIKE_RANGE):
                blip.first_strike_claimed = claimer_id
                self.fs_seq += 1
                fs = FirstStrikeEvent(
                    blip_id   = blip.blip_id,
                    claimer_id= claimer_id,
                    team      = team,
                    tick      = tick,
                    location  = blip.exact_pos,
                )
                self.first_strikes.append(fs)
                self.first_strike_board[claimer_id] += 1
                self.log.append(fs.render())
                return fs
        return None

    def get_blips_near(self, pos: Tuple[float,float],
                       radius: float) -> List[RadarBlip]:
        return [b for b in self.blips
                if dist(pos, b.detected_pos) <= radius and not b.is_stale]

    def deploy_jammer(self, owner_id: str, team: str,
                      position: Tuple[float,float], tick: int):
        self.jammer_seq += 1
        jid = f"JAM{self.jammer_seq:03d}"
        jam = RadarJammer(jid, owner_id, team, position, tick)
        self.jammers.append(jam)
        self.log.append(f"  📵 RADAR JAMMER [{jid}] deployed by [{owner_id}] "
                        f"({team}) @ ({position[0]:.0f},{position[1]:.0f}) "
                        f"radius:{JAMMER_RADIUS:.0f}u dur:{jam.duration}t")
        return jam

    def purge_jammers(self, tick: int):
        self.jammers = [j for j in self.jammers if j.is_active(tick)]

    # ── Renders ──────────────────────────────────────────────────────

    def render_radar_display(self, viewer_team: str = "ALL"):
        """Full radar display — what both teams/mobs see."""
        print(f"\n{'═'*80}")
        print(f"  📡 RADAR SYSTEM DISPLAY  "
              f"| Tick {self.tick:03d}  "
              f"| Active Blips: {sum(1 for b in self.blips if b.is_active(self.tick))}"
              f"  | Jammers: {sum(1 for j in self.jammers if j.is_active(self.tick))}")
        print(f"{'═'*80}")

        active = [b for b in self.blips if b.is_active(self.tick)]
        if not active:
            print("  (no active radar blips)")
        else:
            cats = [BlipCategory.GRANDMASTER, BlipCategory.BOSS_MOB,
                    BlipCategory.PLAYER_TEAM, BlipCategory.ENEMY_TEAM]
            for cat in cats:
                cat_blips = [b for b in active if b.category == cat]
                if cat_blips:
                    print(f"\n  ── {cat.value} Blips ({len(cat_blips)}) {'─'*40}")
                    for b in cat_blips:
                        print(b.render(self.tick))

        # Radar node status
        print(f"\n  📡 Radar Nodes Status:")
        print(f"  {'Node':<25} {'Position':>14} {'Blips Detected':>16}")
        print(f"  {'─'*60}")
        for nname, npos in RADAR_NODES.items():
            node_blips = sum(1 for b in self.blips
                             if b.radar_node == nname and b.is_active(self.tick))
            print(f"  {nname:<25} ({npos[0]:3.0f},{npos[1]:3.0f})     {node_blips:>10}")

        # Jammers
        active_jams = [j for j in self.jammers if j.is_active(self.tick)]
        if active_jams:
            print(f"\n  📵 Active Jammers:")
            for j in active_jams:
                ttl = j.duration - (self.tick - j.deployed_tick)
                print(f"    [{j.jammer_id}] by [{j.owner_id}] ({j.team}) "
                      f"@ ({j.position[0]:.0f},{j.position[1]:.0f}) "
                      f"R:{j.radius:.0f}u TTL:{ttl}t")

    def render_first_strike_log(self):
        print(f"\n  ⚡ FIRST STRIKE EVENTS ({len(self.first_strikes)} total):")
        print(f"  {'─'*70}")
        if not self.first_strikes:
            print("  (none yet)")
        for fs in self.first_strikes[-10:]:
            print(fs.render())

        print(f"\n  🏆 First Strike Leaderboard:")
        board = sorted(self.first_strike_board.items(), key=lambda x: x[1], reverse=True)
        for rank, (eid, count) in enumerate(board[:8], 1):
            print(f"    #{rank}  {eid:<20}  {count} first strikes")

    def render_radar_minimap(self, width=55, height=25):
        """ASCII radar minimap showing blip positions and nodes."""
        sx = MAP_W / width
        sy = MAP_H / height
        grid = [[' ']*width for _ in range(height)]

        # Landmark markers
        lm_chars = {"Parliament_Hall":'P',"Clock_Tower":'C',"North_Stadium":'S',
                    "South_Stadium":'s',"East_Tower":'E',"West_Tower":'W',
                    "Battle_Ground_A":'A',"Battle_Ground_B":'B',
                    "Alpha_Spawn":'α',"Omega_Spawn":'ω'}
        for lm_n, (lx,ly) in LANDMARKS.items():
            gx = min(int(lx/sx), width-1)
            gy = min(int(ly/sy), height-1)
            grid[gy][gx] = lm_chars.get(lm_n, '.')

        # Radar nodes
        for nname, (nx,ny) in RADAR_NODES.items():
            gx = min(int(nx/sx), width-1)
            gy = min(int(ny/sy), height-1)
            grid[gy][gx] = 'R'

        # Blips
        blip_chars = {
            BlipCategory.PLAYER_TEAM: '▲',
            BlipCategory.ENEMY_TEAM:  '▼',
            BlipCategory.BOSS_MOB:    '!',
            BlipCategory.GRANDMASTER: '★',
        }
        for b in self.blips:
            if b.is_active(self.tick):
                gx = min(int(b.detected_pos[0]/sx), width-1)
                gy = min(int(b.detected_pos[1]/sy), height-1)
                grid[gy][gx] = blip_chars.get(b.category, '?')

        # Jammers (show suppression area edges)
        for j in self.jammers:
            if j.is_active(self.tick):
                gx = min(int(j.position[0]/sx), width-1)
                gy = min(int(j.position[1]/sy), height-1)
                grid[gy][gx] = '⊘'

        border = '─' * (width + 4)
        print(f"\n  ┌{border}┐")
        print(f"  │  RADAR MAP  Tick:{self.tick:03d}  "
              f"({'─'*(width - 24)}) │")
        for row in grid:
            print(f"  │  {''.join(row)}  │")
        print(f"  ├{border}┤")
        print(f"  │  R=RadarNode  ▲=Alpha  ▼=Omega  !=Boss  ★=GrandMaster  "
              f"⊘=Jammer  P=Parliament  {'─'*2} │")
        print(f"  └{border}┘")

    def detection_summary(self) -> str:
        lines = ["\n  📊 Radar Detection Summary:"]
        for cat, count in self.detections.items():
            lines.append(f"    {cat:<20} {count:>5} detections")
        return "\n".join(lines)

    def flush_log(self):
        out = self.log[:]
        self.log.clear()
        return out

# ─────────────────────────────────────────────────────────────────────
#  ISLAND GRAND MASTER REGISTRY
# ─────────────────────────────────────────────────────────────────────

class GrandMasterRegistry:
    """
    Manages the 3 Island Grand Masters.
    Each holds a key landmark and must be defeated before the team
    can fully capture it and gain its special bonus.
    """
    def __init__(self):
        self.grand_masters: List[BossMob] = []
        self._spawn_grand_masters()

    def _spawn_grand_masters(self):
        configs = [
            ("GM_Ironclad",  "Nexus",   "Parliament_Hall",  (100.0, 100.0)),
            ("GM_StormLord", "Primal",  "Clock_Tower",      (100.0,  60.0)),
            ("GM_VoidKing",  "Chaos",   "East_Tower",       (160.0, 100.0)),
        ]
        for mob_id, element, guard, pos in configs:
            gm = BossMob(mob_id, MobTier.GRAND_MASTER, element, pos, guard_point=guard)
            gm.behaviour = MobBehaviour.GUARD
            self.grand_masters.append(gm)

    def tick_all(self, all_players: List[dict], radar: RadarSystem,
                 jammers: List[RadarJammer], tick: int, log: List[str]):
        for gm in self.grand_masters:
            if gm.alive:
                gm.tick(all_players, radar, jammers, tick, log)

    def render_status(self):
        print(f"\n  ── 👑 ISLAND GRAND MASTERS ─────────────────────────────────")
        for gm in self.grand_masters:
            alive_str = "ALIVE" if gm.alive else "💀 DEFEATED"
            print(gm.render_status())
            print(f"    Guards: [{gm.guard_point}]  Status: {alive_str}")

    def get_entity_list(self) -> List[dict]:
        return [{"id": gm.mob_id, "team": "MOB", "pos": gm.position,
                 "is_boss": True, "is_gm": True, "radar_sig": gm.radar_sig}
                for gm in self.grand_masters if gm.alive]

# ─────────────────────────────────────────────────────────────────────
#  DEMO
# ─────────────────────────────────────────────────────────────────────

def run_mob_navigation_demo():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║         BACKEND 5 — ENEMY MOB NAVIGATION & RADAR SYSTEM DEMO           ║
║  Radar Sensor · Boss Mobs · Grand Masters · First Strike · Jammers      ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)

    radar    = RadarSystem()
    gm_reg   = GrandMasterRegistry()

    # Rogue & Elite mobs
    rogue_mobs = [
        BossMob(f"Rogue-{i:02d}", MobTier.ROGUE,
                random.choice(["Fire","Dark","Earth","Grass"]),
                (random.uniform(30,170), random.uniform(30,170)))
        for i in range(4)
    ]
    elite_mobs = [
        BossMob("Elite_Magma",  MobTier.ELITE, "Magma",  (80.0, 80.0)),
        BossMob("Elite_Void",   MobTier.ELITE, "Void",   (120.0,120.0)),
    ]
    all_boss_mobs = rogue_mobs + elite_mobs

    # Player agents (simplified positions)
    alpha_players = [
        {"id":"Ignis-Prime", "team":"ALPHA","pos":(30.0,30.0),  "radar_sig":1.0},
        {"id":"AquaVex",     "team":"ALPHA","pos":(35.0,28.0),  "radar_sig":1.0},
        {"id":"Volt-Surge",  "team":"ALPHA","pos":(28.0,35.0),  "radar_sig":1.0},
        {"id":"TerraKnight", "team":"ALPHA","pos":(32.0,32.0),  "radar_sig":1.0},
    ]
    omega_players = [
        {"id":"Sylvan-Wraith","team":"OMEGA","pos":(170.0,170.0),"radar_sig":1.0},
        {"id":"DustSerpent",  "team":"OMEGA","pos":(175.0,168.0),"radar_sig":1.0},
        {"id":"ZephyrBlade",  "team":"OMEGA","pos":(168.0,175.0),"radar_sig":1.0},
        {"id":"Voidwalker",   "team":"OMEGA","pos":(172.0,172.0),"radar_sig":0.3}, # stealth
    ]

    # Simulate player movement toward parliament
    def advance_players(players, direction, amount):
        for p in players:
            p["pos"] = (p["pos"][0]+direction[0]*amount,
                        p["pos"][1]+direction[1]*amount)

    print("  Spawning Grand Masters, Elites, Rogues...\n")
    gm_reg.render_status()

    for t in range(1, 35):
        tick_log = []

        # Move players
        advance_players(alpha_players, (1.0, 1.0), 4.0)
        advance_players(omega_players, (-1.0,-1.0),4.0)

        # Clamp
        for p in alpha_players + omega_players:
            p["pos"] = (max(0,min(200,p["pos"][0])), max(0,min(200,p["pos"][1])))

        # Radar scan — all entities
        all_entities = (alpha_players + omega_players +
                        gm_reg.get_entity_list() +
                        [{"id":m.mob_id,"team":"MOB","pos":m.position,
                          "is_boss":True,"is_gm":False,"radar_sig":m.radar_sig}
                         for m in all_boss_mobs if m.alive])
        radar.scan_all(all_entities, t)

        # Boss ticks
        all_player_list = alpha_players + omega_players
        gm_reg.tick_all(all_player_list, radar, radar.jammers, t, tick_log)
        for mob in all_boss_mobs:
            if mob.alive:
                mob.tick(all_player_list, radar, radar.jammers, t, tick_log)

        # First strike checks
        for p in alpha_players + omega_players:
            fs = radar.check_first_strike(p["id"], p["team"], p["pos"], t)
            if fs:
                tick_log.append(f"  🏆 First Strike bonus applied to {p['id']}!")

        # Special events
        if t == 5:
            print(f"\n  ⚡ [EVENT T{t}] DustSerpent deploys RADAR JAMMER!")
            radar.deploy_jammer("DustSerpent", "OMEGA", omega_players[1]["pos"], t)

        if t == 10:
            print(f"\n  ⚡ [EVENT T{t}] Voidwalker hides in shadows (low sig already)")
            print(f"  ⚡ [EVENT T{t}] Elite_Void transitions to RAMPAGE!")
            elite_mobs[1].hp = elite_mobs[1].max_hp * 0.24   # trigger rampage

        # Purge
        radar.purge_jammers(t)

        # Print log
        for line in tick_log:
            print(line)
        for line in radar.flush_log():
            print(line)

        # Full display at key ticks
        if t in (1, 10, 20, 34):
            radar.render_radar_display()
            radar.render_radar_minimap(width=52, height=22)

    # End
    radar.render_first_strike_log()
    gm_reg.render_status()
    print(radar.detection_summary())
    print(f"\n  Total radar blips generated this session: {radar.blip_seq}")
    print(f"  Total first strikes:                      {len(radar.first_strikes)}\n")

if __name__ == "__main__":
    run_mob_navigation_demo()
