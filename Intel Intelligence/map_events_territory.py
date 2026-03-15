"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — DESTRUCTIBLE MAP EVENTS + TERRITORY CONTROL ENGINE          ║
║   Siege Mechanics · Road Blocking · Point Decay · Contested Zones       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from shared_constants import *

# ── Destructible object definitions ───────────────────────────────────
DESTRUCTIBLES: Dict[str, Dict] = {
    "Clock_Tower": {
        "hp": 500, "armor": 40, "repair_hp": 500,
        "siege_agents_needed": 2,  "siege_ticks": 30,
        "effect_active":   "Radar node active at Clock_Tower",
        "effect_destroyed":"Clock_Tower radar node OFFLINE. Sniper advantage lost.",
        "icon": "🕰️", "repair_cost": 60,   # metaenergy
    },
    "Parliament_Gate": {
        "hp": 800, "armor": 80, "repair_hp": 800,
        "siege_agents_needed": 3,  "siege_ticks": 45,
        "effect_active":   "Parliament interior sealed. Defenders get DEF +20%",
        "effect_destroyed":"Gates breached! Parliament interior accessible.",
        "icon": "🚪", "repair_cost": 100,
    },
    "East_Road_Bridge": {
        "hp": 300, "armor": 20, "repair_hp": 300,
        "siege_agents_needed": 1, "siege_ticks": 15,
        "effect_active":   "East road passable at full speed",
        "effect_destroyed":"East road BLOCKED. Agents must detour (+20 units).",
        "icon": "🌉", "repair_cost": 30,
    },
    "West_Road_Bridge": {
        "hp": 300, "armor": 20, "repair_hp": 300,
        "siege_agents_needed": 1, "siege_ticks": 15,
        "effect_active":   "West road passable at full speed",
        "effect_destroyed":"West road BLOCKED. Agents must detour (+20 units).",
        "icon": "🌉", "repair_cost": 30,
    },
    "North_Stadium_Wall": {
        "hp": 400, "armor": 50, "repair_hp": 400,
        "siege_agents_needed": 2, "siege_ticks": 20,
        "effect_active":   "Stadium walls up. ATK bonus inside stadium active.",
        "effect_destroyed":"Stadium walls FALLEN. ATK bonus lost.",
        "icon": "🏟️", "repair_cost": 45,
    },
    "Tectonic_Fault_A": {
        "hp": 0,   "armor": 0,  "repair_hp": 0,
        "siege_agents_needed": 0, "siege_ticks": 0,
        "effect_active":   "(dormant) Earth agents can trigger earthquake here",
        "effect_destroyed":"EARTHQUAKE TRIGGERED — area around Battle_Ground_A damaged!",
        "icon": "💥", "repair_cost": 0,
        "triggered_by": "Earth",
    },
}

@dataclass
class DestructibleObject:
    obj_id:    str
    hp:        float
    max_hp:    float
    armor:     float
    siege_agents_needed: int
    siege_ticks_total:   int
    siege_progress:      float = 0.0   # 0–100
    is_destroyed:        bool  = False
    is_being_sieged:     bool  = False
    sieging_team:        Optional[str] = None
    sieging_agents:      List[str] = field(default_factory=list)
    repaired_by:         Optional[str] = None
    repair_progress:     float = 0.0

    def siege_tick(self, agents_present: int) -> float:
        """Returns progress gained this tick."""
        if self.is_destroyed or self.is_being_sieged is False:
            return 0.0
        effectiveness = min(agents_present / self.siege_agents_needed, 1.5)
        progress      = (100.0 / self.siege_ticks_total) * effectiveness
        self.siege_progress = min(100.0, self.siege_progress + progress)
        if self.siege_progress >= 100.0:
            self.is_destroyed = True
        return progress

    def take_damage(self, damage: float, attacker_element: str) -> float:
        if self.is_destroyed: return 0.0
        # Tectonic Shift (Earth) deals double to structural objects
        mult = 2.0 if attacker_element == "Earth" else 1.0
        actual = max(0, damage * mult - self.armor * 0.3)
        self.hp = max(0.0, self.hp - actual)
        if self.hp <= 0:
            self.is_destroyed = True
        return actual

    def repair_tick(self, agents: int) -> float:
        if not self.is_destroyed: return 0.0
        rate = 5.0 * agents
        self.repair_progress = min(100.0, self.repair_progress + rate)
        if self.repair_progress >= 100.0:
            self.hp          = self.max_hp
            self.is_destroyed= False
            self.siege_progress = 0.0
            self.repair_progress = 0.0
        return rate

    def hp_bar_str(self) -> str:
        if self.is_destroyed: return "💔 DESTROYED"
        return f"[{hp_bar(self.hp, self.max_hp, 12)}] {self.hp:.0f}/{self.max_hp:.0f}"

    def render(self) -> str:
        defn   = DESTRUCTIBLES[self.obj_id]
        icon   = defn["icon"]
        siege  = (f"⚒️ SIEGE {self.siege_progress:.0f}% "
                  f"by {self.sieging_team}"
                  if self.is_being_sieged else "")
        repair = (f"🔧 REPAIR {self.repair_progress:.0f}%"
                  if self.repair_progress > 0 else "")
        return (f"  {icon} {self.obj_id:<22} {self.hp_bar_str():<28} "
                f"{siege}{repair}")


# ── Territory control ──────────────────────────────────────────────────
@dataclass
class TerritoryPoint:
    name:        str
    position:    Tuple[float, float]
    owner:       str = "Neutral"       # ALPHA | OMEGA | Neutral
    capture_pct: float = 0.0           # 0–100 toward current captor
    contest_pct: float = 0.0           # conflict level
    is_contested:bool  = False
    decay_rate:  float = 2.0           # pct lost per tick if unguarded
    cap_rate:    float = 8.0           # pct gained per tick per agent
    guards:      Dict[str, List[str]] = field(default_factory=dict)  # team→agents
    score_bonus: int   = 2             # score per tick while owned
    held_ticks:  int   = 0             # how long continuously held
    total_caps:  Dict[str, int] = field(default_factory=lambda: {"ALPHA":0,"OMEGA":0})

    def tick(self, alpha_agents: List[str], omega_agents: List[str],
             log: List[str]) -> Optional[str]:
        """
        Process one tick of capture/contest/decay.
        Returns team name if just captured, else None.
        """
        self.guards["ALPHA"] = alpha_agents
        self.guards["OMEGA"] = omega_agents
        a_count = len(alpha_agents)
        o_count = len(omega_agents)

        # ── Contest ────────────────────────────────────────────────
        if a_count > 0 and o_count > 0:
            if not self.is_contested:
                self.is_contested = True
                log.append(f"  ⚔️  [{self.name}] CONTESTED! "
                           f"ALPHA:{a_count} vs OMEGA:{o_count}")
            self.contest_pct = min(100.0, self.contest_pct + 5.0)
            # No capture progress during contest
            self.held_ticks = 0
            return None

        # Contest resolved
        if self.is_contested and (a_count == 0 or o_count == 0):
            self.is_contested = False
            self.contest_pct  = max(0.0, self.contest_pct - 10.0)
            winner_team = "ALPHA" if a_count > 0 else "OMEGA"
            log.append(f"  ✅ [{self.name}] Contest resolved — {winner_team} holds!")

        # ── Capture ────────────────────────────────────────────────
        capturing_team = None
        capturing_agents = 0
        if a_count > 0:
            capturing_team   = "ALPHA"
            capturing_agents = a_count
        elif o_count > 0:
            capturing_team   = "OMEGA"
            capturing_agents = o_count

        if capturing_team:
            if capturing_team == self.owner:
                # Reinforce held point
                self.held_ticks += 1
            elif self.owner == "Neutral":
                self.capture_pct = min(100.0,
                    self.capture_pct + self.cap_rate * capturing_agents)
                if self.capture_pct >= 100.0:
                    old_owner  = self.owner
                    self.owner = capturing_team
                    self.total_caps[capturing_team] += 1
                    self.held_ticks = 0
                    log.append(f"  🚩 [{self.name}] CAPTURED by {capturing_team}! "
                               f"(from {old_owner})")
                    return capturing_team
            else:
                # Neutralizing enemy point
                self.capture_pct = max(0.0,
                    self.capture_pct - self.cap_rate * capturing_agents)
                if self.capture_pct <= 0.0:
                    old_owner  = self.owner
                    self.owner = "Neutral"
                    log.append(f"  ⬜ [{self.name}] NEUTRALIZED "
                               f"(was {old_owner})")
        else:
            # Unguarded — decay toward neutral
            if self.owner != "Neutral":
                self.capture_pct = max(0.0, self.capture_pct - self.decay_rate)
                if self.capture_pct <= 0.0:
                    log.append(f"  📉 [{self.name}] DECAYED to Neutral "
                               f"(was {self.owner})")
                    self.owner = "Neutral"
        return None

    def render(self) -> str:
        owner_icon = {"ALPHA":"🔶","OMEGA":"🔷","Neutral":"⬜"}.get(self.owner,"⬜")
        contest    = " ⚔️CONTESTED" if self.is_contested else ""
        guards_str = (f"A:{len(self.guards.get('ALPHA',[]))} "
                      f"O:{len(self.guards.get('OMEGA',[]))}")
        return (f"  {owner_icon} {self.name:<22} {self.capture_pct:>5.1f}%  "
                f"Held:{self.held_ticks:3d}t  Guards:[{guards_str}]"
                f"  Caps A:{self.total_caps['ALPHA']} O:{self.total_caps['OMEGA']}"
                f"{contest}")


class MapEventsEngine:
    """
    Manages all destructible objects and territory points.
    Processes siege mechanics, road blocking, point capture, and decay.
    """
    def __init__(self):
        self.destructibles: Dict[str, DestructibleObject] = {
            k: DestructibleObject(
                obj_id   = k,
                hp       = v["hp"], max_hp = v["hp"],
                armor    = v["armor"],
                siege_agents_needed = v["siege_agents_needed"],
                siege_ticks_total   = max(1, v["siege_ticks"]),
            )
            for k, v in DESTRUCTIBLES.items()
            if v["hp"] > 0
        }
        self.territory: Dict[str, TerritoryPoint] = {
            k: TerritoryPoint(name=k, position=LANDMARKS[k])
            for k in KEY_POINTS
        }
        self.tick_num  = 0
        self.log:      List[str] = []
        self.scores:   Dict[str, int] = {"ALPHA":0,"OMEGA":0}
        self.blocked_roads: Set[str] = set()

    def tick(self, agent_positions: Dict[str, Tuple[str, Tuple[float,float]]]):
        """
        agent_positions: {agent_id: (team, (x,y))}
        """
        self.tick_num += 1

        # ── Siege processing ───────────────────────────────────────
        for obj_id, obj in self.destructibles.items():
            if obj.is_destroyed: continue
            obj_pos = LANDMARKS.get(obj_id, (100.0,100.0))
            near_agents = {team: [aid for aid,(tm,pos) in agent_positions.items()
                                  if tm == team and dist(pos, obj_pos) < 12]
                           for team in ["ALPHA","OMEGA"]}
            # Determine if any team is sieging
            for team, agents in near_agents.items():
                enemy_team = "OMEGA" if team == "ALPHA" else "ALPHA"
                enemy_near = near_agents.get(enemy_team, [])
                if len(agents) >= obj.siege_agents_needed and not enemy_near:
                    if obj.sieging_team != team:
                        obj.is_being_sieged = True
                        obj.sieging_team    = team
                        obj.sieging_agents  = agents
                        self.log.append(
                            f"  ⚒️  SIEGE STARTED: [{obj_id}] by {team} "
                            f"({len(agents)} agents)")
                    progress = obj.siege_tick(len(agents))
                    if obj.is_destroyed:
                        self.log.append(
                            f"  💥 [{obj_id}] DESTROYED by {team}! "
                            f"{DESTRUCTIBLES[obj_id]['effect_destroyed']}")
                        if "Road" in obj_id or "Bridge" in obj_id:
                            self.blocked_roads.add(obj_id)

        # ── Territory capture ──────────────────────────────────────
        for pt_name, pt in self.territory.items():
            pt_pos = LANDMARKS[pt_name]
            alpha_here = [aid for aid,(tm,pos) in agent_positions.items()
                          if tm == "ALPHA" and dist(pos, pt_pos) < 10]
            omega_here = [aid for aid,(tm,pos) in agent_positions.items()
                          if tm == "OMEGA" and dist(pos, pt_pos) < 10]
            captured   = pt.tick(alpha_here, omega_here, self.log)

        # ── Score update ───────────────────────────────────────────
        for pt in self.territory.values():
            if pt.owner in ("ALPHA","OMEGA"):
                self.scores[pt.owner] += pt.score_bonus

    def trigger_destructible_event(self, agent_id: str, element: str,
                                   pos: Tuple[float,float]):
        """Called when Earth agent uses Tectonic Shift."""
        if element == "Earth":
            nearby_destructibles = [
                obj for obj_id, obj in self.destructibles.items()
                if not obj.is_destroyed and dist(pos, LANDMARKS.get(obj_id,(200,200))) < 25
            ]
            for obj in nearby_destructibles:
                dmg = random.uniform(80, 140)
                actual = obj.take_damage(dmg, "Earth")
                self.log.append(f"  🌍 [{agent_id}] Tectonic Shift damaged "
                               f"[{obj.obj_id}] for {actual:.0f}!")
                if obj.is_destroyed:
                    self.log.append(f"  💥 [{obj.obj_id}] COLLAPSED from earthquake!")

    def is_road_blocked(self, road_id: str) -> bool:
        return road_id in self.blocked_roads

    def repair(self, obj_id: str, team: str, agent_count: int):
        obj = self.destructibles.get(obj_id)
        if obj and obj.is_destroyed:
            rate = obj.repair_tick(agent_count)
            if not obj.is_destroyed:
                self.log.append(f"  🔧 [{obj_id}] REPAIRED by {team}!")
                if obj_id in self.blocked_roads:
                    self.blocked_roads.discard(obj_id)

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render_destructibles(self):
        print(f"\n  ╔══ DESTRUCTIBLE OBJECTS ══╗")
        for obj_id, obj in self.destructibles.items():
            print(obj.render())
        if self.blocked_roads:
            print(f"\n  🚫 BLOCKED ROADS: {', '.join(self.blocked_roads)}")

    def render_territory(self):
        print(f"\n  ╔══ TERRITORY CONTROL ══╗")
        for pt in self.territory.values():
            print(pt.render())
        print(f"\n  🏆 Territory Scores:  "
              f"🔶 ALPHA: {self.scores['ALPHA']}  "
              f"🔷 OMEGA: {self.scores['OMEGA']}")

    def render_all(self):
        self.render_destructibles()
        self.render_territory()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ DESTRUCTIBLE MAP + TERRITORY CONTROL DEMO ══╗\n")
    engine = MapEventsEngine()

    # Simulated agent positions: {id: (team, (x,y))}
    agent_pos = {
        "Ignis-Prime":   ("ALPHA", (100.0,100.0)),
        "AquaVex":       ("ALPHA", (100.0,100.0)),
        "Volt-Surge":    ("ALPHA", (100.0, 60.0)),
        "TerraKnight":   ("ALPHA", ( 40.0,100.0)),
        "Sylvan-Wraith": ("OMEGA", (100.0, 60.0)),  # contesting Clock Tower
        "DustSerpent":   ("OMEGA", (160.0,100.0)),
        "ZephyrBlade":   ("OMEGA", (160.0,100.0)),
        "Voidwalker":    ("OMEGA", (178.0,178.0)),
    }

    for t in range(1, 30):
        engine.tick(agent_pos)
        for line in engine.flush_log(): print(line)

        # Move ALPHA toward capturing more points
        if t == 5:
            agent_pos["AquaVex"] = ("ALPHA", (100.0,30.0))   # North Stadium
        if t == 10:
            agent_pos["Volt-Surge"] = ("ALPHA", (160.0,100.0))   # East Tower

        # OMEGA sieges Clock Tower at tick 12
        if t == 12:
            engine.tick_num = 12
            agent_pos["Sylvan-Wraith"] = ("OMEGA",(100.0,60.0))
            agent_pos["ZephyrBlade"]   = ("OMEGA",(100.0,60.0))
            print(f"\n  ⚡ [EVENT T{t}] OMEGA sieging Clock_Tower with 2 agents!")
            # Start siege manually
            ct_obj = engine.destructibles.get("Clock_Tower")
            if ct_obj:
                ct_obj.is_being_sieged = True
                ct_obj.sieging_team    = "OMEGA"

        # TerraKnight uses Tectonic Shift at tick 18
        if t == 18:
            print(f"\n  ⚡ [EVENT T{t}] TerraKnight triggers Tectonic Shift!")
            engine.trigger_destructible_event("TerraKnight", "Earth", (40.0,100.0))

        if t % 8 == 0:
            engine.render_all()

    engine.render_all()
    print()
