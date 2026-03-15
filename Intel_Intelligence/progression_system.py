"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — PROGRESSION: XP · LEVELS · MATCH HISTORY · ELO/MMR         ║
║   Agent Leveling · Stat Upgrades · Replay Log · Skill-Based Rating      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import json, math, random, time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from shared_constants import *

# ─────────────────────────────────────────────────────────────────────
#  1. XP & LEVEL SYSTEM
# ─────────────────────────────────────────────────────────────────────

MAX_LEVEL   = 10
XP_PER_KILL  = 120
XP_PER_CAP   = 80
XP_PER_BOSS  = 250
XP_PER_ASSIST= 40
XP_PER_TICK  = 1     # passive XP for being alive

def xp_for_level(level: int) -> int:
    """XP needed to reach this level from level 1."""
    return int(100 * (level ** 1.6))

UPGRADEABLE_STATS = ["hp", "atk", "def", "spd", "range"]
STAT_UPGRADE_PCT  = 0.05   # +5% per level per stat

ULTIMATE_ABILITIES: Dict[str, Dict] = {
    "Ignis-Prime": {
        "name":"Solar Flare","dmg":200,"cd":20,"aoe":30.0,
        "effect":"burn","chance":1.0,
        "desc":"Calls down a solar flare — blankets 30u in fire"
    },
    "AquaVex": {
        "name":"Tidal Prison","dmg":80,"cd":18,"aoe":18.0,
        "effect":"freeze","chance":0.90,
        "desc":"Traps all enemies in zone in water prison for 4 ticks"
    },
    "Volt-Surge": {
        "name":"Thunderstorm God","dmg":180,"cd":20,"aoe":35.0,
        "effect":"stun","chance":0.85,
        "desc":"Calls divine thunderstorm — chains to every enemy on field"
    },
    "TerraKnight": {
        "name":"Worldbreaker","dmg":160,"cd":22,"aoe":25.0,
        "effect":"petrify","chance":0.80,
        "desc":"Shatters the ground — petrifies all enemies in radius"
    },
    "Sylvan-Wraith": {
        "name":"World Tree Wrath","dmg":170,"cd":20,"aoe":28.0,
        "effect":"root","chance":0.95,
        "desc":"Summons ancient tree roots across the battlefield"
    },
    "DustSerpent": {
        "name":"Desert Coffin","dmg":130,"cd":18,"aoe":20.0,
        "effect":"sandblind","chance":0.90,
        "desc":"Encases targets in sand — blind and slow"
    },
    "ZephyrBlade": {
        "name":"Eye of the Storm","dmg":190,"cd":21,"aoe":32.0,
        "effect":"stun","chance":0.75,
        "desc":"Becomes the center of a catastrophic hurricane"
    },
    "Voidwalker": {
        "name":"Void Collapse","dmg":220,"cd":22,"aoe":22.0,
        "effect":"drain","chance":1.0,
        "desc":"Collapses the void — steals life from all in zone"
    },
}

@dataclass
class AgentProgression:
    agent_id:  str
    element:   str
    team:      str
    level:     int   = 1
    xp:        int   = 0
    xp_to_next:int   = 0
    kills:     int   = 0
    assists:   int   = 0
    caps:      int   = 0
    boss_kills:int   = 0
    matches:   int   = 0
    wins:      int   = 0
    stat_upgrades: Dict[str, int] = field(default_factory=dict)
    ultimate_unlocked: bool = False
    ultimate_cooldown: int  = 0
    xp_log: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.xp_to_next = xp_for_level(2)
        self.stat_upgrades = {s: 0 for s in UPGRADEABLE_STATS}

    def add_xp(self, amount: int, reason: str):
        self.xp += amount
        self.xp_log.append(f"  +{amount:4d} XP [{reason}] → {self.xp}/{self.xp_to_next}")
        self._check_levelup()

    def _check_levelup(self):
        while self.level < MAX_LEVEL and self.xp >= self.xp_to_next:
            self.xp        -= self.xp_to_next
            self.level     += 1
            self.xp_to_next = xp_for_level(self.level + 1) if self.level < MAX_LEVEL else 999999
            stat   = self._choose_upgrade_stat()
            self.stat_upgrades[stat] += 1
            bonus  = f"+{STAT_UPGRADE_PCT*100:.0f}% {stat}"
            if self.level == MAX_LEVEL and not self.ultimate_unlocked:
                self.ultimate_unlocked = True
                ult = ULTIMATE_ABILITIES.get(self.agent_id, {})
                self.xp_log.append(
                    f"  ⭐ [{self.agent_id}] LEVEL {self.level}! ({bonus}) "
                    f"🔥 ULTIMATE UNLOCKED: [{ult.get('name','?')}]!")
            else:
                self.xp_log.append(
                    f"  ⭐ [{self.agent_id}] LEVEL UP → {self.level}! ({bonus})")

    def _choose_upgrade_stat(self) -> str:
        """Auto-pick stat least upgraded, with element bias."""
        element_pref = {
            "Fire":    ["atk","spd","range","hp","def"],
            "Water":   ["hp","def","range","spd","atk"],
            "Thunder": ["atk","range","spd","hp","def"],
            "Earth":   ["hp","def","atk","spd","range"],
            "Grass":   ["range","atk","hp","def","spd"],
            "Sand":    ["spd","atk","range","hp","def"],
            "Flying":  ["spd","range","atk","hp","def"],
            "Dark":    ["atk","spd","hp","range","def"],
        }
        pref = element_pref.get(self.element, UPGRADEABLE_STATS)
        for stat in pref:
            if self.stat_upgrades[stat] == min(self.stat_upgrades.values()):
                return stat
        return random.choice(UPGRADEABLE_STATS)

    def get_stat_multiplier(self, stat: str) -> float:
        upgrades = self.stat_upgrades.get(stat, 0)
        return 1.0 + (upgrades * STAT_UPGRADE_PCT)

    def use_ultimate(self, tick: int) -> Optional[Dict]:
        if not self.ultimate_unlocked:
            return None
        if self.ultimate_cooldown > 0:
            return None
        ult = ULTIMATE_ABILITIES.get(self.agent_id)
        if ult:
            self.ultimate_cooldown = ult["cd"]
            self.xp_log.append(
                f"  ⚡ [{self.agent_id}] Ultimate [{ult['name']}] USED!")
            return ult
        return None

    def tick_cooldown(self):
        self.ultimate_cooldown = max(0, self.ultimate_cooldown - 1)

    def flush_log(self) -> List[str]:
        out = self.xp_log[:]
        self.xp_log.clear()
        return out

    def xp_bar(self) -> str:
        if self.level >= MAX_LEVEL:
            return f"[{'█'*14}] MAX"
        filled = int((self.xp / max(self.xp_to_next,1)) * 14)
        return f"[{'█'*filled}{'░'*(14-filled)}] {self.xp}/{self.xp_to_next}"

    def render(self) -> str:
        ult_str = (f"⭐Ult:{ULTIMATE_ABILITIES.get(self.agent_id,{}).get('name','?')}"
                   if self.ultimate_unlocked else "🔒 Ult locked")
        return (f"  [{self.agent_id:<18}] Lv:{self.level:2d} {self.xp_bar()}"
                f"  K:{self.kills} A:{self.assists} C:{self.caps} BK:{self.boss_kills}"
                f"  {ult_str}")


# ─────────────────────────────────────────────────────────────────────
#  2. MATCH HISTORY & REPLAY LOG
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ActionRecord:
    tick:      int
    timestamp: str
    actor_id:  str
    action:    str    # "kill","cap","use_ability","move","flare","ultimate"
    target:    str    = ""
    position:  Tuple[float,float] = (0.0,0.0)
    value:     float  = 0.0
    extra:     str    = ""

    def to_dict(self) -> Dict:
        return {
            "tick": self.tick, "timestamp": self.timestamp,
            "actor": self.actor_id, "action": self.action,
            "target": self.target,
            "position": list(self.position),
            "value": round(self.value,2), "extra": self.extra
        }

    def render(self) -> str:
        action_icons = {
            "kill":"💀","cap":"🚩","use_ability":"✨",
            "move":"🚶","flare":"🔴","ultimate":"⭐",
            "damage":"⚔️","death":"💔","respawn":"♻️",
        }
        icon = action_icons.get(self.action,"📝")
        return (f"  T{self.tick:04d} {self.timestamp} "
                f"{icon} [{self.actor_id:<18}] {self.action:<14} "
                f"→ {self.target:<18} val:{self.value:7.1f}  {self.extra}")


class MatchLogger:
    def __init__(self, match_id: str = ""):
        self.match_id   = match_id or f"M{int(time.time())}"
        self.started_at = datetime.now().isoformat()
        self.records:   List[ActionRecord] = []
        self.tick_num   = 0

    def log(self, actor_id: str, action: str, target: str = "",
            position: Tuple[float,float] = (0.0,0.0),
            value: float = 0.0, extra: str = ""):
        ts  = datetime.now().strftime("%H:%M:%S")
        rec = ActionRecord(self.tick_num, ts, actor_id, action,
                           target, position, value, extra)
        self.records.append(rec)
        return rec

    def advance_tick(self):
        self.tick_num += 1

    def get_highlights(self) -> List[ActionRecord]:
        high_value = ["kill","ultimate","cap"]
        return [r for r in self.records if r.action in high_value]

    def get_replay_slice(self, from_tick: int, to_tick: int) -> List[ActionRecord]:
        return [r for r in self.records if from_tick <= r.tick <= to_tick]

    def replay(self, from_tick: int = 0, to_tick: int = 9999,
               highlight_only: bool = False):
        records = self.get_highlights() if highlight_only else self.records
        records = [r for r in records if from_tick <= r.tick <= to_tick]
        print(f"\n  🎬 REPLAY [{self.match_id}] T{from_tick}→T{to_tick}"
              f" ({len(records)} events):")
        print(f"  {'─'*90}")
        for r in records:
            print(r.render())

    def save_json(self, path: str = ""):
        data = {
            "match_id":   self.match_id,
            "started_at": self.started_at,
            "total_ticks":self.tick_num,
            "records":    [r.to_dict() for r in self.records],
        }
        path = path or f"match_{self.match_id}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def load_json(self, path: str):
        with open(path) as f:
            data = json.load(f)
        self.match_id   = data["match_id"]
        self.started_at = data["started_at"]
        self.tick_num   = data["total_ticks"]
        self.records    = [
            ActionRecord(
                r["tick"], r["timestamp"], r["actor"],
                r["action"], r["target"], tuple(r["position"]),
                r["value"], r["extra"]
            )
            for r in data["records"]
        ]
        return self

    def stats_summary(self) -> str:
        kills  = [r for r in self.records if r.action == "kill"]
        caps   = [r for r in self.records if r.action == "cap"]
        ults   = [r for r in self.records if r.action == "ultimate"]
        return (f"\n  📊 Match [{self.match_id}] Summary:\n"
                f"    Total ticks: {self.tick_num}\n"
                f"    Kill events: {len(kills)}\n"
                f"    Captures:    {len(caps)}\n"
                f"    Ultimates:   {len(ults)}\n"
                f"    Total events:{len(self.records)}")


# ─────────────────────────────────────────────────────────────────────
#  3. ELO / MMR RATING SYSTEM
# ─────────────────────────────────────────────────────────────────────

BASE_MMR          = 1200
K_FACTOR          = 32     # adjustment speed
KILL_WEIGHT       = 0.35
MAP_CONTROL_WEIGHT= 0.30
BOSS_WEIGHT       = 0.20
STRATEGY_WEIGHT   = 0.15

@dataclass
class TeamRating:
    team_name: str
    mmr:       float = float(BASE_MMR)
    wins:      int   = 0
    losses:    int   = 0
    draws:     int   = 0
    peak_mmr:  float = float(BASE_MMR)
    history:   List[Dict] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total else 0.0

    @property
    def rank_label(self) -> str:
        if self.mmr >= 2000: return "🏆 Grand Master"
        if self.mmr >= 1800: return "💎 Diamond"
        if self.mmr >= 1600: return "🥇 Platinum"
        if self.mmr >= 1400: return "🥈 Gold"
        if self.mmr >= 1200: return "🥉 Silver"
        return                      "⚪ Bronze"

    def render(self) -> str:
        return (f"  {self.rank_label:<20} [{self.team_name}]  "
                f"MMR:{self.mmr:6.0f}  "
                f"W:{self.wins} L:{self.losses} D:{self.draws}  "
                f"WR:{self.win_rate*100:.1f}%  Peak:{self.peak_mmr:.0f}")


class MMRSystem:
    def __init__(self):
        self.teams:  Dict[str, TeamRating] = {
            "ALPHA": TeamRating("ALPHA"),
            "OMEGA": TeamRating("OMEGA"),
        }
        self.match_history: List[Dict] = []

    def _expected_score(self, mmr_a: float, mmr_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((mmr_b - mmr_a) / 400.0))

    def record_match(self, winner: str,
                     alpha_stats: Dict, omega_stats: Dict):
        """
        Stats dict keys:
          kills, map_control_pct, boss_kills, strategy_score (0–1)
        """
        alpha_r = self.teams["ALPHA"]
        omega_r = self.teams["OMEGA"]
        E_a = self._expected_score(alpha_r.mmr, omega_r.mmr)
        E_o = 1.0 - E_a

        # Compute performance scores (0–1)
        def perf(stats: Dict) -> float:
            return (stats.get("kills",0)           * KILL_WEIGHT / 4.0 +
                    stats.get("map_control_pct",0) * MAP_CONTROL_WEIGHT +
                    stats.get("boss_kills",0)       * BOSS_WEIGHT / 3.0 +
                    stats.get("strategy_score",0.5) * STRATEGY_WEIGHT)

        a_perf = min(1.0, perf(alpha_stats))
        o_perf = min(1.0, perf(omega_stats))

        if winner == "ALPHA":
            S_a, S_o = 1.0, 0.0
            alpha_r.wins   += 1
            omega_r.losses += 1
        elif winner == "OMEGA":
            S_a, S_o = 0.0, 1.0
            alpha_r.losses += 1
            omega_r.wins   += 1
        else:
            S_a = S_o = 0.5
            alpha_r.draws += 1
            omega_r.draws += 1

        # Performance-weighted score
        S_a = S_a * 0.7 + a_perf * 0.3
        S_o = S_o * 0.7 + o_perf * 0.3

        delta_a = K_FACTOR * (S_a - E_a)
        delta_o = K_FACTOR * (S_o - E_o)

        alpha_r.mmr += delta_a
        omega_r.mmr += delta_o
        alpha_r.peak_mmr = max(alpha_r.peak_mmr, alpha_r.mmr)
        omega_r.peak_mmr = max(omega_r.peak_mmr, omega_r.mmr)

        record = {
            "winner":winner, "delta_alpha":round(delta_a,1),
            "delta_omega":round(delta_o,1),
            "alpha_mmr":round(alpha_r.mmr,1),
            "omega_mmr":round(omega_r.mmr,1),
        }
        self.match_history.append(record)
        return record

    def render_leaderboard(self):
        print(f"\n  ╔══ MMR LEADERBOARD ══╗")
        for r in sorted(self.teams.values(), key=lambda x: x.mmr, reverse=True):
            print(r.render())
        print(f"\n  Match History (last 5):")
        for rec in self.match_history[-5:]:
            print(f"    Winner:{rec['winner']}  "
                  f"ALPHA:{rec['delta_alpha']:+.0f}→{rec['alpha_mmr']}  "
                  f"OMEGA:{rec['delta_omega']:+.0f}→{rec['omega_mmr']}")


# ─────────────────────────────────────────────────────────────────────
#  UNIFIED PROGRESSION ENGINE
# ─────────────────────────────────────────────────────────────────────

class ProgressionEngine:
    def __init__(self):
        all_agents = ALPHA_AGENTS + OMEGA_AGENTS
        self.agents: Dict[str, AgentProgression] = {
            aid: AgentProgression(aid, ELEMENT_OF[aid], TEAM_OF[aid])
            for aid in all_agents
        }
        self.match_logger = MatchLogger()
        self.mmr          = MMRSystem()
        self.tick_num     = 0

    def tick(self, alive_agents: List[str]):
        self.tick_num += 1
        self.match_logger.advance_tick()
        for aid in alive_agents:
            if aid in self.agents:
                self.agents[aid].add_xp(XP_PER_TICK, "alive")
                self.agents[aid].tick_cooldown()

    def on_kill(self, killer_id: str, victim_id: str,
                pos: Tuple[float,float], damage: float = 0.0):
        if killer_id in self.agents:
            self.agents[killer_id].kills += 1
            self.agents[killer_id].add_xp(XP_PER_KILL, f"kill:{victim_id}")
        self.match_logger.log(killer_id, "kill", victim_id, pos, damage)

    def on_assist(self, agent_id: str, victim_id: str):
        if agent_id in self.agents:
            self.agents[agent_id].assists += 1
            self.agents[agent_id].add_xp(XP_PER_ASSIST, f"assist:{victim_id}")

    def on_capture(self, agent_id: str, landmark: str):
        if agent_id in self.agents:
            self.agents[agent_id].caps += 1
            self.agents[agent_id].add_xp(XP_PER_CAP, f"cap:{landmark}")
        self.match_logger.log(agent_id, "cap", landmark)

    def on_boss_kill(self, agent_id: str, boss_id: str, pos: Tuple[float,float]):
        if agent_id in self.agents:
            self.agents[agent_id].boss_kills += 1
            self.agents[agent_id].add_xp(XP_PER_BOSS, f"boss:{boss_id}")
        self.match_logger.log(agent_id, "kill", boss_id, pos, 900.0, "boss")

    def use_ultimate(self, agent_id: str, pos: Tuple[float,float]) -> Optional[Dict]:
        prog = self.agents.get(agent_id)
        if prog:
            ult = prog.use_ultimate(self.tick_num)
            if ult:
                self.match_logger.log(agent_id, "ultimate", ult["name"], pos,
                                      ult["dmg"])
                return ult
        return None

    def end_match(self, winner: str, alpha_stats: Dict, omega_stats: Dict):
        for aid, prog in self.agents.items():
            if TEAM_OF.get(aid) == winner:
                prog.wins += 1
            prog.matches += 1
        record = self.mmr.record_match(winner, alpha_stats, omega_stats)
        print(f"\n  🏆 Match ended. Winner: {winner}")
        print(f"    MMR delta — ALPHA:{record['delta_alpha']:+.0f}  "
              f"OMEGA:{record['delta_omega']:+.0f}")

    def flush_all_logs(self) -> List[str]:
        lines = []
        for prog in self.agents.values():
            lines.extend(prog.flush_log())
        return lines

    def render_progression(self):
        print(f"\n  ╔══ AGENT PROGRESSION ══╗")
        for team in ["ALPHA","OMEGA"]:
            print(f"\n  {'🔶' if team=='ALPHA' else '🔷'} Team {team}:")
            for aid in (ALPHA_AGENTS if team=="ALPHA" else OMEGA_AGENTS):
                print(self.agents[aid].render())
        self.mmr.render_leaderboard()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ PROGRESSION ENGINE DEMO ══╗\n")
    eng = ProgressionEngine()

    events = [
        (3,  "Ignis-Prime",  "kill",  "Sylvan-Wraith",  (80.0,80.0),  90.0),
        (5,  "Volt-Surge",   "cap",   "Clock_Tower",     (100.0,60.0), 0.0),
        (8,  "Ignis-Prime",  "kill",  "DustSerpent",     (95.0,95.0),  77.0),
        (10, "TerraKnight",  "cap",   "Parliament_Hall", (100.0,100.0),0.0),
        (12, "AquaVex",      "boss",  "GM_Ironclad",     (100.0,100.0),900.0),
        (15, "Volt-Surge",   "kill",  "ZephyrBlade",     (110.0,85.0), 55.0),
        (18, "Ignis-Prime",  "ult",   "",                (100.0,100.0),200.0),
        (20, "TerraKnight",  "kill",  "Voidwalker",      (105.0,102.0),120.0),
    ]

    for t in range(1, 25):
        alive = ALPHA_AGENTS + OMEGA_AGENTS
        eng.tick(alive)
        for line in eng.flush_all_logs():
            if "LEVEL" in line or "XP" in line and "kill" in line:
                print(line)

        for ev_t, actor, ev_type, target, pos, val in events:
            if t == ev_t:
                if ev_type == "kill":
                    eng.on_kill(actor, target, pos, val)
                elif ev_type == "cap":
                    eng.on_capture(actor, target)
                elif ev_type == "boss":
                    eng.on_boss_kill(actor, target, pos)
                elif ev_type == "ult":
                    eng.use_ultimate(actor, pos)

    eng.end_match("ALPHA",
        alpha_stats={"kills":4,"map_control_pct":0.67,"boss_kills":1,"strategy_score":0.8},
        omega_stats={"kills":0,"map_control_pct":0.33,"boss_kills":0,"strategy_score":0.4})

    eng.render_progression()
    print(eng.match_logger.stats_summary())
    eng.match_logger.replay(highlight_only=True)
    print()
