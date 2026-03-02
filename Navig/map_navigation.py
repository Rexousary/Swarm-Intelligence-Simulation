"""
╔══════════════════════════════════════════════════════════════════════════╗
║       BACKEND 4 — MAP NAVIGATION ENGINE                                 ║
║  Full Map Access · Location Sharing · Red Flare Signals                 ║
║  Fog of War · Team-Only Visibility · Rogue Mob Awareness                ║
╚══════════════════════════════════════════════════════════════════════════╝

Features:
  - Full 200×200 Parliament City map with all zones, roads, landmarks
  - Fog of War per team — each team only sees what their agents reveal
  - Location Ping / Red Flare system:
      * Player or agent fires a RED FLARE at their position
      * Flare BLINKS (visible on ticks 0,2,4,6... → disappears tick 8)
      * Visible ONLY to: same-team members + nearby Rogue Mobs in range
      * Generates a chat relay code: [FLARE:AgentID:X:Y:TICK]
  - Shared map state — agents broadcast their explored tiles to teammates
  - Real-time minimap ASCII renderer (40×20 view)
  - Zone entry/exit events
  - Path overlay — draw A* routes on minimap
  - Landmark capture state overlay
  - Emergency signal relay (lost agent auto-fires flare + chat code)
"""

import math
import heapq
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
from collections import deque, defaultdict

# ─────────────────────────────────────────────────────────────────────
#  MAP CONSTANTS  (shared with all backends)
# ─────────────────────────────────────────────────────────────────────
MAP_W = 200
MAP_H = 200

LANDMARKS: Dict[str, Tuple[float, float]] = {
    "Parliament_Hall":  (100, 100),
    "Clock_Tower":      (100,  60),
    "North_Stadium":    (100,  30),
    "South_Stadium":    (100, 170),
    "East_Tower":       (160, 100),
    "West_Tower":       ( 40, 100),
    "North_Shore":      ( 50,  10),
    "South_Shore":      (150, 190),
    "Battle_Ground_A":  ( 60,  60),
    "Battle_Ground_B":  (140, 140),
    "Road_Junction_N":  (100,  75),
    "Road_Junction_S":  (100, 125),
    "Road_Junction_E":  (130, 100),
    "Road_Junction_W":  ( 70, 100),
    "Alpha_Spawn":      ( 22,  22),
    "Omega_Spawn":      (178, 178),
}

ROAD_GRAPH: Dict[str, List[str]] = {
    "Alpha_Spawn":     ["Road_Junction_W", "Battle_Ground_A", "North_Shore"],
    "Omega_Spawn":     ["Road_Junction_E", "Battle_Ground_B", "South_Shore"],
    "Road_Junction_N": ["Parliament_Hall", "Clock_Tower", "Road_Junction_W", "Road_Junction_E"],
    "Road_Junction_S": ["Parliament_Hall", "Road_Junction_W", "Road_Junction_E", "South_Stadium"],
    "Road_Junction_E": ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S", "East_Tower"],
    "Road_Junction_W": ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S", "West_Tower"],
    "Parliament_Hall": ["Road_Junction_N", "Road_Junction_S", "Road_Junction_E", "Road_Junction_W"],
    "Clock_Tower":     ["Road_Junction_N", "North_Stadium"],
    "North_Stadium":   ["Clock_Tower", "North_Shore"],
    "South_Stadium":   ["Road_Junction_S", "South_Shore"],
    "East_Tower":      ["Road_Junction_E", "Battle_Ground_B"],
    "West_Tower":      ["Road_Junction_W", "Battle_Ground_A"],
    "Battle_Ground_A": ["West_Tower", "Alpha_Spawn", "Road_Junction_W"],
    "Battle_Ground_B": ["East_Tower", "Omega_Spawn", "Road_Junction_E"],
    "North_Shore":     ["Alpha_Spawn", "North_Stadium"],
    "South_Shore":     ["Omega_Spawn", "South_Stadium"],
}

ZONE_BOUNDS = {
    "Parliament_Core": (85, 85, 115, 115),
    "Clock_Tower":     (90, 50, 110,  70),
    "North_Stadium":   (75, 15, 125,  45),
    "South_Stadium":   (75,155, 125, 185),
    "East_Tower":      (145,85, 175, 115),
    "West_Tower":      (25,  85,  55, 115),
    "Battle_A":        (45,  45,  75,  75),
    "Battle_B":        (125,125, 155, 155),
    "North_Shore":     (0,   0,   80,  20),
    "South_Shore":     (120,180, 200, 200),
}

KEY_POINTS = ["Parliament_Hall", "Clock_Tower", "North_Stadium",
              "South_Stadium", "East_Tower", "West_Tower"]

VISION_RADIUS   = 25.0   # how far each agent sees
FLARE_DURATION  = 8      # ticks flare stays active
FLARE_BLINK     = 2      # blink every N ticks
FLARE_RADIUS    = 45.0   # how far flare is visible
MOB_FLARE_RANGE = 30.0   # rogue mobs can see flare within this range

# ─────────────────────────────────────────────────────────────────────
#  MATH
# ─────────────────────────────────────────────────────────────────────

def dist(a, b): return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
def move_toward(pos, tgt, spd):
    d = dist(pos, tgt)
    if d < 0.5: return tgt
    r = min(spd/d, 1.0)
    return (round(pos[0]+(tgt[0]-pos[0])*r, 2), round(pos[1]+(tgt[1]-pos[1])*r, 2))
def clamp(pos): return (max(0.0,min(float(MAP_W),pos[0])), max(0.0,min(float(MAP_H),pos[1])))

def nearest_landmark(pos):
    return min(LANDMARKS.keys(), key=lambda k: dist(pos, LANDMARKS[k]))

def get_zone(pos):
    x, y = pos
    for name, (x1,y1,x2,y2) in ZONE_BOUNDS.items():
        if x1<=x<=x2 and y1<=y<=y2: return name
    return "Open_Field"

# ─────────────────────────────────────────────────────────────────────
#  A*  PATHFINDER
# ─────────────────────────────────────────────────────────────────────

def a_star(start_lm: str, goal_lm: str) -> List[str]:
    if start_lm == goal_lm: return [start_lm]
    if start_lm not in ROAD_GRAPH: return [start_lm, goal_lm]
    def h(n): return dist(LANDMARKS[n], LANDMARKS[goal_lm])
    open_q = [(h(start_lm), start_lm)]
    came   = {}
    g      = {start_lm: 0.0}
    while open_q:
        _, cur = heapq.heappop(open_q)
        if cur == goal_lm:
            path = []
            while cur in came:
                path.append(cur); cur = came[cur]
            path.append(start_lm)
            return list(reversed(path))
        for nb in ROAD_GRAPH.get(cur, []):
            tg = g[cur] + dist(LANDMARKS[cur], LANDMARKS[nb])
            if tg < g.get(nb, float('inf')):
                came[nb] = cur; g[nb] = tg
                heapq.heappush(open_q, (tg+h(nb), nb))
    return [start_lm, goal_lm]

def path_coords(start_pos, goal_lm) -> List[Tuple[float,float]]:
    slm   = nearest_landmark(start_pos)
    nodes = a_star(slm, goal_lm)
    coords = [LANDMARKS[n] for n in nodes]
    if coords and dist(start_pos, coords[0]) > 5:
        coords.insert(0, start_pos)
    return coords

# ─────────────────────────────────────────────────────────────────────
#  RED FLARE SIGNAL
# ─────────────────────────────────────────────────────────────────────

@dataclass
class FlareSignal:
    flare_id:   str
    sender_id:  str
    team:       str
    position:   Tuple[float, float]
    fired_tick: int
    message:    str = ""          # optional attached message
    is_sos:     bool = False       # true = emergency/lost signal
    relay_code: str = ""           # [FLARE:sender:X:Y:tick]

    def __post_init__(self):
        x, y = self.position
        self.relay_code = (f"[FLARE:{self.sender_id}:"
                           f"{x:.0f}:{y:.0f}:{self.fired_tick}]")

    def is_active(self, current_tick: int) -> bool:
        return (current_tick - self.fired_tick) < FLARE_DURATION

    def is_visible(self, current_tick: int) -> bool:
        """Blinks: visible on even offset ticks."""
        if not self.is_active(current_tick): return False
        offset = current_tick - self.fired_tick
        return (offset % FLARE_BLINK) == 0

    def can_see(self, observer_pos: Tuple[float,float],
                observer_team: str, is_mob: bool = False) -> bool:
        """Visibility rules: same team OR nearby rogue mob."""
        d = dist(observer_pos, self.position)
        if observer_team == self.team:
            return d <= FLARE_RADIUS
        if is_mob:
            return d <= MOB_FLARE_RANGE
        return False   # enemy players cannot see flares

    def render(self, current_tick: int) -> str:
        visible = self.is_visible(current_tick)
        blink   = "🔴" if visible else "  "
        sos_tag = " 🆘SOS" if self.is_sos else ""
        age     = current_tick - self.fired_tick
        ttl     = FLARE_DURATION - age
        return (f"  {blink} FLARE [{self.flare_id}] "
                f"by {self.sender_id} ({self.team}) "
                f"@ ({self.position[0]:.0f},{self.position[1]:.0f}) "
                f"| {self.relay_code} | TTL:{ttl}t{sos_tag}")

# ─────────────────────────────────────────────────────────────────────
#  FOG OF WAR  (per-team explored tile grid)
# ─────────────────────────────────────────────────────────────────────

FOG_TILE = 5   # each tile represents 5×5 map units

class FogOfWar:
    """
    Tracks which map tiles each team has explored.
    Tiles are revealed when an agent enters vision radius.
    """
    def __init__(self, team: str):
        self.team    = team
        self.cols    = MAP_W // FOG_TILE
        self.rows    = MAP_H // FOG_TILE
        # 0 = unexplored | 1 = explored (seen) | 2 = currently visible
        self.grid: List[List[int]] = [[0]*self.cols for _ in range(self.rows)]
        self.explored_pct = 0.0

    def reveal(self, center: Tuple[float,float], radius: float = VISION_RADIUS):
        cx, cy = int(center[0]//FOG_TILE), int(center[1]//FOG_TILE)
        tile_r = int(radius // FOG_TILE) + 1
        revealed = 0
        for dy in range(-tile_r, tile_r+1):
            for dx in range(-tile_r, tile_r+1):
                tx, ty = cx+dx, cy+dy
                if 0 <= tx < self.cols and 0 <= ty < self.rows:
                    world_x = tx * FOG_TILE + FOG_TILE//2
                    world_y = ty * FOG_TILE + FOG_TILE//2
                    if dist(center, (world_x, world_y)) <= radius:
                        if self.grid[ty][tx] == 0:
                            revealed += 1
                        self.grid[ty][tx] = 2
        total = self.cols * self.rows
        explored = sum(1 for row in self.grid for v in row if v > 0)
        self.explored_pct = (explored / total) * 100
        return revealed

    def decay_visible(self):
        """After each tick, currently-visible (2) fades to explored (1)."""
        for row in self.grid:
            for i, v in enumerate(row):
                if v == 2:
                    row[i] = 1

    def is_visible(self, pos: Tuple[float,float]) -> bool:
        tx = int(pos[0] // FOG_TILE)
        ty = int(pos[1] // FOG_TILE)
        if 0 <= tx < self.cols and 0 <= ty < self.rows:
            return self.grid[ty][tx] == 2
        return False

    def is_explored(self, pos: Tuple[float,float]) -> bool:
        tx = int(pos[0] // FOG_TILE)
        ty = int(pos[1] // FOG_TILE)
        if 0 <= tx < self.cols and 0 <= ty < self.rows:
            return self.grid[ty][tx] >= 1
        return False

    def merge_from(self, other: 'FogOfWar'):
        """Share exploration data from an ally's fog map."""
        for ry in range(self.rows):
            for rx in range(self.cols):
                if other.grid[ry][rx] > self.grid[ry][rx]:
                    self.grid[ry][rx] = other.grid[ry][rx]

# ─────────────────────────────────────────────────────────────────────
#  MAP AGENT
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MapAgent:
    agent_id:  str
    team:      str
    position:  Tuple[float, float]
    speed:     float = 7.0
    vision:    float = VISION_RADIUS
    is_mob:    bool  = False

    waypoints:    List[Tuple[float,float]] = field(default_factory=list)
    wp_idx:       int = 0
    is_lost:      bool = False
    last_seen_pos: Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    pos_history:  deque = field(default_factory=lambda: deque(maxlen=10))
    ticks_stuck:  int = 0
    flare_fired:  int = 0   # last tick a flare was fired

    zone_history: List[str] = field(default_factory=list)
    explored_landmarks: Set[str] = field(default_factory=set)

    def __post_init__(self):
        self.last_seen_pos = self.position

    def tick_move(self, fog: FogOfWar, flare_manager: 'FlareManager',
                  tick: int, log: List[str]):
        self.pos_history.append(self.position)

        # Move along waypoints
        if self.waypoints and self.wp_idx < len(self.waypoints):
            tgt = self.waypoints[self.wp_idx]
            self.position = clamp(move_toward(self.position, tgt, self.speed))
            if dist(self.position, tgt) < 2.5:
                self.wp_idx += 1
        else:
            # Idle: small drift
            jx = random.uniform(-0.5, 0.5)
            jy = random.uniform(-0.5, 0.5)
            self.position = clamp((self.position[0]+jx, self.position[1]+jy))

        # Reveal fog
        fog.reveal(self.position, self.vision)

        # Zone detection
        zone = get_zone(self.position)
        lm   = nearest_landmark(self.position)
        if zone not in self.zone_history:
            self.zone_history.append(zone)
            log.append(f"  🗺️  [{self.agent_id}] entered zone [{zone}]")
        if lm not in self.explored_landmarks and dist(self.position, LANDMARKS[lm]) < 15:
            self.explored_landmarks.add(lm)
            log.append(f"  📍 [{self.agent_id}] discovered landmark [{lm}]")

        # Stuck / lost detection
        if len(self.pos_history) >= 8:
            spread = max(dist(self.pos_history[0], p) for p in list(self.pos_history)[1:])
            if spread < 1.5:
                self.ticks_stuck += 1
                if self.ticks_stuck >= 10 and not self.is_lost:
                    self.is_lost = True
                    self.ticks_stuck = 0
                    log.append(f"  ⚠️  [{self.agent_id}] LOST at "
                               f"({self.position[0]:.0f},{self.position[1]:.0f})!")
                    # Auto-fire SOS flare
                    if tick - self.flare_fired > FLARE_DURATION:
                        flare_manager.fire_flare(
                            self.agent_id, self.team, self.position, tick,
                            is_sos=True,
                            message=f"{self.agent_id} is LOST — sending SOS!",
                            log=log
                        )
                        self.flare_fired = tick
            else:
                self.ticks_stuck = 0
                if self.is_lost:
                    self.is_lost = False
                    log.append(f"  ✅ [{self.agent_id}] recovered from LOST state")

        self.last_seen_pos = self.position

    def navigate_to(self, goal_lm: str, log: List[str]):
        self.waypoints = path_coords(self.position, goal_lm)
        self.wp_idx    = 0
        log.append(f"  🧭 [{self.agent_id}] navigating → [{goal_lm}] "
                   f"({len(self.waypoints)} waypoints)")

    def fire_flare(self, flare_manager: 'FlareManager', tick: int,
                   message: str, log: List[str]):
        if tick - self.flare_fired < FLARE_DURATION:
            log.append(f"  ⏳ [{self.agent_id}] flare cooldown active")
            return
        flare_manager.fire_flare(
            self.agent_id, self.team, self.position, tick,
            message=message, log=log
        )
        self.flare_fired = tick

# ─────────────────────────────────────────────────────────────────────
#  FLARE MANAGER
# ─────────────────────────────────────────────────────────────────────

class FlareManager:
    def __init__(self):
        self.flares:    List[FlareSignal] = []
        self.flare_seq: int = 0
        self.relay_log: List[str] = []

    def fire_flare(self, sender_id: str, team: str,
                   position: Tuple[float,float], tick: int,
                   is_sos: bool = False, message: str = "",
                   log: List[str] = None):
        self.flare_seq += 1
        fid   = f"F{self.flare_seq:04d}"
        flare = FlareSignal(
            flare_id   = fid,
            sender_id  = sender_id,
            team       = team,
            position   = position,
            fired_tick = tick,
            message    = message,
            is_sos     = is_sos,
        )
        self.flares.append(flare)
        self.relay_log.append(flare.relay_code)
        sos_str = " 🆘 SOS SIGNAL" if is_sos else ""
        entry   = (f"  🔴 FLARE FIRED by [{sender_id}] ({team}) "
                   f"@ ({position[0]:.0f},{position[1]:.0f})"
                   f"{sos_str} | Code: {flare.relay_code}")
        if message:
            entry += f" | Msg: {message}"
        if log is not None: log.append(entry)
        return flare

    def get_visible_flares(self, observer_pos: Tuple[float,float],
                           observer_team: str, current_tick: int,
                           is_mob: bool = False) -> List[FlareSignal]:
        return [f for f in self.flares
                if f.is_visible(current_tick) and
                   f.can_see(observer_pos, observer_team, is_mob)]

    def purge_expired(self, current_tick: int):
        self.flares = [f for f in self.flares if f.is_active(current_tick)]

    def render_active(self, current_tick: int):
        active = [f for f in self.flares if f.is_active(current_tick)]
        if not active:
            print("  (no active flares)")
            return
        for f in active:
            print(f.render(current_tick))

# ─────────────────────────────────────────────────────────────────────
#  MAP NAVIGATOR (team coordinator)
# ─────────────────────────────────────────────────────────────────────

class MapNavigator:
    """
    Full map navigation system for one team.
    Manages fog sharing, flare visibility, zone coverage, and minimap.
    """
    def __init__(self, team: str, agents: List[MapAgent]):
        self.team        = team
        self.agents      = agents
        self.fog         = FogOfWar(team)
        self.flare_mgr   = FlareManager()
        self.tick_num    = 0
        self.log: List[str] = []
        self.captured_points: Dict[str, str] = {k: "Neutral" for k in KEY_POINTS}
        self.event_log:  List[str] = []

    def tick(self, mob_agents: List[MapAgent] = None):
        self.tick_num += 1
        tick_log = [f"\n{'─'*70}",
                    f"  🗺️  MAP NAV TICK {self.tick_num:03d} | Team {self.team}"]

        # Move all agents + reveal fog
        for agent in self.agents:
            agent.tick_move(self.fog, self.flare_mgr, self.tick_num, tick_log)

        # Fog sharing between teammates
        for i, a in enumerate(self.agents):
            for j, b in enumerate(self.agents):
                if i != j and dist(a.position, b.position) < VISION_RADIUS * 1.5:
                    self.fog.merge_from(FogOfWar(self.team))   # simplified: shared view

        # Decay fog visibility
        self.fog.decay_visible()

        # Check landmark captures
        for lm_name in KEY_POINTS:
            lm_pos = LANDMARKS[lm_name]
            for agent in self.agents:
                if dist(agent.position, lm_pos) < 8:
                    if self.captured_points.get(lm_name) != self.team:
                        self.captured_points[lm_name] = self.team
                        tick_log.append(f"  🚩 [{agent.agent_id}] CAPTURED [{lm_name}]!")

        # Show visible flares to agents
        for agent in self.agents:
            visible = self.flare_mgr.get_visible_flares(
                agent.position, self.team, self.tick_num)
            for flare in visible:
                if flare.is_sos:
                    tick_log.append(f"  📡 [{agent.agent_id}] SEES SOS FLARE "
                                    f"from [{flare.sender_id}] → {flare.relay_code}")

        # Mob flare detection
        if mob_agents:
            for mob in mob_agents:
                visible = self.flare_mgr.get_visible_flares(
                    mob.position, mob.team, self.tick_num, is_mob=True)
                for flare in visible:
                    tick_log.append(f"  👾 MOB [{mob.agent_id}] ATTRACTED by flare "
                                    f"{flare.relay_code} at "
                                    f"({flare.position[0]:.0f},{flare.position[1]:.0f})")
                    # Mob navigates toward flare
                    mob.navigate_to(nearest_landmark(flare.position), tick_log)

        # Purge expired flares
        self.flare_mgr.purge_expired(self.tick_num)

        self.log.extend(tick_log)

    def player_fire_flare(self, agent_id: str, message: str = ""):
        """Player manually triggers a flare for their agent."""
        agent = next((a for a in self.agents if a.agent_id == agent_id), None)
        if agent:
            agent.fire_flare(self.flare_mgr, self.tick_num, message, self.log)
        else:
            self.log.append(f"  ❌ Agent [{agent_id}] not found for flare")

    def share_location(self, agent_id: str, target_agent_id: str):
        """Agent shares exact coordinates with a teammate via relay code."""
        src  = next((a for a in self.agents if a.agent_id == agent_id), None)
        tgt  = next((a for a in self.agents if a.agent_id == target_agent_id), None)
        if src and tgt:
            code = (f"[LOC:{src.agent_id}:{src.position[0]:.0f}:"
                    f"{src.position[1]:.0f}:{self.tick_num}]")
            self.log.append(f"  📡 [{agent_id}] → [{target_agent_id}] "
                            f"LOCATION SHARE: {code}")
            return code
        return None

    def render_minimap(self, width: int = 50, height: int = 25,
                       show_fog: bool = True):
        """ASCII minimap renderer with fog, agents, flares, landmarks."""
        # Scale factors
        sx = MAP_W / width
        sy = MAP_H / height
        grid = [['·'] * width for _ in range(height)]

        # Fog overlay
        if show_fog:
            for gy in range(height):
                for gx in range(width):
                    wx = gx * sx + sx/2
                    wy = gy * sy + sy/2
                    tile_x = int(wx // FOG_TILE)
                    tile_y = int(wy // FOG_TILE)
                    if (0 <= tile_x < self.fog.cols and
                            0 <= tile_y < self.fog.rows):
                        v = self.fog.grid[tile_y][tile_x]
                        if v == 0:   grid[gy][gx] = '░'
                        elif v == 1: grid[gy][gx] = '·'
                        else:        grid[gy][gx] = ' '
                    else:
                        grid[gy][gx] = '░'

        # Landmarks
        lm_chars = {
            "Parliament_Hall": 'P', "Clock_Tower": 'C',
            "North_Stadium": 'S',   "South_Stadium": 's',
            "East_Tower": 'E',       "West_Tower": 'W',
            "Battle_Ground_A": 'A', "Battle_Ground_B": 'B',
            "North_Shore": '~',      "South_Shore": '~',
            "Alpha_Spawn": '⊕',     "Omega_Spawn": '⊗',
        }
        for lm_name, (lx, ly) in LANDMARKS.items():
            gx = min(int(lx / sx), width-1)
            gy = min(int(ly / sy), height-1)
            grid[gy][gx] = lm_chars.get(lm_name, 'L')

        # Agents
        team_char = {'ALPHA': '▲', 'OMEGA': '▼', 'MOB': 'M'}
        for agent in self.agents:
            gx = min(int(agent.position[0] / sx), width-1)
            gy = min(int(agent.position[1] / sy), height-1)
            grid[gy][gx] = team_char.get(self.team, '?')

        # Active flares (blink)
        for flare in self.flare_mgr.flares:
            if flare.is_visible(self.tick_num):
                gx = min(int(flare.position[0] / sx), width-1)
                gy = min(int(flare.position[1] / sy), height-1)
                grid[gy][gx] = '*'   # flare blink character

        # Captured points
        cap_chars = {'ALPHA': '🔶', 'OMEGA': '🔷', 'Neutral': '⬜'}

        # Render
        border = '═' * (width + 4)
        print(f"\n  ╔{border}╗")
        print(f"  ║  PARLIAMENT CITY MINIMAP  |  Team {self.team}  "
              f"|  Tick {self.tick_num:03d}  "
              f"|  Fog: {100-self.fog.explored_pct:.0f}% unexplored  ║")
        print(f"  ╠{border}╣")
        for gy, row in enumerate(grid):
            line = ''.join(row)
            print(f"  ║  {line}  ║")
        print(f"  ╠{border}╣")
        # Legend
        print(f"  ║  ▲=Team Agent  *=Flare  P=Parliament  C=Clock  "
              f"S=Stadium  E/W=Tower  A/B=BattleGrd  ~=Shore  ░=Fog  ║")
        print(f"  ╚{border}╝")

        # Agent position table
        print(f"\n  Agent Positions (Team {self.team}):")
        print(f"  {'Agent':<18} {'Position':>14} {'Zone':<20} "
              f"{'Landmark':<20} {'Lost':<6} {'Explored LMs'}")
        print(f"  {'─'*95}")
        for a in self.agents:
            zone = get_zone(a.position)
            lm   = nearest_landmark(a.position)
            lost = "⚠️ YES" if a.is_lost else "  no"
            print(f"  {a.agent_id:<18} "
                  f"({a.position[0]:5.1f},{a.position[1]:5.1f})  "
                  f"{zone:<20} {lm:<20} {lost:<6} "
                  f"{len(a.explored_landmarks)}")

        # Capture status
        print(f"\n  🏁 Controlled Points (Team {self.team} perspective):")
        for pt in KEY_POINTS:
            ctrl  = self.captured_points.get(pt, "Neutral")
            icon  = "🔶" if ctrl=="ALPHA" else ("🔷" if ctrl=="OMEGA" else "⬜")
            print(f"    {icon} {pt:<22} → {ctrl}")

    def flush_log(self):
        out = self.log[:]
        self.log.clear()
        return out

# ─────────────────────────────────────────────────────────────────────
#  FULL MAP NAVIGATION DEMO
# ─────────────────────────────────────────────────────────────────────

def run_map_navigation_demo():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║         BACKEND 4 — MAP NAVIGATION ENGINE DEMO                          ║
║  Fog of War · Red Flares · Location Sharing · Full Map Access           ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)

    # Build agents
    alpha_agents = [
        MapAgent("Ignis-Prime",  "ALPHA", (22.0, 22.0), speed=8.0),
        MapAgent("AquaVex",      "ALPHA", (25.0, 20.0), speed=6.5),
        MapAgent("Volt-Surge",   "ALPHA", (20.0, 25.0), speed=10.0),
        MapAgent("TerraKnight",  "ALPHA", (24.0, 24.0), speed=5.0),
    ]
    omega_agents = [
        MapAgent("Sylvan-Wraith","OMEGA", (178.0,178.0), speed=7.0),
        MapAgent("DustSerpent",  "OMEGA", (180.0,175.0), speed=9.0),
        MapAgent("ZephyrBlade",  "OMEGA", (175.0,180.0), speed=12.0),
        MapAgent("Voidwalker",   "OMEGA", (179.0,179.0), speed=8.5),
    ]
    mob_agents = [
        MapAgent(f"Mob-{i:02d}", "MOB", (random.uniform(30,170),
                 random.uniform(30,170)), speed=5.0, is_mob=True)
        for i in range(4)
    ]

    # Build navigators
    alpha_nav = MapNavigator("ALPHA", alpha_agents)
    omega_nav = MapNavigator("OMEGA", omega_agents)

    # Assign routes
    alpha_agents[0].navigate_to("Parliament_Hall", alpha_nav.log)
    alpha_agents[1].navigate_to("Clock_Tower",     alpha_nav.log)
    alpha_agents[2].navigate_to("East_Tower",      alpha_nav.log)
    alpha_agents[3].navigate_to("West_Tower",      alpha_nav.log)

    omega_agents[0].navigate_to("Parliament_Hall", omega_nav.log)
    omega_agents[1].navigate_to("Battle_Ground_B", omega_nav.log)
    omega_agents[2].navigate_to("Clock_Tower",     omega_nav.log)
    omega_agents[3].navigate_to("South_Stadium",   omega_nav.log)

    print("  Initial routes assigned. Running simulation...\n")

    for t in range(1, 30):
        alpha_nav.tick(mob_agents)
        omega_nav.tick(mob_agents)

        # Print log first 3 ticks
        if t <= 3:
            for line in alpha_nav.flush_log() + omega_nav.flush_log():
                print(line)
        else:
            alpha_nav.flush_log(); omega_nav.flush_log()

        # Manual flare events
        if t == 5:
            print(f"\n  ⚡ [EVENT T{t}] Ignis-Prime fires a location flare!")
            alpha_nav.player_fire_flare("Ignis-Prime", "Enemy spotted near Clock Tower!")
            alpha_nav.share_location("Ignis-Prime", "Volt-Surge")

        if t == 8:
            print(f"\n  ⚡ [EVENT T{t}] AquaVex goes LOST — auto SOS fired!")
            alpha_agents[1].is_lost = True
            alpha_agents[1].fire_flare(alpha_nav.flare_mgr, t,
                                       "AquaVex LOST near North area!", alpha_nav.log)

        if t == 12:
            print(f"\n  ⚡ [EVENT T{t}] Voidwalker fires dark flare (OMEGA SOS)!")
            omega_nav.player_fire_flare("Voidwalker", "Surrounded — need backup!")

        # Minimap at key ticks
        if t in (1, 10, 20, 29):
            alpha_nav.render_minimap(width=55, height=22, show_fog=True)

    # Final flare log
    print(f"\n  {'═'*70}")
    print(f"  📡 FLARE RELAY LOG (all fired this session):")
    print(f"  {'─'*70}")
    for code in alpha_nav.flare_mgr.relay_log + omega_nav.flare_mgr.relay_log:
        print(f"    {code}")

    print(f"\n  🗺️  Final Map Coverage:")
    print(f"    Team ALPHA fog explored: {alpha_nav.fog.explored_pct:.1f}%")
    print(f"    Team OMEGA fog explored: {omega_nav.fog.explored_pct:.1f}%")
    print()

if __name__ == "__main__":
    run_map_navigation_demo()
