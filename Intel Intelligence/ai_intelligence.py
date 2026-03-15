"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — AI INTELLIGENCE: MEMORY · PERSONALITY · STAMINA · HIVEMIND ║
║   Last Known Positions · Behaviour Drift · Sprint/Fatigue · Coordination║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import deque
from shared_constants import *

# ─────────────────────────────────────────────────────────────────────
#  1. AGENT MEMORY SYSTEM
# ─────────────────────────────────────────────────────────────────────

MEMORY_TTL        = 20    # ticks before last-seen memory expires
DANGER_ZONE_TTL   = 15    # avoid a zone this many ticks after getting killed there
MAX_MEMORY_ENTRIES = 12

@dataclass
class MemoryEntry:
    target_id:   str
    last_pos:    Tuple[float,float]
    seen_at_tick: int
    threat_level: float   # 0–1 based on HP difference when seen
    was_killed_here: bool = False   # agent was killed near this position

    def is_fresh(self, current_tick: int) -> bool:
        return (current_tick - self.seen_at_tick) < MEMORY_TTL

    def staleness(self, current_tick: int) -> float:
        age = current_tick - self.seen_at_tick
        return min(1.0, age / MEMORY_TTL)


class AgentMemory:
    """
    Per-agent memory of enemy positions, danger zones, and learned routes.
    Agents remember:
      - Last seen position of each enemy (fades over 20 ticks)
      - Routes that led to deaths (avoid for 15 ticks)
      - Routes that led to successful kills (prefer for 10 ticks)
    """
    def __init__(self, owner_id: str):
        self.owner_id    = owner_id
        self.entries:    Dict[str, MemoryEntry] = {}
        self.danger_zones: List[Dict] = []    # {pos, radius, expires_tick}
        self.preferred_routes: List[str] = []  # landmark names
        self.avoided_routes:   List[str] = []
        self.kill_log:   List[Dict] = []
        self.death_log:  List[Dict] = []

    def observe(self, target_id: str, pos: Tuple[float,float],
                tick: int, threat_level: float = 0.5):
        self.entries[target_id] = MemoryEntry(
            target_id    = target_id,
            last_pos     = pos,
            seen_at_tick = tick,
            threat_level = threat_level,
        )

    def record_kill(self, victim_id: str, pos: Tuple[float,float],
                    tick: int, via_landmark: str = ""):
        self.kill_log.append({"victim":victim_id,"pos":pos,"tick":tick})
        if via_landmark and via_landmark not in self.preferred_routes:
            self.preferred_routes.append(via_landmark)
            if len(self.preferred_routes) > 5:
                self.preferred_routes.pop(0)

    def record_death(self, pos: Tuple[float,float], tick: int,
                     near_landmark: str = ""):
        self.death_log.append({"pos":pos,"tick":tick})
        self.danger_zones.append({
            "pos":pos, "radius":20.0,
            "expires_tick": tick + DANGER_ZONE_TTL
        })
        if near_landmark and near_landmark not in self.avoided_routes:
            self.avoided_routes.append(near_landmark)

    def is_danger_zone(self, pos: Tuple[float,float], tick: int) -> bool:
        for zone in self.danger_zones:
            if (zone["expires_tick"] > tick and
                    dist(pos, zone["pos"]) < zone["radius"]):
                return True
        return False

    def get_last_known(self, target_id: str) -> Optional[MemoryEntry]:
        return self.entries.get(target_id)

    def get_fresh_targets(self, tick: int) -> List[MemoryEntry]:
        return [e for e in self.entries.values() if e.is_fresh(tick)]

    def purge_stale(self, tick: int):
        self.entries    = {k:v for k,v in self.entries.items() if v.is_fresh(tick)}
        self.danger_zones = [z for z in self.danger_zones if z["expires_tick"] > tick]

    def render(self, tick: int) -> str:
        lines = [f"  💾 Memory [{self.owner_id}]:"]
        fresh = self.get_fresh_targets(tick)
        if fresh:
            for e in fresh:
                age = tick - e.seen_at_tick
                lines.append(f"    👁️  {e.target_id:<18} last at "
                             f"({e.last_pos[0]:.0f},{e.last_pos[1]:.0f}) "
                             f"{age}t ago  threat:{e.threat_level:.1f}")
        else:
            lines.append("    (no fresh enemy sightings)")
        if self.danger_zones:
            lines.append(f"    🚫 Danger zones: {len(self.danger_zones)}")
        if self.preferred_routes:
            lines.append(f"    ✅ Preferred routes: {', '.join(self.preferred_routes)}")
        return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────
#  2. PERSONALITY DRIFT SYSTEM
# ─────────────────────────────────────────────────────────────────────

# Personality axes: each 0–100
# aggression: 0=passive, 100=reckless charge
# caution:    0=fearless, 100=extreme caution
# teamwork:   0=lone wolf, 100=stays with team
# confidence: 0=broken, 100=dominant

PERSONALITY_BASELINES: Dict[str, Dict] = {
    "Ignis-Prime":   {"aggression":75,"caution":20,"teamwork":45,"confidence":80},
    "AquaVex":       {"aggression":35,"caution":70,"teamwork":80,"confidence":60},
    "Volt-Surge":    {"aggression":85,"caution":15,"teamwork":55,"confidence":75},
    "TerraKnight":   {"aggression":45,"caution":55,"teamwork":85,"confidence":70},
    "Sylvan-Wraith": {"aggression":50,"caution":65,"teamwork":70,"confidence":60},
    "DustSerpent":   {"aggression":60,"caution":50,"teamwork":50,"confidence":65},
    "ZephyrBlade":   {"aggression":80,"caution":20,"teamwork":40,"confidence":78},
    "Voidwalker":    {"aggression":70,"caution":40,"teamwork":35,"confidence":72},
}

@dataclass
class PersonalityState:
    agent_id:   str
    aggression: float
    caution:    float
    teamwork:   float
    confidence: float
    drift_log:  List[str] = field(default_factory=list)

    def apply_kill(self, victim_id: str):
        """Getting a kill boosts aggression and confidence."""
        delta_agg  = random.uniform(3, 8)
        delta_conf = random.uniform(4, 10)
        self.aggression = min(100, self.aggression + delta_agg)
        self.confidence = min(100, self.confidence + delta_conf)
        self.caution    = max(0, self.caution - random.uniform(2, 5))
        self.drift_log.append(
            f"  📈 [{self.agent_id}] Kill of {victim_id} → "
            f"AGG+{delta_agg:.1f} CONF+{delta_conf:.1f}")

    def apply_death_of_ally(self, ally_id: str):
        """Losing an ally increases caution (AquaVex especially)."""
        delta_caut = random.uniform(5, 15)
        delta_conf = random.uniform(3, 10)
        self.caution    = min(100, self.caution + delta_caut)
        self.confidence = max(0, self.confidence - delta_conf)
        self.aggression = max(0, self.aggression - random.uniform(2, 6))
        self.drift_log.append(
            f"  📉 [{self.agent_id}] Ally {ally_id} lost → "
            f"CAUT+{delta_caut:.1f} CONF-{delta_conf:.1f}")

    def apply_own_death(self):
        """Own death sharply drops confidence, raises caution."""
        self.confidence = max(0, self.confidence - random.uniform(15, 25))
        self.caution    = min(100, self.caution + random.uniform(10, 20))
        self.aggression = max(0, self.aggression - random.uniform(8, 15))
        self.drift_log.append(
            f"  💀 [{self.agent_id}] Own death — confidence SHATTERED")

    def apply_winning_streak(self, kills: int):
        """Winning team drifts reckless — confidence spikes, caution falls."""
        boost = kills * 4.0
        self.aggression = min(100, self.aggression + boost * 0.7)
        self.confidence = min(100, self.confidence + boost)
        self.caution    = max(0, self.caution - boost * 0.5)
        self.drift_log.append(
            f"  🔥 [{self.agent_id}] Win streak×{kills} → "
            f"going RECKLESS (AGG:{self.aggression:.0f} CONF:{self.confidence:.0f})")

    def apply_losing_spiral(self, allies_lost: int):
        """Losing team becomes desperate — erratic aggression OR collapse."""
        if self.confidence < 40:
            # Desperation spike — goes all-in
            self.aggression = min(100, self.aggression + random.uniform(10, 20))
            self.drift_log.append(
                f"  😤 [{self.agent_id}] DESPERATE — going all-in!")
        else:
            # Cautious collapse
            self.caution    = min(100, self.caution + allies_lost * 8.0)
            self.confidence = max(0, self.confidence - allies_lost * 7.0)
            self.drift_log.append(
                f"  😰 [{self.agent_id}] Losing spiral — pulling back")

    def get_behaviour_weights(self) -> Dict[str, float]:
        """Convert personality into behaviour state weights."""
        return {
            "ATTACK":  self.aggression / 100.0,
            "SEARCH":  (self.aggression * 0.6 + self.confidence * 0.4) / 100.0,
            "DEFEND":  self.caution / 100.0,
            "SUPPORT": self.teamwork / 100.0,
            "RETREAT": max(0, (self.caution - self.confidence) / 100.0),
            "ROAM":    0.15,
        }

    def choose_behaviour(self) -> str:
        weights = self.get_behaviour_weights()
        total   = sum(weights.values())
        r       = random.random() * total
        cum     = 0.0
        for beh, w in weights.items():
            cum += w
            if r <= cum:
                return beh
        return "ROAM"

    def chat_tone(self) -> str:
        if self.confidence >= 80 and self.aggression >= 70:
            return "boastful"
        if self.confidence < 35:
            return "distress"
        if self.caution >= 75:
            return "quiet"
        return "normal"

    def flush_drift_log(self) -> List[str]:
        out = self.drift_log[:]
        self.drift_log.clear()
        return out

    def render(self) -> str:
        tone = self.chat_tone()
        tone_icon = {"boastful":"😤","distress":"😱","quiet":"😶","normal":"😐"}.get(tone,"")
        return (f"  {tone_icon} [{self.agent_id:<18}] "
                f"AGG:{self.aggression:5.1f} "
                f"CAUT:{self.caution:5.1f} "
                f"TEAM:{self.teamwork:5.1f} "
                f"CONF:{self.confidence:5.1f}  "
                f"Tone:{tone}")


class PersonalityDriftEngine:
    def __init__(self):
        self.states: Dict[str, PersonalityState] = {
            aid: PersonalityState(aid, **PERSONALITY_BASELINES[aid])
            for aid in PERSONALITY_BASELINES
        }
        self.kill_counts: Dict[str, int] = {aid:0 for aid in PERSONALITY_BASELINES}

    def on_kill(self, killer_id: str, victim_id: str):
        self.kill_counts[killer_id] = self.kill_counts.get(killer_id, 0) + 1
        if killer_id in self.states:
            self.states[killer_id].apply_kill(victim_id)
            kills = self.kill_counts[killer_id]
            if kills >= 2:
                self.states[killer_id].apply_winning_streak(kills)

    def on_ally_death(self, ally_id: str, team: str):
        team_agents = ALPHA_AGENTS if team == "ALPHA" else OMEGA_AGENTS
        allies_lost = sum(1 for a in team_agents
                          if a in self.states and self.states[a].confidence < 50)
        for agent_id in team_agents:
            if agent_id != ally_id and agent_id in self.states:
                self.states[agent_id].apply_death_of_ally(ally_id)
                if allies_lost >= 2:
                    self.states[agent_id].apply_losing_spiral(allies_lost)

    def on_own_death(self, agent_id: str):
        if agent_id in self.states:
            self.states[agent_id].apply_own_death()

    def flush_all_logs(self) -> List[str]:
        lines = []
        for s in self.states.values():
            lines.extend(s.flush_drift_log())
        return lines

    def render_all(self):
        print(f"\n  ╔══ PERSONALITY STATES ══╗")
        print(f"  {'Agent':<20} {'AGG':>6} {'CAUT':>6} {'TEAM':>6} {'CONF':>6}  Tone")
        print(f"  {'─'*60}")
        for s in self.states.values():
            print(s.render())


# ─────────────────────────────────────────────────────────────────────
#  3. STAMINA / FATIGUE SYSTEM
# ─────────────────────────────────────────────────────────────────────

MAX_STAMINA         = 100.0
SPRINT_DRAIN        = 12.0   # per tick while sprinting
WALK_DRAIN          = 1.0    # per tick while moving at normal speed
REGEN_RATE          = 2.0    # per tick while stationary
SPRINT_THRESHOLD    = 5      # ticks sprinting before penalty kicks in
PENALTY_SPEED_MULT  = 0.70   # 30% speed reduction when fatigued
STAMINA_WARN        = 25.0   # low stamina threshold

@dataclass
class StaminaState:
    owner_id:    str
    stamina:     float = MAX_STAMINA
    is_sprinting:bool  = False
    sprint_ticks:int   = 0
    is_fatigued: bool  = False
    fatigued_ticks:int = 0
    log: List[str] = field(default_factory=list)

    def tick(self, is_moving: bool, sprinting: bool,
             weather_drain_bonus: float = 0.0) -> float:
        """Returns current speed multiplier."""
        self.is_sprinting = sprinting and is_moving

        if self.is_sprinting:
            drain = SPRINT_DRAIN + weather_drain_bonus
            self.stamina    = max(0.0, self.stamina - drain)
            self.sprint_ticks += 1
            if self.sprint_ticks >= SPRINT_THRESHOLD and not self.is_fatigued:
                self.is_fatigued   = True
                self.fatigued_ticks = 0
                self.log.append(
                    f"  😮‍💨 [{self.owner_id}] FATIGUED after "
                    f"{self.sprint_ticks}t sprint! SPD −30%")
        elif is_moving:
            self.stamina    = max(0.0, self.stamina - WALK_DRAIN - weather_drain_bonus)
            self.sprint_ticks = max(0, self.sprint_ticks - 1)
        else:
            # Stationary: regen
            old = self.stamina
            self.stamina = min(MAX_STAMINA, self.stamina + REGEN_RATE)
            self.sprint_ticks = max(0, self.sprint_ticks - 2)
            if self.is_fatigued and self.stamina > 40:
                self.is_fatigued    = False
                self.fatigued_ticks = 0
                self.log.append(f"  💪 [{self.owner_id}] Recovered from fatigue")

        if self.is_fatigued:
            self.fatigued_ticks += 1

        # Stamina warning
        if self.stamina <= STAMINA_WARN and self.stamina > 0:
            if random.random() < 0.3:
                self.log.append(
                    f"  ⚠️  [{self.owner_id}] LOW STAMINA ({self.stamina:.0f})")

        # Speed modifier
        if self.is_fatigued:
            return PENALTY_SPEED_MULT
        if self.is_sprinting:
            return 1.35  # sprint bonus
        return 1.0

    def effective_speed(self, base_speed: float, is_moving: bool,
                        sprinting: bool, weather_drain: float = 0.0) -> float:
        mult = self.tick(is_moving, sprinting, weather_drain)
        return base_speed * mult

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self) -> str:
        bar   = hp_bar(self.stamina, MAX_STAMINA, 12)
        state = "🏃SPRINT" if self.is_sprinting else ("😮‍💨FATIGUED" if self.is_fatigued else "🚶walk")
        return (f"  [{self.owner_id:<18}] STA:[{bar}] {self.stamina:5.1f}/100  "
                f"{state}  SprintT:{self.sprint_ticks}")


# ─────────────────────────────────────────────────────────────────────
#  4. HIVEMIND PROTOCOL
# ─────────────────────────────────────────────────────────────────────

HIVEMIND_RADIUS      = 20.0    # units — agents within this range = hivemind
HIVEMIND_MIN_AGENTS  = 3
HIVEMIND_AOE_BONUS   = 0.20    # +20% AOE effectiveness
HIVEMIND_VISION_SHARE= True    # agents share full vision in hivemind
SPLIT_ACCURACY_PENALTY = 0.15  # −15% accuracy if hivemind broken

@dataclass
class HivemindState:
    team:          str
    active:        bool       = False
    member_ids:    List[str]  = field(default_factory=list)
    center:        Tuple[float,float] = (100.0,100.0)
    formed_tick:   int        = 0
    ticks_active:  int        = 0
    was_active:    bool       = False   # was hivemind active last tick
    split_tick:    Optional[int] = None  # when it broke
    log: List[str] = field(default_factory=list)

    def tick(self, agent_positions: Dict[str, Tuple[float,float]],
             tick: int) -> bool:
        self.was_active = self.active
        positions = list(agent_positions.values())
        ids       = list(agent_positions.keys())

        if not positions:
            self.active = False
            return False

        centroid = midpoint(positions)

        # Count agents within hivemind radius of centroid
        near = [(aid, pos) for aid, pos in agent_positions.items()
                if dist(pos, centroid) <= HIVEMIND_RADIUS]

        if len(near) >= HIVEMIND_MIN_AGENTS:
            members = [aid for aid, _ in near]
            if not self.active:
                self.active      = True
                self.formed_tick = tick
                self.member_ids  = members
                self.center      = centroid
                self.log.append(
                    f"  🧠 [{self.team}] HIVEMIND FORMED! "
                    f"Members: {', '.join(members)}"
                    f" — AOE +{HIVEMIND_AOE_BONUS*100:.0f}% | Vision shared")
            else:
                self.member_ids = members
                self.center     = centroid
                self.ticks_active += 1
        else:
            if self.active:
                # Hivemind broken
                self.split_tick = tick
                self.log.append(
                    f"  💔 [{self.team}] HIVEMIND BROKEN! "
                    f"Agents spreading — accuracy −{SPLIT_ACCURACY_PENALTY*100:.0f}%"
                    f" for 5 ticks")
            self.active     = False
            self.member_ids = []

        return self.active

    def get_aoe_multiplier(self, agent_id: str) -> float:
        if self.active and agent_id in self.member_ids:
            return 1.0 + HIVEMIND_AOE_BONUS
        return 1.0

    def get_accuracy_penalty(self, agent_id: str, current_tick: int) -> float:
        if (not self.active and self.split_tick and
                current_tick - self.split_tick < 5):
            return SPLIT_ACCURACY_PENALTY
        return 0.0

    def is_member(self, agent_id: str) -> bool:
        return self.active and agent_id in self.member_ids

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self) -> str:
        if self.active:
            return (f"  🧠 HIVEMIND ACTIVE [{self.team}] "
                    f"Members: {', '.join(self.member_ids)}  "
                    f"Duration:{self.ticks_active}t  "
                    f"Center:({self.center[0]:.0f},{self.center[1]:.0f})")
        return f"  💤 Hivemind INACTIVE [{self.team}]"


# ─────────────────────────────────────────────────────────────────────
#  UNIFIED AI INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────

class AIIntelligenceEngine:
    def __init__(self):
        all_agents = ALPHA_AGENTS + OMEGA_AGENTS
        self.memory    = {aid: AgentMemory(aid)  for aid in all_agents}
        self.stamina   = {aid: StaminaState(aid) for aid in all_agents}
        self.personality_engine = PersonalityDriftEngine()
        self.hivemind  = {
            "ALPHA": HivemindState("ALPHA"),
            "OMEGA": HivemindState("OMEGA"),
        }
        self.tick_num  = 0

    def tick(self, agent_positions: Dict[str, Tuple[float,float]],
             sprinting_agents: Set[str], weather_drain: float = 0.0) -> Dict:
        self.tick_num += 1
        results = {}

        # Stamina
        for aid, sta in self.stamina.items():
            pos = agent_positions.get(aid)
            moving   = pos is not None
            sprinting= aid in sprinting_agents
            spd_mult = sta.tick(moving, sprinting, weather_drain)
            results[aid] = {"speed_mult": spd_mult}

        # Hivemind per team
        for team in ["ALPHA","OMEGA"]:
            team_agents = ALPHA_AGENTS if team == "ALPHA" else OMEGA_AGENTS
            team_pos    = {aid: agent_positions[aid]
                           for aid in team_agents if aid in agent_positions}
            self.hivemind[team].tick(team_pos, self.tick_num)

        # Purge stale memories
        for mem in self.memory.values():
            mem.purge_stale(self.tick_num)

        return results

    def on_enemy_sighted(self, observer_id: str, target_id: str,
                          target_pos: Tuple[float,float],
                          observer_hp_pct: float = 1.0, target_hp_pct: float = 1.0):
        mem = self.memory.get(observer_id)
        if mem:
            threat = target_hp_pct / max(observer_hp_pct, 0.01)
            mem.observe(target_id, target_pos, self.tick_num, threat)

        # Hivemind vision share
        team = TEAM_OF.get(observer_id, "")
        hm = self.hivemind.get(team)
        if hm and hm.is_member(observer_id):
            for ally in hm.member_ids:
                if ally != observer_id:
                    self.memory[ally].observe(
                        target_id, target_pos, self.tick_num, 0.5)

    def on_kill(self, killer_id: str, victim_id: str,
                kill_pos: Tuple[float, float]):
        self.personality_engine.on_kill(killer_id, victim_id)
        team = TEAM_OF.get(killer_id, "")
        victim_team = TEAM_OF.get(victim_id, "")
        self.personality_engine.on_ally_death(victim_id, victim_team)

    def on_death(self, agent_id: str, death_pos: Tuple[float,float]):
        near = nearest_landmark(death_pos)
        self.memory[agent_id].record_death(death_pos, self.tick_num, near)
        self.personality_engine.on_own_death(agent_id)

    def flush_all_logs(self) -> List[str]:
        lines = []
        for sta in self.stamina.values():
            lines.extend(sta.flush_log())
        for hm in self.hivemind.values():
            lines.extend(hm.flush_log())
        lines.extend(self.personality_engine.flush_all_logs())
        return lines

    def render_full(self):
        print(f"\n{'═'*70}")
        print(f"  🧠 AI INTELLIGENCE ENGINE — Tick {self.tick_num}")
        print(f"{'═'*70}")
        self.personality_engine.render_all()
        print(f"\n  STAMINA:")
        print(f"  {'Agent':<20} {'STA Bar':<18} {'Val':>6}  State")
        print(f"  {'─'*60}")
        for s in self.stamina.values():
            print(s.render())
        print(f"\n  HIVEMIND:")
        for hm in self.hivemind.values():
            print(f"  {hm.render()}")
        print()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ AI INTELLIGENCE ENGINE DEMO ══╗\n")
    engine = AIIntelligenceEngine()

    # Simulate positions — both teams converging
    positions = {
        "Ignis-Prime":   (50.0,50.0),  "AquaVex":       (55.0,50.0),
        "Volt-Surge":    (48.0,55.0),  "TerraKnight":   (52.0,53.0),
        "Sylvan-Wraith": (150.0,150.0),"DustSerpent":   (155.0,148.0),
        "ZephyrBlade":   (148.0,155.0),"Voidwalker":    (152.0,152.0),
    }
    sprinting = {"Volt-Surge", "ZephyrBlade"}

    print("  Phase 1: Teams at spawn, some agents sprinting\n")
    for t in range(1, 20):
        results = engine.tick(positions, sprinting)
        logs = engine.flush_all_logs()
        if logs: print("\n".join(logs))

        # Converge
        for aid in positions:
            team = TEAM_OF.get(aid,"")
            if team == "ALPHA":
                positions[aid] = (min(200,positions[aid][0]+3),
                                   min(200,positions[aid][1]+3))
            else:
                positions[aid] = (max(0,positions[aid][0]-3),
                                   max(0,positions[aid][1]-3))

        if t == 8:
            print(f"\n  ⚡ [EVENT T{t}] Ignis-Prime kills Sylvan-Wraith!")
            engine.on_kill("Ignis-Prime", "Sylvan-Wraith", (90.0,90.0))
            engine.on_death("Sylvan-Wraith", (90.0,90.0))

        if t == 12:
            print(f"\n  ⚡ [EVENT T{t}] Voidwalker kills AquaVex and Volt-Surge!")
            engine.on_kill("Voidwalker", "AquaVex",    (95.0,95.0))
            engine.on_kill("Voidwalker", "Volt-Surge", (98.0,93.0))
            engine.on_death("AquaVex",   (95.0,95.0))
            engine.on_death("Volt-Surge",(98.0,93.0))

    engine.render_full()
