"""
╔══════════════════════════════════════════════════════════════════════════╗
║       BACKEND 6 — ENEMY PLAYER NAVIGATION SYSTEM                       ║
║  Peak-Moment Intel · Group Location Reveal · Full Combat Trigger        ║
║  Tension Meter · Engagement Zones · Formation Intel                     ║
╚══════════════════════════════════════════════════════════════════════════╝

Features:
  - PEAK MOMENT SYSTEM:
      * The game engine tracks a TENSION METER (0–100)
      * Tension rises with: kills, landmark caps, boss defeats, time elapsed
      * At TENSION ≥ 70 → "PEAK MOMENT" unlocks Enemy Player Navigation
      * During Peak Moment: both teams see each other's GROUP LOCATION
        (not individual agent coords — just a zone cluster indicator)
      * At TENSION = 100 → FULL REVEAL: exact positions exposed for 5 ticks

  - GROUP LOCATION INTEL:
      * Group A/B location displayed as a cluster zone (e.g. "near Parliament,  
        radius ~20 units" — not exact agent positions)
      * Updates every 2 ticks during Peak Moment
      * Shows: team heading direction, formation type, estimated HP %

  - FULL COMBAT ENGAGEMENT TRIGGER:
      * When both groups are within ENGAGEMENT_RANGE of each other
      * Engine broadcasts ENGAGEMENT ALERT to both teams + all mobs
      * Agents switch to combat-ready states
      * Generates combat-start relay code: [ENGAGE:TeamA:TeamB:Zone:Tick]

  - INTEL DECAY:
      * After Peak Moment ends, intel becomes stale over 5 ticks
      * Teams must generate new kills/caps to raise tension again

  - COUNTER-INTEL:
      * Dark/Flying agents can perform GHOST MOVE — briefly hides from intel
      * Sand agents can deploy DECOY BEACON — sends false location data

  - DANGER ESCALATION STAGES:
      Stage 1 (0-39):   Normal — no enemy intel
      Stage 2 (40-69):  Alert — radar blips only (from Backend 5)
      Stage 3 (70-89):  Peak Moment — group location revealed
      Stage 4 (90-99):  Critical — formation + heading exposed
      Stage 5 (100):    Total War — full exact positions, 5-tick window
"""

import math
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
from collections import deque, defaultdict

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
    "Alpha_Spawn":      ( 22,  22), "Omega_Spawn":      (178, 178),
}

ZONE_BOUNDS = {
    "Parliament_Core": (85, 85, 115, 115),
    "Clock_Tower":     (90, 50, 110,  70),
    "North_Stadium":   (75, 15, 125,  45),
    "South_Stadium":   (75,155, 125, 185),
    "East_Tower":      (145,85, 175, 115),
    "West_Tower":      (25, 85,  55, 115),
    "Battle_A":        (45, 45,  75,  75),
    "Battle_B":        (125,125,155, 155),
    "North_Shore":     (0,   0,  80,  20),
    "South_Shore":     (120,180,200, 200),
}

def dist(a, b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2)
def clamp(p): return (max(0.0,min(float(MAP_W),p[0])), max(0.0,min(float(MAP_H),p[1])))
def midpoint(pts): return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))
def move_toward(pos, tgt, spd):
    d = dist(pos, tgt)
    if d < 0.5: return tgt
    r = min(spd/d, 1.0)
    return (round(pos[0]+(tgt[0]-pos[0])*r,2), round(pos[1]+(tgt[1]-pos[1])*r,2))
def angle_deg(a, b): return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 360
def compass(ang):
    dirs = ["N","NE","E","SE","S","SW","W","NW","N"]
    return dirs[int((ang+22.5)//45)]
def get_zone(pos):
    x, y = pos
    for name, (x1,y1,x2,y2) in ZONE_BOUNDS.items():
        if x1<=x<=x2 and y1<=y<=y2: return name
    return "Open_Field"

# ─────────────────────────────────────────────────────────────────────
#  TENSION & ESCALATION CONSTANTS
# ─────────────────────────────────────────────────────────────────────

TENSION_PER_KILL          = 8.0
TENSION_PER_CAP           = 6.0
TENSION_PER_BOSS_KILL     = 15.0
TENSION_PER_TICK          = 0.5    # passive build over time
TENSION_DECAY_PER_TICK    = 0.2    # when nothing happens
PEAK_MOMENT_THRESHOLD     = 70.0
CRITICAL_THRESHOLD        = 90.0
TOTAL_WAR_THRESHOLD       = 100.0
TOTAL_WAR_DURATION        = 5      # ticks at full reveal
ENGAGEMENT_RANGE          = 35.0   # distance for combat trigger
GHOST_MOVE_DURATION       = 4      # ticks hidden from intel
DECOY_DURATION            = 8      # ticks decoy broadcasts false position

# ─────────────────────────────────────────────────────────────────────
#  ESCALATION STAGE
# ─────────────────────────────────────────────────────────────────────

class EscalationStage(Enum):
    NORMAL      = (0,   39,  "Normal",      "⚪ No enemy intel")
    ALERT       = (40,  69,  "Alert",       "🟡 Radar blips only")
    PEAK_MOMENT = (70,  89,  "Peak Moment", "🟠 Group location revealed")
    CRITICAL    = (90,  99,  "Critical",    "🔴 Formation + heading exposed")
    TOTAL_WAR   = (100, 100, "Total War",   "☢️  FULL POSITIONS EXPOSED")

    def __new__(cls, min_t, max_t, label, desc):
        obj = object.__new__(cls)
        obj._value_ = min_t
        obj.min_tension = min_t
        obj.max_tension = max_t
        obj.label       = label
        obj.desc        = desc
        return obj

def get_stage(tension: float) -> EscalationStage:
    if tension >= 100: return EscalationStage.TOTAL_WAR
    if tension >= 90:  return EscalationStage.CRITICAL
    if tension >= 70:  return EscalationStage.PEAK_MOMENT
    if tension >= 40:  return EscalationStage.ALERT
    return EscalationStage.NORMAL

# ─────────────────────────────────────────────────────────────────────
#  GROUP INTEL PACKET
# ─────────────────────────────────────────────────────────────────────

@dataclass
class GroupIntel:
    """
    What one team knows about the other — level-gated by tension.
    Never reveals exact agent positions (except at TOTAL WAR stage).
    """
    team:           str               # team this intel is ABOUT
    tick:           int
    stage:          EscalationStage

    # Stage 3+ (Peak Moment): group-level data
    group_center:   Optional[Tuple[float,float]] = None   # approx cluster center
    cluster_radius: float = 0.0                            # spread of the group
    zone:           str   = "Unknown"
    heading:        str   = "N/A"                          # compass direction moving
    alive_count:    int   = 0
    hp_pct_est:     float = 0.0                            # estimated average HP%
    formation_hint: str   = "Unknown"                      # "clustered"/"spread"/"line"

    # Stage 4+ (Critical): formation details
    formation_type: str   = "N/A"
    sub_groups:     int   = 1                              # split into how many groups
    likely_target:  str   = "Unknown"                      # landmark they're heading for

    # Stage 5 (Total War): exact positions exposed temporarily
    exact_positions: List[Tuple[str, Tuple[float,float]]] = field(default_factory=list)
    exact_expires_tick: int = 0

    # Stale tracking
    stale_tick:     int   = 0
    is_stale:       bool  = False

    def is_valid(self, current_tick: int) -> bool:
        return not self.is_stale and (current_tick - self.tick) < 6

    def render(self, current_tick: int, viewer_team: str):
        age     = current_tick - self.tick
        stale_s = " ⚠️ STALE" if self.is_stale or age > 4 else ""
        lines   = [f"\n  ╔{'═'*65}╗"]
        lines.append(f"  ║  ENEMY INTEL: Team {self.team}  |  "
                     f"Stage: {self.stage.label}  |  Tick {self.tick}{stale_s}  ║")
        lines.append(f"  ╠{'═'*65}╣")

        if self.stage == EscalationStage.NORMAL:
            lines.append(f"  ║  {EscalationStage.NORMAL.desc}  ║")

        elif self.stage == EscalationStage.ALERT:
            lines.append(f"  ║  {EscalationStage.ALERT.desc:<63} ║")
            lines.append(f"  ║  Check radar display for blip positions             ║")

        elif self.stage in (EscalationStage.PEAK_MOMENT, EscalationStage.CRITICAL):
            cx, cy = self.group_center or (0,0)
            lines.append(f"  ║  📍 Group Center: ~({cx:.0f},{cy:.0f})  "
                         f"Zone: [{self.zone}]{'':<20} ║")
            lines.append(f"  ║  📏 Spread Radius: ~{self.cluster_radius:.0f} units  "
                         f"Heading: {self.heading:<30}  ║")
            lines.append(f"  ║  👥 Alive: {self.alive_count}/4  "
                         f"Est.HP: {self.hp_pct_est*100:.0f}%  "
                         f"Formation: {self.formation_hint:<22} ║")
            if self.stage == EscalationStage.CRITICAL:
                lines.append(f"  ║  ─── CRITICAL INTEL ─────────────────────────────── ║")
                lines.append(f"  ║  🎯 Likely Target: [{self.likely_target}]  "
                             f"Sub-groups: {self.sub_groups}  "
                             f"Formation: {self.formation_type:<12} ║")

        elif self.stage == EscalationStage.TOTAL_WAR:
            lines.append(f"  ║  ☢️  TOTAL WAR — FULL POSITIONS EXPOSED              ║")
            lines.append(f"  ║  Expires: Tick {self.exact_expires_tick:<50} ║")
            for agent_id, pos in self.exact_positions:
                lines.append(f"  ║    ▶ {agent_id:<18} → ({pos[0]:.1f},{pos[1]:.1f})"
                             f"{'':>25}║")

        lines.append(f"  ╚{'═'*65}╝")
        return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────
#  DECOY BEACON
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DecoyBeacon:
    beacon_id:    str
    owner_id:     str
    team:         str
    fake_pos:     Tuple[float, float]
    deployed_tick: int
    duration:     int = DECOY_DURATION

    def is_active(self, tick: int) -> bool:
        return (tick - self.deployed_tick) < self.duration

    def render(self, tick: int) -> str:
        ttl = self.duration - (tick - self.deployed_tick)
        return (f"  📡 DECOY [{self.beacon_id}] by [{self.owner_id}] ({self.team}) "
                f"broadcasting false pos ({self.fake_pos[0]:.0f},{self.fake_pos[1]:.0f})  "
                f"TTL:{ttl}t")

# ─────────────────────────────────────────────────────────────────────
#  COMBAT ENGAGEMENT EVENT
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EngagementEvent:
    engage_id:    str
    team_a:       str
    team_b:       str
    zone:         str
    tick:         int
    distance:     float
    relay_code:   str = ""

    def __post_init__(self):
        self.relay_code = (f"[ENGAGE:{self.team_a}:{self.team_b}:"
                           f"{self.zone}:{self.tick}]")

    def render(self) -> str:
        return (f"\n  {'╔'+'═'*65+'╗'}\n"
                f"  ║  ⚔️  COMBAT ENGAGEMENT TRIGGERED                                ║\n"
                f"  ║  Teams:     {self.team_a} vs {self.team_b}{'':>37}║\n"
                f"  ║  Zone:      {self.zone:<51} ║\n"
                f"  ║  Distance:  {self.distance:.1f} units{'':>46} ║\n"
                f"  ║  Tick:      {self.tick:<51} ║\n"
                f"  ║  Code:      {self.relay_code:<51} ║\n"
                f"  {'╚'+'═'*65+'╝'}")

# ─────────────────────────────────────────────────────────────────────
#  PLAYER ENTITY
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PlayerEntity:
    agent_id:    str
    team:        str
    element:     str
    position:    Tuple[float, float]
    speed:       float = 7.0
    hp:          float = 300.0
    max_hp:      float = 300.0

    # Counter-intel abilities
    ghost_active:      bool = False
    ghost_expires:     int  = 0     # tick when ghost ends
    decoy_deployed:    bool = False

    # Movement
    waypoints:   List[Tuple[float,float]] = field(default_factory=list)
    wp_idx:      int = 0
    velocity:    Tuple[float, float] = (0.0, 0.0)   # for heading calc
    prev_pos:    Tuple[float, float] = field(default_factory=lambda: (0.0,0.0))

    kills:       int = 0
    caps:        int = 0

    def __post_init__(self):
        self.prev_pos = self.position

    @property
    def alive(self): return self.hp > 0

    def hp_pct(self): return self.hp / self.max_hp

    def activate_ghost(self, tick: int, log: List[str]):
        if self.element in ("Dark","Flying"):
            self.ghost_active  = True
            self.ghost_expires = tick + GHOST_MOVE_DURATION
            log.append(f"  👻 [{self.agent_id}] GHOST MOVE activated — "
                       f"hidden from intel for {GHOST_MOVE_DURATION} ticks!")
        else:
            log.append(f"  ❌ [{self.agent_id}] Ghost Move requires Dark or Flying element")

    def check_ghost_expiry(self, tick: int, log: List[str]):
        if self.ghost_active and tick >= self.ghost_expires:
            self.ghost_active = False
            log.append(f"  👻 [{self.agent_id}] Ghost Move EXPIRED — visible on intel again")

    def tick_move(self, log: List[str]):
        self.prev_pos = self.position
        if self.waypoints and self.wp_idx < len(self.waypoints):
            tgt = self.waypoints[self.wp_idx]
            self.position = clamp(move_toward(self.position, tgt, self.speed))
            # Track velocity
            self.velocity = (self.position[0]-self.prev_pos[0],
                             self.position[1]-self.prev_pos[1])
            if dist(self.position, tgt) < 2.5:
                self.wp_idx += 1
        else:
            jx, jy = random.uniform(-0.3,0.3), random.uniform(-0.3,0.3)
            self.position = clamp((self.position[0]+jx, self.position[1]+jy))
            self.velocity = (jx, jy)

    def heading(self) -> str:
        vx, vy = self.velocity
        if abs(vx) < 0.1 and abs(vy) < 0.1: return "STATIONARY"
        ang = math.degrees(math.atan2(vy, vx)) % 360
        return compass(ang)

def compass(ang):
    dirs = ["N","NE","E","SE","S","SW","W","NW","N"]
    return dirs[int((ang+22.5)//45)]

# ─────────────────────────────────────────────────────────────────────
#  TENSION METER
# ─────────────────────────────────────────────────────────────────────

class TensionMeter:
    def __init__(self):
        self.value:  float = 0.0
        self.history: deque = deque(maxlen=30)
        self.events:  List[str] = []

    def add(self, amount: float, reason: str):
        old = self.value
        self.value = min(100.0, self.value + amount)
        self.events.append(f"  +{amount:.1f} tension [{reason}] → {self.value:.1f}")

    def decay(self):
        self.value = max(0.0, self.value - TENSION_DECAY_PER_TICK)

    def tick_passive(self):
        self.add(TENSION_PER_TICK, "passive time")
        self.history.append(self.value)

    @property
    def stage(self) -> EscalationStage:
        return get_stage(self.value)

    def render_bar(self, width: int = 40) -> str:
        filled  = int((self.value / 100) * width)
        bar     = '█' * filled + '░' * (width - filled)
        stage   = self.stage
        color_s = {
            EscalationStage.NORMAL:      "⚪",
            EscalationStage.ALERT:       "🟡",
            EscalationStage.PEAK_MOMENT: "🟠",
            EscalationStage.CRITICAL:    "🔴",
            EscalationStage.TOTAL_WAR:   "☢️ ",
        }.get(stage, "⚪")
        return (f"  {color_s} TENSION [{bar}] {self.value:5.1f}/100  "
                f"Stage: {stage.label}  — {stage.desc}")

    def flush_events(self) -> List[str]:
        out = self.events[:]
        self.events.clear()
        return out

# ─────────────────────────────────────────────────────────────────────
#  ENEMY PLAYER NAVIGATION ENGINE
# ─────────────────────────────────────────────────────────────────────

class EnemyPlayerNavEngine:
    """
    Core engine for enemy player position intel.
    Unlocked progressively based on tension meter.
    """
    def __init__(self):
        self.tension          = TensionMeter()
        self.tick_num:  int   = 0
        self.log: List[str]   = []

        # Intel packets per team (what ALPHA knows about OMEGA and vice versa)
        self.alpha_intel: Optional[GroupIntel] = None   # ALPHA's view of OMEGA
        self.omega_intel: Optional[GroupIntel] = None   # OMEGA's view of ALPHA

        # Total War
        self.total_war_active: bool = False
        self.total_war_start:  int  = 0

        # Engagements
        self.engagements: List[EngagementEvent] = []
        self.engage_seq:  int = 0
        self.active_engagement: Optional[EngagementEvent] = None

        # Decoys
        self.decoys: List[DecoyBeacon] = []
        self.decoy_seq: int = 0

        # Ghost movers
        self.ghost_agents: Set[str] = set()

    # ── Tension events ────────────────────────────────────────────
    def event_kill(self, killer_id: str, victim_id: str, team: str):
        self.tension.add(TENSION_PER_KILL,
                         f"Kill: {killer_id} → {victim_id}")

    def event_capture(self, agent_id: str, landmark: str):
        self.tension.add(TENSION_PER_CAP,
                         f"Cap: {agent_id} @ {landmark}")

    def event_boss_kill(self, agent_id: str, boss_id: str):
        self.tension.add(TENSION_PER_BOSS_KILL,
                         f"Boss Kill: {agent_id} → {boss_id}")

    # ── Intel generation ─────────────────────────────────────────
    def _build_group_intel(self, about_team: str,
                           players: List[PlayerEntity],
                           tick: int) -> GroupIntel:
        stage   = self.tension.stage
        alive   = [p for p in players if p.alive]
        if not alive:
            return GroupIntel(team=about_team, tick=tick, stage=stage,
                              alive_count=0)

        # Filter ghost agents
        visible = [p for p in alive if not p.ghost_active]
        if not visible:
            return GroupIntel(team=about_team, tick=tick, stage=stage,
                              alive_count=0, formation_hint="HIDDEN")

        positions = [p.position for p in visible]
        center    = midpoint(positions)
        spread    = max(dist(center, p) for p in positions) if len(positions) > 1 else 0.0
        avg_hp    = sum(p.hp_pct() for p in visible) / len(visible)
        zone      = get_zone(center)

        # Heading: average velocity direction
        vx = sum(p.velocity[0] for p in visible) / len(visible)
        vy = sum(p.velocity[1] for p in visible) / len(visible)
        if abs(vx) < 0.1 and abs(vy) < 0.1:
            hdg = "STATIONARY"
        else:
            hdg = compass(math.degrees(math.atan2(vy, vx)) % 360)

        # Formation hint
        if spread < 10:   form_hint = "Tight Cluster"
        elif spread < 25: form_hint = "Standard Group"
        else:             form_hint = "Spread / Split"

        # Add noise to center (not exact) at lower stages
        if stage in (EscalationStage.PEAK_MOMENT, EscalationStage.ALERT):
            noise = 8.0
            cx = center[0] + random.uniform(-noise, noise)
            cy = center[1] + random.uniform(-noise, noise)
            approx_center = (round(cx/10)*10, round(cy/10)*10)  # snap to 10-unit grid
        else:
            approx_center = center

        # Likely target (which landmark they're heading toward)
        if vx != 0 or vy != 0:
            future = (center[0]+vx*15, center[1]+vy*15)
            likely = min(LANDMARKS.keys(), key=lambda k: dist(future, LANDMARKS[k]))
        else:
            likely = min(LANDMARKS.keys(), key=lambda k: dist(center, LANDMARKS[k]))

        # Sub-group detection
        sub_groups = 1
        if len(visible) >= 3:
            # Simple: if any pair is far apart, consider it split
            for i in range(len(visible)):
                for j in range(i+1, len(visible)):
                    if dist(visible[i].position, visible[j].position) > 40:
                        sub_groups = 2
                        break

        # Formation type
        if spread < 8:
            form_type = "Wedge/Stack"
        elif sub_groups == 2:
            form_type = "Split Push"
        else:
            form_type = "Line/Advance"

        # Exact positions (only at TOTAL WAR)
        exact = []
        if stage == EscalationStage.TOTAL_WAR:
            exact = [(p.agent_id, p.position) for p in alive]

        return GroupIntel(
            team           = about_team,
            tick           = tick,
            stage          = stage,
            group_center   = approx_center,
            cluster_radius = spread,
            zone           = zone,
            heading        = hdg,
            alive_count    = len(visible),
            hp_pct_est     = avg_hp,
            formation_hint = form_hint,
            formation_type = form_type,
            sub_groups     = sub_groups,
            likely_target  = likely,
            exact_positions= exact,
            exact_expires_tick = tick + TOTAL_WAR_DURATION,
        )

    # ── Decoy system ─────────────────────────────────────────────
    def deploy_decoy(self, agent: PlayerEntity, fake_pos: Tuple[float,float],
                     log: List[str]):
        if agent.element not in ("Sand", "Dark"):
            log.append(f"  ❌ [{agent.agent_id}] Decoy requires Sand or Dark element")
            return
        self.decoy_seq += 1
        did = f"DCY{self.decoy_seq:03d}"
        d   = DecoyBeacon(did, agent.agent_id, agent.team,
                          fake_pos, self.tick_num)
        self.decoys.append(d)
        log.append(f"  🎭 DECOY [{did}] deployed by [{agent.agent_id}] ({agent.team}) "
                   f"— broadcasting false position "
                   f"({fake_pos[0]:.0f},{fake_pos[1]:.0f}) for {DECOY_DURATION}t")

    def _inject_decoys(self, about_team: str,
                        intel: GroupIntel) -> GroupIntel:
        """If enemy has active decoys, corrupt their intel center."""
        active_decoys = [d for d in self.decoys
                         if d.is_active(self.tick_num) and d.team == about_team]
        if active_decoys and intel.group_center:
            decoy = random.choice(active_decoys)
            # Shift intel center toward decoy position
            cx, cy = intel.group_center
            dx, dy = decoy.fake_pos
            intel.group_center = (round((cx+dx)/2/10)*10, round((cy+dy)/2/10)*10)
            self.log.append(f"  🎭 DECOY [{decoy.beacon_id}] corrupting enemy intel "
                            f"for team {about_team}!")
        return intel

    # ── Engagement detection ─────────────────────────────────────
    def _check_engagement(self, alpha: List[PlayerEntity],
                           omega: List[PlayerEntity]):
        alive_a = [p for p in alpha if p.alive]
        alive_o = [p for p in omega if p.alive]
        if not alive_a or not alive_o:
            return
        center_a = midpoint([p.position for p in alive_a])
        center_o = midpoint([p.position for p in alive_o])
        d = dist(center_a, center_o)
        if d <= ENGAGEMENT_RANGE:
            if self.active_engagement is None:
                self.engage_seq += 1
                zone = get_zone(midpoint([center_a, center_o]))
                ev   = EngagementEvent(
                    engage_id = f"ENG{self.engage_seq:03d}",
                    team_a    = "ALPHA",
                    team_b    = "OMEGA",
                    zone      = zone,
                    tick      = self.tick_num,
                    distance  = d,
                )
                self.engagements.append(ev)
                self.active_engagement = ev
                self.log.append(ev.render())
                # Tension spike on engagement
                self.tension.add(12.0, "Combat Engagement")
        else:
            if self.active_engagement:
                self.log.append(f"  ✅ Engagement [{self.active_engagement.engage_id}] "
                                f"disengaged (distance now {d:.1f}u)")
                self.active_engagement = None

    # ── Main tick ────────────────────────────────────────────────
    def tick(self, alpha_players: List[PlayerEntity],
             omega_players: List[PlayerEntity]):
        self.tick_num += 1
        tick_log = [f"\n{'═'*70}",
                    f"  ⚡ ENEMY NAV TICK {self.tick_num:03d}"]

        # Tension passive build
        self.tension.tick_passive()
        tick_log.extend(self.tension.flush_events())
        tick_log.append(self.tension.render_bar())

        # Move all players
        for p in alpha_players + omega_players:
            p.tick_move(tick_log)
            p.check_ghost_expiry(self.tick_num, tick_log)

        # Build intel based on current stage
        stage = self.tension.stage

        if stage != EscalationStage.NORMAL:
            # ALPHA sees OMEGA's intel
            self.alpha_intel = self._build_group_intel(
                "OMEGA", omega_players, self.tick_num)
            self.alpha_intel = self._inject_decoys("OMEGA", self.alpha_intel)

            # OMEGA sees ALPHA's intel
            self.omega_intel = self._build_group_intel(
                "ALPHA", alpha_players, self.tick_num)
            self.omega_intel = self._inject_decoys("ALPHA", self.omega_intel)

        # Stale old intel after 6 ticks
        for intel in [self.alpha_intel, self.omega_intel]:
            if intel and (self.tick_num - intel.tick) > 5:
                intel.is_stale = True

        # Engagement check
        self._check_engagement(alpha_players, omega_players)

        # Total War: special handling
        if stage == EscalationStage.TOTAL_WAR:
            if not self.total_war_active:
                self.total_war_active = True
                self.total_war_start  = self.tick_num
                tick_log.append(f"\n  {'☢️ '*8}")
                tick_log.append(f"  ☢️  TOTAL WAR ACTIVATED — FULL POSITIONS EXPOSED!")
                tick_log.append(f"  {'☢️ '*8}")
            elif (self.tick_num - self.total_war_start) >= TOTAL_WAR_DURATION:
                tick_log.append(f"  ⚠️  Total War window EXPIRED — intel degrading...")
                self.tension.value = 80.0   # drop back to Critical
                self.total_war_active = False

        # Purge decoys
        self.decoys = [d for d in self.decoys if d.is_active(self.tick_num)]

        self.log.extend(tick_log)

    # ── Display methods ───────────────────────────────────────────
    def render_intel_for_team(self, viewer_team: str, current_tick: int):
        print(f"\n  {'─'*68}")
        print(f"  👁️  INTEL DISPLAY for Team {viewer_team} "
              f"| Tick {current_tick:03d}")
        intel = self.alpha_intel if viewer_team == "ALPHA" else self.omega_intel
        if intel:
            print(intel.render(current_tick, viewer_team))
        else:
            print("  (no intel available — tension too low)")

    def render_tension_overview(self):
        stage = self.tension.stage
        print(f"\n  ╔{'═'*65}╗")
        print(f"  ║  BATTLE TENSION OVERVIEW  |  Tick {self.tick_num:03d}{'':>30}║")
        print(f"  ╠{'═'*65}╣")
        print(f"  ║  {self.tension.render_bar(38):<63}║")
        print(f"  ╠{'═'*65}╣")
        print(f"  ║  Current Stage: {stage.label:<48}║")
        print(f"  ║  Effect:        {stage.desc:<48}║")
        print(f"  ╠{'═'*65}╣")
        stages_info = [
            (EscalationStage.NORMAL,      "  0–39",  "No intel"),
            (EscalationStage.ALERT,       " 40–69",  "Radar blips visible"),
            (EscalationStage.PEAK_MOMENT, " 70–89",  "Group zone + heading revealed"),
            (EscalationStage.CRITICAL,    " 90–99",  "Formation + target landmark"),
            (EscalationStage.TOTAL_WAR,   "   100",  "FULL POSITIONS for 5 ticks"),
        ]
        for s, rng, desc in stages_info:
            active = "◀ ACTIVE" if s == stage else "        "
            icon   = s.desc.split()[0]
            print(f"  ║  {icon} {rng}  {desc:<42} {active} ║")
        print(f"  ╚{'═'*65}╝")

    def render_engagement_log(self):
        print(f"\n  ⚔️  ENGAGEMENT LOG ({len(self.engagements)} events):")
        print(f"  {'─'*70}")
        if not self.engagements:
            print("  (no engagements triggered yet)")
        for ev in self.engagements:
            print(f"    [{ev.engage_id}] T{ev.tick:03d}  "
                  f"{ev.team_a} vs {ev.team_b}  "
                  f"Zone:[{ev.zone}]  Dist:{ev.distance:.1f}u  "
                  f"Code:{ev.relay_code}")
        if self.active_engagement:
            print(f"\n  🔴 ACTIVE ENGAGEMENT: {self.active_engagement.relay_code}")

    def render_decoy_status(self):
        active = [d for d in self.decoys if d.is_active(self.tick_num)]
        if active:
            print(f"\n  🎭 Active Decoy Beacons:")
            for d in active:
                print(d.render(self.tick_num))

    def render_ghost_agents(self, all_players: List[PlayerEntity]):
        ghosts = [p for p in all_players if p.ghost_active]
        if ghosts:
            print(f"\n  👻 Ghost-Active Agents (hidden from intel):")
            for p in ghosts:
                ttl = p.ghost_expires - self.tick_num
                print(f"    [{p.agent_id}] ({p.team}) TTL:{ttl}t")

    def flush_log(self):
        out = self.log[:]
        self.log.clear()
        return out

# ─────────────────────────────────────────────────────────────────────
#  DEMO
# ─────────────────────────────────────────────────────────────────────

def run_enemy_nav_demo():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║         BACKEND 6 — ENEMY PLAYER NAVIGATION DEMO                       ║
║  Tension Meter · Peak Moment · Group Intel · Total War · Engagements    ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)

    engine = EnemyPlayerNavEngine()

    # Build player entities
    alpha = [
        PlayerEntity("Ignis-Prime",   "ALPHA", "Fire",    (22.0, 22.0), speed=8.0,  hp=280, max_hp=280),
        PlayerEntity("AquaVex",       "ALPHA", "Water",   (25.0, 20.0), speed=6.5,  hp=320, max_hp=320),
        PlayerEntity("Volt-Surge",    "ALPHA", "Thunder", (20.0, 25.0), speed=10.0, hp=250, max_hp=250),
        PlayerEntity("TerraKnight",   "ALPHA", "Earth",   (24.0, 24.0), speed=5.0,  hp=400, max_hp=400),
    ]
    omega = [
        PlayerEntity("Sylvan-Wraith", "OMEGA", "Grass",   (178.0,178.0), speed=7.0,  hp=300, max_hp=300),
        PlayerEntity("DustSerpent",   "OMEGA", "Sand",    (180.0,175.0), speed=9.0,  hp=270, max_hp=270),
        PlayerEntity("ZephyrBlade",   "OMEGA", "Flying",  (175.0,180.0), speed=12.0, hp=240, max_hp=240),
        PlayerEntity("Voidwalker",    "OMEGA", "Dark",    (179.0,179.0), speed=8.5,  hp=290, max_hp=290),
    ]

    # Set march routes (both teams converging on Parliament)
    march_alpha = [(50.0,50.0),(80.0,80.0),(100.0,100.0)]
    march_omega = [(150.0,150.0),(120.0,120.0),(100.0,100.0)]
    for p in alpha: p.waypoints = march_alpha.copy(); p.wp_idx = 0
    for p in omega: p.waypoints = march_omega.copy(); p.wp_idx = 0

    print("  Both teams converging on Parliament Hall...\n")

    for t in range(1, 45):
        # Inject tension events at specific ticks
        if t == 3:
            engine.event_kill("Ignis-Prime", "Rogue-01", "ALPHA")
        if t == 6:
            engine.event_capture("TerraKnight", "West_Tower")
            engine.event_capture("Volt-Surge", "Clock_Tower")
        if t == 8:
            engine.event_kill("AquaVex", "Rogue-02", "ALPHA")
            engine.event_kill("ZephyrBlade", "Rogue-03", "OMEGA")
        if t == 10:
            engine.event_boss_kill("Sylvan-Wraith", "Elite_Void")
        if t == 12:
            engine.event_capture("Voidwalker", "East_Tower")
            engine.event_kill("DustSerpent", "Rogue-04", "OMEGA")
        if t == 14:
            # Ghost move from dark/flying agents
            print(f"\n  ⚡ [EVENT T{t}] Voidwalker activates Ghost Move!")
            omega[3].activate_ghost(t, engine.log)
            print(f"\n  ⚡ [EVENT T{t}] DustSerpent deploys Decoy near South Shore!")
            engine.deploy_decoy(omega[1], (150.0, 185.0), engine.log)
        if t == 18:
            engine.event_kill("Ignis-Prime", "ZephyrBlade", "ALPHA")
            omega[2].hp = 0   # ZephyrBlade defeated
        if t == 20:
            engine.event_capture("Ignis-Prime", "Parliament_Hall")
            engine.event_kill("TerraKnight", "Elite_Magma", "ALPHA")
            engine.event_boss_kill("TerraKnight", "GM_StormLord")

        engine.tick(alpha, omega)
        logs = engine.flush_log()

        # Print logs at key moments
        if t <= 3 or t % 8 == 0:
            for line in logs:
                print(line)

        # Show full display at key tension thresholds
        stage = engine.tension.stage
        if t in (5, 12, 18, 25, 35, 44):
            engine.render_tension_overview()
            engine.render_intel_for_team("ALPHA", t)
            engine.render_intel_for_team("OMEGA", t)
            engine.render_decoy_status()
            engine.render_ghost_agents(alpha + omega)

    # Final summary
    engine.render_tension_overview()
    engine.render_engagement_log()
    print(f"\n  📊 Final Tension: {engine.tension.value:.1f}/100")
    print(f"  🎭 Total Decoys Deployed: {engine.decoy_seq}")
    print(f"  ⚔️  Combat Engagements:   {len(engine.engagements)}")
    print(f"  Total Ticks Run:          {engine.tick_num}\n")

if __name__ == "__main__":
    run_enemy_nav_demo()
