"""
╔══════════════════════════════════════════════════════════════════════╗
║          BACKEND 1 — SWARM AI NAVIGATION ENGINE                     ║
║  Pathfinding · Regrouping · Zone Awareness · Large Map Traversal    ║
╚══════════════════════════════════════════════════════════════════════╝

Handles:
  - A* pathfinding across Parliament City map grid
  - Zone-based navigation (sectors, roads, buildings)
  - Lost-agent detection + automatic team regroup logic
  - Waypoint patrol system
  - Formation movement
  - Collision avoidance between allied agents
"""

import math
import heapq
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
from collections import deque

# ─────────────────────────────────────────────────────────────────────
#  MAP CONSTANTS
# ─────────────────────────────────────────────────────────────────────

MAP_W = 200
MAP_H = 200

# ── Zone IDs ──────────────────────────────────────────────────────────
class Zone(Enum):
    OPEN_FIELD      = "Open Field"
    ROAD            = "Road"
    PARLIAMENT_CORE = "Parliament Core"
    STADIUM_NORTH   = "North Stadium"
    STADIUM_SOUTH   = "South Stadium"
    BATTLE_GROUND_A = "Battle Ground A"
    BATTLE_GROUND_B = "Battle Ground B"
    CLOCK_TOWER     = "Clock Tower"
    EAST_TOWER      = "East Tower"
    WEST_TOWER      = "West Tower"
    NORTH_SHORE     = "North Shore"
    SOUTH_SHORE     = "South Shore"
    ROAD_JUNCTION   = "Road Junction"

# ── Landmark registry ─────────────────────────────────────────────────
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

# ── Road network (connected nodes for pathfinding graph) ─────────────
ROAD_GRAPH: Dict[str, List[str]] = {
    "Alpha_Spawn":      ["Road_Junction_W", "Battle_Ground_A", "North_Shore"],
    "Omega_Spawn":      ["Road_Junction_E", "Battle_Ground_B", "South_Shore"],
    "Road_Junction_N":  ["Parliament_Hall", "Clock_Tower", "Road_Junction_W", "Road_Junction_E"],
    "Road_Junction_S":  ["Parliament_Hall", "Road_Junction_W", "Road_Junction_E", "South_Stadium"],
    "Road_Junction_E":  ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S", "East_Tower"],
    "Road_Junction_W":  ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S", "West_Tower"],
    "Parliament_Hall":  ["Road_Junction_N", "Road_Junction_S", "Road_Junction_E", "Road_Junction_W"],
    "Clock_Tower":      ["Road_Junction_N", "North_Stadium"],
    "North_Stadium":    ["Clock_Tower", "North_Shore"],
    "South_Stadium":    ["Road_Junction_S", "South_Shore"],
    "East_Tower":       ["Road_Junction_E", "Battle_Ground_B"],
    "West_Tower":       ["Road_Junction_W", "Battle_Ground_A"],
    "Battle_Ground_A":  ["West_Tower", "Alpha_Spawn", "Road_Junction_W"],
    "Battle_Ground_B":  ["East_Tower", "Omega_Spawn", "Road_Junction_E"],
    "North_Shore":      ["Alpha_Spawn", "North_Stadium"],
    "South_Shore":      ["Omega_Spawn", "South_Stadium"],
}

# ── Zone bounding boxes: (x_min, y_min, x_max, y_max) ────────────────
ZONE_BOUNDS: Dict[Zone, Tuple[int,int,int,int]] = {
    Zone.PARLIAMENT_CORE: (85,  85, 115, 115),
    Zone.CLOCK_TOWER:     (90,  50, 110,  70),
    Zone.STADIUM_NORTH:   (75,  15, 125,  45),
    Zone.STADIUM_SOUTH:   (75, 155, 125, 185),
    Zone.EAST_TOWER:      (145, 85, 175, 115),
    Zone.WEST_TOWER:      ( 25, 85,  55, 115),
    Zone.BATTLE_GROUND_A: ( 45, 45,  75,  75),
    Zone.BATTLE_GROUND_B: (125,125, 155, 155),
    Zone.NORTH_SHORE:     (  0,  0,  80,  20),
    Zone.SOUTH_SHORE:     (120,180, 200, 200),
}

def get_zone(pos: Tuple[float,float]) -> Zone:
    x, y = pos
    for zone, (x1, y1, x2, y2) in ZONE_BOUNDS.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            return zone
    return Zone.OPEN_FIELD

def nearest_landmark(pos: Tuple[float,float]) -> str:
    return min(LANDMARKS.keys(), key=lambda k: dist(pos, LANDMARKS[k]))

# ─────────────────────────────────────────────────────────────────────
#  MATH UTILITIES
# ─────────────────────────────────────────────────────────────────────

def dist(a: Tuple[float,float], b: Tuple[float,float]) -> float:
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

def move_toward(pos, target, speed) -> Tuple[float,float]:
    d = dist(pos, target)
    if d < 0.5:
        return target
    ratio = min(speed / d, 1.0)
    return (round(pos[0] + (target[0]-pos[0]) * ratio, 2),
            round(pos[1] + (target[1]-pos[1]) * ratio, 2))

def clamp(pos: Tuple[float,float]) -> Tuple[float,float]:
    return (max(0.0, min(float(MAP_W), pos[0])),
            max(0.0, min(float(MAP_H), pos[1])))

def midpoint(positions: List[Tuple[float,float]]) -> Tuple[float,float]:
    if not positions:
        return (100.0, 100.0)
    return (sum(p[0] for p in positions)/len(positions),
            sum(p[1] for p in positions)/len(positions))

# ─────────────────────────────────────────────────────────────────────
#  A* GRAPH PATHFINDING (Road Network)
# ─────────────────────────────────────────────────────────────────────

def road_path(start_node: str, goal_node: str) -> List[str]:
    """A* over the road graph — returns list of landmark names."""
    if start_node == goal_node:
        return [start_node]
    if start_node not in ROAD_GRAPH or goal_node not in ROAD_GRAPH:
        return [start_node, goal_node]

    def h(node):
        return dist(LANDMARKS[node], LANDMARKS[goal_node])

    open_set: List[Tuple[float, str]] = [(h(start_node), start_node)]
    came_from: Dict[str, str] = {}
    g_score: Dict[str, float] = {start_node: 0.0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_node:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start_node)
            return list(reversed(path))

        for neighbor in ROAD_GRAPH.get(current, []):
            tentative = g_score[current] + dist(LANDMARKS[current], LANDMARKS[neighbor])
            if tentative < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heapq.heappush(open_set, (tentative + h(neighbor), neighbor))

    return [start_node, goal_node]  # fallback direct

def landmark_path_coords(start_pos: Tuple[float,float],
                          goal_landmark: str) -> List[Tuple[float,float]]:
    """Converts road-graph path into coordinate waypoints."""
    start_lm = nearest_landmark(start_pos)
    nodes = road_path(start_lm, goal_landmark)
    coords = [LANDMARKS[n] for n in nodes]
    # Prepend actual start position
    if coords and dist(start_pos, coords[0]) > 5:
        coords.insert(0, start_pos)
    return coords

# ─────────────────────────────────────────────────────────────────────
#  NAVIGATION STATE
# ─────────────────────────────────────────────────────────────────────

class NavState(Enum):
    IDLE        = "IDLE"
    PATROLLING  = "PATROLLING"
    ROUTING     = "ROUTING"        # Following A* path
    LOST        = "LOST"
    REGROUPING  = "REGROUPING"
    ESCORTING   = "ESCORTING"      # Moving with formation
    FLANKING    = "FLANKING"       # Going wide around obstacles

@dataclass
class NavigationAgent:
    """
    Represents one swarm agent's navigation controller.
    Wraps position, waypoints, lost-state detection, and regroup logic.
    """
    agent_id:   str
    team:       str
    position:   Tuple[float, float]
    speed:      float = 7.0
    nav_state:  NavState = NavState.IDLE

    # Waypoint queue
    waypoints:  List[Tuple[float,float]] = field(default_factory=list)
    current_wp: int = 0

    # Lost tracking
    ticks_without_progress: int = 0
    last_position:          Tuple[float,float] = field(default_factory=lambda: (0.0, 0.0))
    lost_threshold:         int = 12   # ticks stuck before "LOST"

    # Regroup
    regroup_target: Optional[Tuple[float,float]] = None
    patrol_points:  List[str] = field(default_factory=list)
    patrol_idx:     int = 0

    # History trail (last N positions for stuck detection)
    position_history: deque = field(default_factory=lambda: deque(maxlen=8))

    # Stats
    total_distance: float = 0.0
    lost_events:    int   = 0
    regroup_events: int   = 0

    def __post_init__(self):
        self.last_position = self.position

    # ── Waypoint management ─────────────────────────────────────────
    def set_destination(self, goal_landmark: str, log: List[str]):
        """Route agent to a landmark using A* road path."""
        coords = landmark_path_coords(self.position, goal_landmark)
        self.waypoints  = coords
        self.current_wp = 0
        self.nav_state  = NavState.ROUTING
        log.append(f"  🗺️  [{self.agent_id}] Routing to [{goal_landmark}] "
                   f"via {len(coords)} waypoints")

    def set_patrol(self, patrol_route: List[str], log: List[str]):
        """Set a named patrol route."""
        self.patrol_points = patrol_route
        self.patrol_idx    = 0
        self.nav_state     = NavState.PATROLLING
        self.set_destination(patrol_route[0], log)
        log.append(f"  🔄 [{self.agent_id}] Patrol set: {' → '.join(patrol_route)}")

    def set_regroup(self, team_center: Tuple[float,float], log: List[str]):
        """Force agent to regroup toward team center."""
        self.regroup_target = team_center
        self.nav_state      = NavState.REGROUPING
        self.waypoints      = [self.position, team_center]
        self.current_wp     = 0
        self.regroup_events += 1
        log.append(f"  🔗 [{self.agent_id}] REGROUPING → center "
                   f"({team_center[0]:.0f},{team_center[1]:.0f})")

    def force_flank(self, enemy_pos: Tuple[float,float], log: List[str]):
        """Navigate wide around enemy position (flanking maneuver)."""
        ex, ey = enemy_pos
        px, py = self.position
        # Perpendicular offset
        angle  = math.atan2(ey - py, ex - px) + math.pi / 2
        flank_x = ex + math.cos(angle) * 35
        flank_y = ey + math.sin(angle) * 35
        flank_pt = clamp((flank_x, flank_y))
        self.waypoints  = [self.position, flank_pt, enemy_pos]
        self.current_wp = 0
        self.nav_state  = NavState.FLANKING
        log.append(f"  ↩️  [{self.agent_id}] FLANKING around enemy at "
                   f"({ex:.0f},{ey:.0f}) → flank point ({flank_x:.0f},{flank_y:.0f})")

    # ── Stuck / Lost detection ──────────────────────────────────────
    def _is_stuck(self) -> bool:
        if len(self.position_history) < 6:
            return False
        positions = list(self.position_history)[-6:]
        spread = max(dist(positions[0], p) for p in positions[1:])
        return spread < 2.0  # barely moved in last 6 ticks

    def _check_lost(self, log: List[str]):
        if self._is_stuck():
            self.ticks_without_progress += 1
            if self.ticks_without_progress >= self.lost_threshold:
                self.nav_state  = NavState.LOST
                self.lost_events += 1
                log.append(f"  ⚠️  [{self.agent_id}] is LOST at "
                           f"({self.position[0]:.0f},{self.position[1]:.0f})! "
                           f"Nearest landmark: [{nearest_landmark(self.position)}]")
        else:
            self.ticks_without_progress = 0

    # ── Collision avoidance ─────────────────────────────────────────
    def _avoid_allies(self, allies: List['NavigationAgent']) -> Tuple[float,float]:
        """Nudge position slightly if overlapping with allies."""
        px, py = self.position
        for ally in allies:
            if ally.agent_id == self.agent_id:
                continue
            d = dist(self.position, ally.position)
            if d < 5.0 and d > 0.01:
                # Push away
                dx = (px - ally.position[0]) / d
                dy = (py - ally.position[1]) / d
                px += dx * 1.5
                py += dy * 1.5
        return clamp((px, py))

    # ── Main tick ──────────────────────────────────────────────────
    def tick(self, allies: List['NavigationAgent'], log: List[str]):
        self.position_history.append(self.position)
        old_pos = self.position

        if self.nav_state == NavState.LOST:
            self._recover_from_lost(log)

        elif self.nav_state in (NavState.ROUTING, NavState.REGROUPING,
                                NavState.FLANKING, NavState.ESCORTING):
            self._follow_waypoints(log)

        elif self.nav_state == NavState.PATROLLING:
            self._patrol_tick(log)

        elif self.nav_state == NavState.IDLE:
            # Small random drift
            jitter = (random.uniform(-1, 1), random.uniform(-1, 1))
            self.position = clamp((self.position[0]+jitter[0],
                                   self.position[1]+jitter[1]))

        # Collision avoidance
        self.position = self._avoid_allies(allies)

        # Accumulate distance
        self.total_distance += dist(old_pos, self.position)

        # Stuck/lost check
        self._check_lost(log)

    def _follow_waypoints(self, log: List[str]):
        if self.current_wp >= len(self.waypoints):
            self._on_destination_reached(log)
            return
        target = self.waypoints[self.current_wp]
        self.position = clamp(move_toward(self.position, target, self.speed))
        if dist(self.position, target) < 3.0:
            self.current_wp += 1
            if self.current_wp >= len(self.waypoints):
                self._on_destination_reached(log)

    def _on_destination_reached(self, log: List[str]):
        lm = nearest_landmark(self.position)
        if self.nav_state == NavState.PATROLLING:
            log.append(f"  ✅ [{self.agent_id}] Reached patrol point [{lm}]")
            self.patrol_idx = (self.patrol_idx + 1) % max(1, len(self.patrol_points))
            if self.patrol_points:
                next_pt = self.patrol_points[self.patrol_idx]
                self.set_destination(next_pt, log)
        elif self.nav_state == NavState.REGROUPING:
            self.nav_state      = NavState.IDLE
            self.regroup_target = None
            log.append(f"  🤝 [{self.agent_id}] Successfully REGROUPED at [{lm}]")
        else:
            self.nav_state = NavState.IDLE
            log.append(f"  📍 [{self.agent_id}] Arrived at [{lm}]")

    def _patrol_tick(self, log: List[str]):
        """Continue patrol while nav_state is PATROLLING."""
        self._follow_waypoints(log)

    def _recover_from_lost(self, log: List[str]):
        """Recovery: navigate to nearest known landmark."""
        nearest = nearest_landmark(self.position)
        log.append(f"  🧭 [{self.agent_id}] Recovering — heading to nearest landmark [{nearest}]")
        self.set_destination(nearest, log)
        self.ticks_without_progress = 0

    def status_line(self) -> str:
        zone = get_zone(self.position)
        lm   = nearest_landmark(self.position)
        wp_remaining = max(0, len(self.waypoints) - self.current_wp)
        return (f"  [{self.agent_id:<18}] {self.nav_state.value:<14} "
                f"Pos:({self.position[0]:5.1f},{self.position[1]:5.1f})  "
                f"Zone:{zone.value:<20} Near:[{lm:<18}] "
                f"WP:{wp_remaining:2d}  Dist:{self.total_distance:6.1f}  "
                f"Lost:{self.lost_events}  Regroup:{self.regroup_events}")

# ─────────────────────────────────────────────────────────────────────
#  SWARM NAVIGATOR — Team-Level Coordination
# ─────────────────────────────────────────────────────────────────────

REGROUP_DISTANCE_THRESHOLD = 60.0   # units — if farther than this, flag as separated

class SwarmNavigator:
    """
    Manages navigation for an entire team's swarm.
    Handles:
      - Separation detection (lost from team)
      - Regroup triggers
      - Formation movement
      - Patrol scheduling
    """
    def __init__(self, team_name: str, agents: List[NavigationAgent]):
        self.team_name = team_name
        self.agents    = agents
        self.tick_num  = 0
        self.log: List[str] = []

        # Preset patrol routes per element role
        self.patrol_routes = {
            "aggressive": ["Battle_Ground_A", "Road_Junction_W", "Parliament_Hall",
                           "Road_Junction_E", "Battle_Ground_B"],
            "defensive":  ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S",
                           "Road_Junction_W", "Road_Junction_E"],
            "recon":      ["Clock_Tower", "North_Stadium", "North_Shore",
                           "West_Tower", "Road_Junction_W", "Parliament_Hall"],
            "support":    ["Parliament_Hall", "Road_Junction_N", "Road_Junction_S"],
        }

    @property
    def alive_agents(self):
        return self.agents   # In navigation layer all agents exist; battle layer marks alive

    def team_center(self) -> Tuple[float,float]:
        return midpoint([a.position for a in self.agents])

    def _detect_separated(self) -> List[NavigationAgent]:
        """Return agents too far from team center."""
        center = self.team_center()
        return [a for a in self.agents
                if dist(a.position, center) > REGROUP_DISTANCE_THRESHOLD]

    def _trigger_regroup(self, separated: List[NavigationAgent]):
        center = self.team_center()
        for agent in separated:
            if agent.nav_state not in (NavState.REGROUPING, NavState.LOST):
                agent.set_regroup(center, self.log)

    def assign_patrol(self, agent: NavigationAgent, route_type: str):
        route = self.patrol_routes.get(route_type, self.patrol_routes["defensive"])
        agent.set_patrol(route, self.log)

    def formation_advance(self, goal_landmark: str, formation: str = "wedge"):
        """
        Move whole team toward a landmark in formation.
        Formations: wedge | line | box | diamond
        """
        center = LANDMARKS[goal_landmark]
        offsets = self._formation_offsets(formation)
        self.log.append(f"\n  📐 [{self.team_name}] Formation ADVANCE → "
                        f"[{goal_landmark}] in {formation.upper()} formation")
        for i, agent in enumerate(self.agents):
            if i < len(offsets):
                ox, oy = offsets[i]
                target = clamp((center[0]+ox, center[1]+oy))
            else:
                target = center
            agent.waypoints  = [agent.position, target]
            agent.current_wp = 0
            agent.nav_state  = NavState.ESCORTING

    def _formation_offsets(self, formation: str) -> List[Tuple[float,float]]:
        """Returns (dx,dy) offsets for each agent slot."""
        if formation == "wedge":
            return [(0,0), (-15, 15), (15, 15), (0, 25)]
        elif formation == "line":
            return [(-22, 0), (-7, 0), (7, 0), (22, 0)]
        elif formation == "box":
            return [(-12,-12), (12,-12), (-12, 12), (12, 12)]
        elif formation == "diamond":
            return [(0,-18), (-18, 0), (18, 0), (0, 18)]
        return [(0,0)] * 4

    def tick(self):
        """Run one navigation tick for the whole team."""
        self.tick_num += 1
        self.log.append(f"\n{'─'*65}")
        self.log.append(f"  🧭 [{self.team_name}] NAV TICK {self.tick_num:03d}")

        # Separation check every 5 ticks
        if self.tick_num % 5 == 0:
            separated = self._detect_separated()
            if separated:
                self.log.append(f"  ⚠️  [{self.team_name}] Separated agents detected: "
                               f"{[a.agent_id for a in separated]}")
                self._trigger_regroup(separated)
            else:
                self.log.append(f"  ✅ [{self.team_name}] All agents within cohesion range")

        # Tick each agent
        for agent in self.agents:
            agent.tick(self.agents, self.log)

        # Print team status every 10 ticks
        if self.tick_num % 10 == 0:
            self.print_team_status()

    def print_team_status(self):
        border = "═" * 100
        print(f"\n{border}")
        print(f"  🧭 NAVIGATION STATUS — Team {self.team_name} | Tick {self.tick_num:03d}")
        print(f"  Team Center: ({self.team_center()[0]:.1f}, {self.team_center()[1]:.1f})")
        print(border)
        header = (f"  {'Agent':<20} {'NavState':<14} {'Position':<18} "
                  f"{'Zone':<22} {'Nearest LM':<20} {'WP':<4} {'Dist':>7} {'Lost':>5}")
        print(header)
        print(f"  {'─'*95}")
        for a in self.agents:
            print(a.status_line())
        print(border)

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

# ─────────────────────────────────────────────────────────────────────
#  DUAL-TEAM NAVIGATION DEMO
# ─────────────────────────────────────────────────────────────────────

def build_alpha_navigator() -> SwarmNavigator:
    agents = [
        NavigationAgent("Ignis-Prime",   "ALPHA", LANDMARKS["Alpha_Spawn"], speed=8.0),
        NavigationAgent("AquaVex",       "ALPHA", LANDMARKS["Alpha_Spawn"], speed=6.5),
        NavigationAgent("Volt-Surge",    "ALPHA", LANDMARKS["Alpha_Spawn"], speed=10.0),
        NavigationAgent("TerraKnight",   "ALPHA", LANDMARKS["Alpha_Spawn"], speed=5.0),
    ]
    return SwarmNavigator("ALPHA", agents)

def build_omega_navigator() -> SwarmNavigator:
    agents = [
        NavigationAgent("Sylvan-Wraith", "OMEGA", LANDMARKS["Omega_Spawn"], speed=7.0),
        NavigationAgent("DustSerpent",   "OMEGA", LANDMARKS["Omega_Spawn"], speed=9.0),
        NavigationAgent("ZephyrBlade",   "OMEGA", LANDMARKS["Omega_Spawn"], speed=12.0),
        NavigationAgent("Voidwalker",    "OMEGA", LANDMARKS["Omega_Spawn"], speed=8.5),
    ]
    return SwarmNavigator("OMEGA", agents)

def run_navigation_demo(ticks: int = 40):
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║         SWARM NAVIGATION ENGINE — DEMO RUN                          ║
║  A* Pathfinding · Regroup · Patrol · Formation · Lost Recovery      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    alpha_nav = build_alpha_navigator()
    omega_nav = build_omega_navigator()

    # ── Assign initial orders ──────────────────────────────────────
    log = []

    # ALPHA: different patrol & routing roles
    alpha_nav.assign_patrol(alpha_nav.agents[0], "aggressive")   # Ignis
    alpha_nav.assign_patrol(alpha_nav.agents[1], "support")      # AquaVex
    alpha_nav.assign_patrol(alpha_nav.agents[2], "recon")        # Volt-Surge
    alpha_nav.assign_patrol(alpha_nav.agents[3], "defensive")    # TerraKnight

    # OMEGA: formation advance on Parliament
    omega_nav.formation_advance("Parliament_Hall", formation="wedge")

    print("  Initial orders assigned. Beginning navigation simulation...\n")

    for t in range(ticks):
        alpha_nav.tick()
        omega_nav.tick()

        # Flush and print logs
        alpha_log = alpha_nav.flush_log()
        omega_log = omega_nav.flush_log()

        if t < 5 or t % 10 == 0:
            for line in alpha_log + omega_log:
                print(line)

        # Simulate mid-battle: at tick 20 ZephyrBlade gets "lost" (teleport far away)
        if t == 20:
            zeph = next(a for a in omega_nav.agents if a.agent_id == "ZephyrBlade")
            zeph.position = (10.0, 10.0)   # dropped far away
            zeph.waypoints = []
            zeph.nav_state = NavState.IDLE
            print(f"\n  ⚡ [SIMULATION EVENT T{t}] ZephyrBlade got separated — dropped to (10,10)!")

        # At tick 15 ALPHA formation push
        if t == 15:
            print(f"\n  ⚡ [SIMULATION EVENT T{t}] ALPHA orders formation PUSH to Parliament!")
            alpha_nav.formation_advance("Parliament_Hall", formation="box")

        time.sleep(0.01)

    # Final status
    alpha_nav.print_team_status()
    omega_nav.print_team_status()

    # Path demo
    print("\n  📡 ROAD PATH DEMOS:")
    paths = [
        ("Alpha_Spawn", "Parliament_Hall"),
        ("Alpha_Spawn", "South_Shore"),
        ("Battle_Ground_A", "East_Tower"),
    ]
    for start, end in paths:
        path = road_path(start, end)
        coords = [f"({LANDMARKS[n][0]:.0f},{LANDMARKS[n][1]:.0f})" for n in path]
        print(f"  {start:<25} → {end:<20}: {' ➜ '.join(path)}")
        print(f"    Coords: {' ➜ '.join(coords)}")
    print()

if __name__ == "__main__":
    run_navigation_demo(ticks=40)
