"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — PLAYER EXPERIENCE: LOADOUT · RESPAWN · ECONOMY · BOUNTIES  ║
║   Ability Selection · Death/Revival · Metaenergy · Boss Bounty System   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from shared_constants import *

# ─────────────────────────────────────────────────────────────────────
#  1. LOADOUT / BUILD SYSTEM
# ─────────────────────────────────────────────────────────────────────

# All available abilities per element (choose 2 of 3 before battle)
ALL_ABILITIES: Dict[str, List[Dict]] = {
    "Fire": [
        {"id":"fire_1","name":"Inferno Burst","dmg":45,"cd":3,"aoe":8.0,"effect":"burn","chance":0.60,"type":"AOE"},
        {"id":"fire_2","name":"Flame Lance",  "dmg":30,"cd":1,"aoe":0.0,"effect":"burn","chance":0.30,"type":"single"},
        {"id":"fire_3","name":"Meteor Crash", "dmg":80,"cd":8,"aoe":15.0,"effect":"stun","chance":0.40,"type":"ultimate"},
    ],
    "Water": [
        {"id":"wat_1","name":"Tidal Wave",  "dmg":40,"cd":4,"aoe":12.0,"effect":"slow","chance":0.70,"type":"AOE"},
        {"id":"wat_2","name":"Hydro Blast", "dmg":25,"cd":1,"aoe":0.0, "effect":"none","chance":0.0, "type":"single"},
        {"id":"wat_3","name":"Deep Freeze", "dmg":60,"cd":7,"aoe":6.0, "effect":"freeze","chance":0.50,"type":"AOE"},
    ],
    "Thunder": [
        {"id":"thu_1","name":"Chain Lightning","dmg":50,"cd":4,"aoe":10.0,"effect":"paralyze","chance":0.50,"type":"AOE"},
        {"id":"thu_2","name":"Volt Strike",    "dmg":35,"cd":1,"aoe":0.0,"effect":"paralyze","chance":0.20,"type":"single"},
        {"id":"thu_3","name":"Thunder God",    "dmg":90,"cd":10,"aoe":20.0,"effect":"stun","chance":0.80,"type":"ultimate"},
    ],
    "Earth": [
        {"id":"ear_1","name":"Rock Avalanche", "dmg":55,"cd":5,"aoe":10.0,"effect":"slow","chance":0.50,"type":"AOE"},
        {"id":"ear_2","name":"Ground Slam",    "dmg":40,"cd":2,"aoe":6.0, "effect":"knockback","chance":0.60,"type":"AOE"},
        {"id":"ear_3","name":"Tectonic Shift", "dmg":70,"cd":9,"aoe":18.0,"effect":"stun","chance":0.40,"type":"ultimate"},
    ],
    "Grass": [
        {"id":"gra_1","name":"Vine Trap",    "dmg":35,"cd":3,"aoe":8.0, "effect":"root","chance":0.70,"type":"AOE"},
        {"id":"gra_2","name":"Thorn Barrage","dmg":28,"cd":1,"aoe":0.0, "effect":"bleed","chance":0.40,"type":"single"},
        {"id":"gra_3","name":"Nature's Wrath","dmg":75,"cd":8,"aoe":16.0,"effect":"root","chance":0.60,"type":"ultimate"},
    ],
    "Sand": [
        {"id":"san_1","name":"Sandstorm",    "dmg":38,"cd":4,"aoe":14.0,"effect":"blind","chance":0.70,"type":"AOE"},
        {"id":"san_2","name":"Sand Spike",   "dmg":25,"cd":1,"aoe":0.0, "effect":"bleed","chance":0.30,"type":"single"},
        {"id":"san_3","name":"Quicksand Pit","dmg":65,"cd":8,"aoe":10.0,"effect":"root","chance":0.80,"type":"AOE"},
    ],
    "Flying": [
        {"id":"fly_1","name":"Gale Force",   "dmg":42,"cd":3,"aoe":12.0,"effect":"knockback","chance":0.60,"type":"AOE"},
        {"id":"fly_2","name":"Talon Strike", "dmg":30,"cd":1,"aoe":0.0, "effect":"bleed","chance":0.30,"type":"single"},
        {"id":"fly_3","name":"Hurricane",    "dmg":85,"cd":10,"aoe":22.0,"effect":"stun","chance":0.50,"type":"ultimate"},
    ],
    "Dark": [
        {"id":"dar_1","name":"Shadow Blast", "dmg":45,"cd":3,"aoe":8.0, "effect":"fear","chance":0.50,"type":"AOE"},
        {"id":"dar_2","name":"Void Strike",  "dmg":35,"cd":1,"aoe":0.0, "effect":"drain","chance":0.40,"type":"single"},
        {"id":"dar_3","name":"Eclipse",      "dmg":80,"cd":9,"aoe":18.0,"effect":"blind","chance":0.90,"type":"ultimate"},
    ],
}

# Passive traits per element
PASSIVE_TRAITS: Dict[str, Dict] = {
    "Fire": {
        "Pyromaniac":   {"desc":"Fire deals +10% dmg to burning targets",      "bonus":0.10, "condition":"target_burning"},
        "Inferno Step": {"desc":"Leaves fire trail — 4 burn DOT to anyone behind","bonus":4.0, "condition":"on_move"},
    },
    "Water": {
        "Tide Turner":  {"desc":"Heals 5 HP per status effect removed",         "bonus":5.0, "condition":"on_cleanse"},
        "Flood Control":{"desc":"Slow duration +1 tick on Water abilities",     "bonus":1,   "condition":"slow_applied"},
    },
    "Thunder": {
        "Static Charge":{"desc":"Every 3rd hit deals ×1.5 damage",             "bonus":1.5, "condition":"every_3_hits"},
        "Overdrive":    {"desc":"Speed +15% for 2t after using Thunder ability","bonus":0.15,"condition":"after_thunder_abil"},
    },
    "Earth": {
        "Immovable":    {"desc":"Knockback immune. Block chance +10%",          "bonus":0.10,"condition":"always"},
        "Resonance":    {"desc":"AOE attacks deal +20% if target is on ground", "bonus":0.20,"condition":"aoe_on_ground"},
    },
    "Grass": {
        "Overgrowth":   {"desc":"Root duration +1t. Vine grows back 10% HP on break","bonus":10.0,"condition":"root_breaks"},
        "Thornwall":    {"desc":"Attackers within 5u take 6 bleed DOT",        "bonus":6.0, "condition":"nearby_attacker"},
    },
    "Sand": {
        "Mirage":       {"desc":"20% chance to avoid detection (radar jammer)","bonus":0.20,"condition":"always"},
        "Quicksand":    {"desc":"All movement-impairing effects last +1t",     "bonus":1,   "condition":"on_slow_root"},
    },
    "Flying": {
        "Aerial Mastery":{"desc":"Dodge chance +10% while airborne",           "bonus":0.10,"condition":"always"},
        "Wind Rider":   {"desc":"Speed +10% per tick not hit",                 "bonus":0.10,"condition":"not_hit"},
    },
    "Dark": {
        "Shadow Step":  {"desc":"After dodge, next attack deals ×1.5",        "bonus":1.5, "condition":"after_dodge"},
        "Void Feed":    {"desc":"Drain DOT heals self for 50% of dmg",         "bonus":0.50,"condition":"drain_active"},
    },
}

@dataclass
class AgentLoadout:
    agent_id:  str
    element:   str
    ability_pool: List[Dict] = field(default_factory=list)
    chosen_abilities: List[Dict] = field(default_factory=list)
    chosen_passive: Optional[str] = None
    passive_data: Optional[Dict] = None
    locked: bool = False   # locked = battle started, can't change

    def __post_init__(self):
        self.ability_pool = ALL_ABILITIES.get(self.element, [])

    def select_abilities(self, ability_ids: List[str]) -> bool:
        """Player selects exactly 2 abilities from the pool."""
        if self.locked:
            return False
        if len(ability_ids) != 2:
            return False
        chosen = [a for a in self.ability_pool if a["id"] in ability_ids]
        if len(chosen) != 2:
            return False
        self.chosen_abilities = chosen
        return True

    def select_passive(self, passive_name: str) -> bool:
        if self.locked:
            return False
        passives = PASSIVE_TRAITS.get(self.element, {})
        if passive_name in passives:
            self.chosen_passive = passive_name
            self.passive_data   = passives[passive_name]
            return True
        return False

    def auto_select(self):
        """Auto-select based on role (for AI agents)."""
        pool = self.ability_pool
        if len(pool) >= 2:
            # Prefer highest damage + highest AOE
            sorted_by_dmg = sorted(pool, key=lambda a: a["dmg"] + a["aoe"]*0.5, reverse=True)
            self.chosen_abilities = sorted_by_dmg[:2]
        passives = list(PASSIVE_TRAITS.get(self.element, {}).keys())
        if passives:
            self.chosen_passive = passives[0]
            self.passive_data   = PASSIVE_TRAITS[self.element][passives[0]]

    def lock(self):
        if not self.chosen_abilities:
            self.auto_select()
        self.locked = True

    def render(self) -> str:
        ab_str = " | ".join(f"[{a['name']}]" for a in self.chosen_abilities) or "(none chosen)"
        pass_str = f"[{self.chosen_passive}]" if self.chosen_passive else "(none)"
        lock_str = "🔒LOCKED" if self.locked else "🔓open"
        return (f"  {self.agent_id:<18} {self.element:<10} {lock_str}  "
                f"Abilities:{ab_str}  Passive:{pass_str}")


class LoadoutManager:
    def __init__(self):
        all_agents = ALPHA_AGENTS + OMEGA_AGENTS
        self.loadouts: Dict[str, AgentLoadout] = {
            aid: AgentLoadout(aid, ELEMENT_OF[aid])
            for aid in all_agents
        }

    def player_select(self, agent_id: str, ability_ids: List[str],
                      passive_name: str) -> bool:
        lo = self.loadouts.get(agent_id)
        if not lo: return False
        ok_ab = lo.select_abilities(ability_ids)
        ok_pa = lo.select_passive(passive_name)
        return ok_ab and ok_pa

    def lock_all(self):
        for lo in self.loadouts.values():
            lo.lock()

    def render_all(self):
        print(f"\n  ╔══ PRE-BATTLE LOADOUTS ══╗")
        for lo in self.loadouts.values():
            print(lo.render())


# ─────────────────────────────────────────────────────────────────────
#  2. RESPAWN & DEATH SYSTEM
# ─────────────────────────────────────────────────────────────────────

BASE_RESPAWN_TICKS  = 8
ALLY_RESPAWN_BONUS  = 1   # -1 tick per alive ally
MIN_RESPAWN_TICKS   = 3
MAX_RESPAWN_TICKS   = 15

@dataclass
class DeathRecord:
    agent_id:     str
    team:         str
    death_tick:   int
    respawn_tick: int
    death_pos:    Tuple[float,float]
    killer_id:    str
    respawn_pos:  Tuple[float,float]
    respawned:    bool = False

    def ticks_until_respawn(self, current_tick: int) -> int:
        return max(0, self.respawn_tick - current_tick)

    def render(self) -> str:
        status = "✅ Respawned" if self.respawned else f"⏳ {self.respawn_tick}t"
        return (f"  💀 [{self.agent_id}] killed by [{self.killer_id}] "
                f"@ ({self.death_pos[0]:.0f},{self.death_pos[1]:.0f})  "
                f"Respawn: {status}")


class RespawnSystem:
    def __init__(self):
        self.deaths:      List[DeathRecord] = []
        self.alive_counts:Dict[str, int]    = {"ALPHA":4,"OMEGA":4}
        self.total_deaths:Dict[str, int]    = {"ALPHA":0,"OMEGA":0}
        self.tick_num:    int = 0
        self.log: List[str] = []

    def on_death(self, agent_id: str, team: str, death_tick: int,
                 death_pos: Tuple[float,float], killer_id: str) -> DeathRecord:
        self.alive_counts[team] = max(0, self.alive_counts.get(team,4) - 1)
        self.total_deaths[team] = self.total_deaths.get(team,0) + 1
        alive_allies = self.alive_counts.get(team, 0)
        respawn_delay = max(MIN_RESPAWN_TICKS,
                            BASE_RESPAWN_TICKS - alive_allies * ALLY_RESPAWN_BONUS)
        respawn_tick  = death_tick + respawn_delay
        spawn_pos     = SPAWN_OF.get(team, (100.0,100.0))
        rec = DeathRecord(agent_id, team, death_tick, respawn_tick,
                          death_pos, killer_id, spawn_pos)
        self.deaths.append(rec)
        self.log.append(
            f"  💀 [{agent_id}] DIED at T{death_tick} "
            f"— respawn in {respawn_delay}t @ T{respawn_tick}")
        return rec

    def tick(self, current_tick: int) -> List[str]:
        """Check for respawns. Returns list of respawned agent IDs."""
        self.tick_num = current_tick
        respawned = []
        for rec in self.deaths:
            if not rec.respawned and rec.respawn_tick <= current_tick:
                rec.respawned = True
                self.alive_counts[rec.team] = min(4,
                    self.alive_counts.get(rec.team, 0) + 1)
                self.log.append(
                    f"  ♻️  [{rec.agent_id}] RESPAWNED at T{current_tick} "
                    f"@ spawn ({rec.respawn_pos[0]:.0f},{rec.respawn_pos[1]:.0f})")
                respawned.append(rec.agent_id)
        return respawned

    def get_active_deaths(self) -> List[DeathRecord]:
        return [d for d in self.deaths if not d.respawned]

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self):
        print(f"\n  ╔══ RESPAWN TRACKER ══╗")
        print(f"  ALPHA alive: {self.alive_counts.get('ALPHA',0)}/4  "
              f"Total deaths: {self.total_deaths.get('ALPHA',0)}")
        print(f"  OMEGA alive: {self.alive_counts.get('OMEGA',0)}/4  "
              f"Total deaths: {self.total_deaths.get('OMEGA',0)}")
        active = self.get_active_deaths()
        if active:
            print(f"\n  Pending respawns ({len(active)}):")
            for rec in active:
                print(rec.render())


# ─────────────────────────────────────────────────────────────────────
#  3. RESOURCE ECONOMY — METAENERGY
# ─────────────────────────────────────────────────────────────────────

METAENERGY_PER_TICK_PER_POINT = 3   # per controlled landmark per tick
METAENERGY_PER_KILL            = 15
METAENERGY_CAP                 = 200

METAENERGY_COSTS = {
    "ultimate_ability":  60,
    "deploy_jammer":     40,
    "call_mob_reinforce":80,
    "emergency_respawn": 70,   # instant respawn (no wait)
    "barrier_recharge":  35,
    "aoe_damage_flare":  25,
}

@dataclass
class TeamEconomy:
    team:         str
    metaenergy:   float = 0.0
    total_earned: float = 0.0
    total_spent:  float = 0.0
    transactions: List[Dict] = field(default_factory=list)

    def earn(self, amount: float, reason: str, tick: int):
        self.metaenergy   = min(METAENERGY_CAP, self.metaenergy + amount)
        self.total_earned += amount
        self.transactions.append({"t":tick,"type":"earn","amount":amount,"reason":reason})

    def spend(self, amount: float, item: str, tick: int) -> bool:
        if self.metaenergy < amount:
            return False
        self.metaenergy  -= amount
        self.total_spent += amount
        self.transactions.append({"t":tick,"type":"spend","amount":amount,"item":item})
        return True

    def can_afford(self, item: str) -> bool:
        cost = METAENERGY_COSTS.get(item, 999)
        return self.metaenergy >= cost

    def energy_bar(self) -> str:
        return hp_bar(self.metaenergy, METAENERGY_CAP, 14)

    def render(self) -> str:
        return (f"  {'🔶' if self.team=='ALPHA' else '🔷'} {self.team}  "
                f"[{self.energy_bar()}] {self.metaenergy:.0f}/{METAENERGY_CAP}  "
                f"Earned:{self.total_earned:.0f}  Spent:{self.total_spent:.0f}")


class ResourceEconomy:
    def __init__(self):
        self.teams = {
            "ALPHA": TeamEconomy("ALPHA"),
            "OMEGA": TeamEconomy("OMEGA"),
        }
        self.tick_num = 0
        self.log: List[str] = []

    def tick(self, controlled_points: Dict[str, str]):
        self.tick_num += 1
        for pt_name, owner in controlled_points.items():
            if owner in self.teams:
                amt = METAENERGY_PER_TICK_PER_POINT
                self.teams[owner].earn(amt, f"holding {pt_name}", self.tick_num)

    def on_kill(self, killer_id: str, team: str):
        self.teams[team].earn(METAENERGY_PER_KILL,
                              f"kill by {killer_id}", self.tick_num)

    def purchase(self, team: str, item: str) -> Tuple[bool, str]:
        economy  = self.teams.get(team)
        if not economy: return False, "Team not found"
        cost = METAENERGY_COSTS.get(item, 999)
        if not economy.can_afford(item):
            msg = (f"  💸 [{team}] Cannot afford [{item}] "
                   f"(need {cost}, have {economy.metaenergy:.0f})")
            self.log.append(msg)
            return False, msg
        economy.spend(cost, item, self.tick_num)
        msg = (f"  💰 [{team}] Purchased [{item}] for {cost} Metaenergy "
               f"→ {economy.metaenergy:.0f} remaining")
        self.log.append(msg)
        return True, msg

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self):
        print(f"\n  ╔══ METAENERGY ECONOMY ══╗")
        for eco in self.teams.values():
            print(eco.render())
        print(f"\n  Shop (Metaenergy Costs):")
        for item, cost in METAENERGY_COSTS.items():
            print(f"    {item:<25} {cost:>4} ME")


# ─────────────────────────────────────────────────────────────────────
#  4. BOSS BOUNTY SYSTEM
# ─────────────────────────────────────────────────────────────────────

BOUNTY_DEFINITIONS = {
    "GM_Ironclad": {
        "bounty_me":   120,    # metaenergy reward to team
        "team_buff":   {"atk":1.15, "hp_regen":8.0, "duration":15},
        "icon":        "👑",
        "announce":    "⚔️  IRONCLAD FALLS! The Parliament gates weaken!",
    },
    "GM_StormLord": {
        "bounty_me":   100,
        "team_buff":   {"spd":1.20, "thunder_atk":1.30, "duration":15},
        "icon":        "👑",
        "announce":    "⚡ STORMLORD DEFEATED! Thunder answers the victors!",
    },
    "GM_VoidKing": {
        "bounty_me":   110,
        "team_buff":   {"crit":0.15, "drain_immunity":True, "duration":15},
        "icon":        "👑",
        "announce":    "🌑 VOID KING SLAIN! Darkness retreats before them!",
    },
    "Elite_Magma": {
        "bounty_me":   55,
        "team_buff":   {"fire_atk":1.20, "duration":8},
        "icon":        "👹",
        "announce":    "🔥 Elite Magma extinguished! Fire claims victory!",
    },
    "Elite_Void": {
        "bounty_me":   60,
        "team_buff":   {"atk":1.10, "duration":8},
        "icon":        "👹",
        "announce":    "🌑 Elite Void collapsed! The shadow breaks!",
    },
}

@dataclass
class BountyRecord:
    boss_id:     str
    claimed_by:  str     # team
    killer_id:   str
    tick:        int
    me_rewarded: int
    buff_applied: Dict

    def render(self) -> str:
        defn = BOUNTY_DEFINITIONS.get(self.boss_id, {})
        icon = defn.get("icon", "👾")
        return (f"  {icon} [{self.boss_id}] claimed by "
                f"{self.claimed_by} ({self.killer_id}) "
                f"at T{self.tick}  +{self.me_rewarded}ME  "
                f"Buff:{list(self.buff_applied.keys())}")

@dataclass
class ActiveBuff:
    team:       str
    source:     str
    buff_data:  Dict
    applied_tick: int
    duration:   int

    def is_active(self, tick: int) -> bool:
        return (tick - self.applied_tick) < self.duration

    def render(self, tick: int) -> str:
        ttl = self.duration - (tick - self.applied_tick)
        mods = {k:v for k,v in self.buff_data.items() if k != "duration"}
        return (f"  ✨ [{self.team}] {self.source} buff: "
                f"{mods}  TTL:{ttl}t")


class BossBountySystem:
    def __init__(self, resource_economy: ResourceEconomy):
        self.economy   = resource_economy
        self.records:  List[BountyRecord] = []
        self.active_buffs: List[ActiveBuff] = []
        self.boss_status: Dict[str, str] = {
            b: "alive" for b in BOUNTY_DEFINITIONS
        }
        self.log: List[str] = []

    def on_boss_kill(self, boss_id: str, killer_id: str,
                     team: str, tick: int) -> Optional[BountyRecord]:
        defn = BOUNTY_DEFINITIONS.get(boss_id)
        if not defn:
            return None
        if self.boss_status.get(boss_id) != "alive":
            return None

        self.boss_status[boss_id] = "defeated"
        me_reward = defn["bounty_me"]
        buff      = {k:v for k,v in defn["team_buff"].items() if k != "duration"}
        dur       = defn["team_buff"].get("duration", 10)

        # Award metaenergy
        self.economy.teams[team].earn(me_reward, f"bounty:{boss_id}", tick)

        # Apply team buff
        active_buff = ActiveBuff(team, boss_id, buff, tick, dur)
        self.active_buffs.append(active_buff)

        rec = BountyRecord(boss_id, team, killer_id, tick, me_reward, buff)
        self.records.append(rec)

        ann = defn.get("announce", f"Boss {boss_id} defeated!")
        self.log.append(f"  🏆 BOUNTY CLAIMED: {ann}")
        self.log.append(f"    Team {team}: +{me_reward} Metaenergy  "
                        f"Buff:{list(buff.keys())} for {dur}t")
        return rec

    def tick(self, tick: int):
        self.active_buffs = [b for b in self.active_buffs if b.is_active(tick)]

    def get_team_buffs(self, team: str, tick: int) -> Dict:
        """Returns merged buff dict for a team."""
        merged: Dict = {}
        for buff in self.active_buffs:
            if buff.team == team and buff.is_active(tick):
                for k, v in buff.buff_data.items():
                    if isinstance(v, float):
                        merged[k] = merged.get(k, 1.0) * v
                    elif isinstance(v, bool):
                        merged[k] = True
                    else:
                        merged[k] = merged.get(k, 0) + v
        return merged

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self, tick: int):
        print(f"\n  ╔══ BOSS BOUNTY SYSTEM ══╗")
        print(f"  Boss Status:")
        for boss_id, status in self.boss_status.items():
            defn = BOUNTY_DEFINITIONS[boss_id]
            icon = "✅" if status == "alive" else "💀"
            print(f"    {icon} {defn['icon']} {boss_id:<20} {status:<10} "
                  f"Bounty:{defn['bounty_me']} ME")
        if self.records:
            print(f"\n  Claimed Bounties:")
            for r in self.records:
                print(r.render())
        if self.active_buffs:
            print(f"\n  Active Team Buffs:")
            for buff in self.active_buffs:
                if buff.is_active(tick):
                    print(buff.render(tick))


# ─────────────────────────────────────────────────────────────────────
#  PLAYER EXPERIENCE ENGINE
# ─────────────────────────────────────────────────────────────────────

class PlayerExperienceEngine:
    def __init__(self):
        self.loadouts  = LoadoutManager()
        self.respawn   = RespawnSystem()
        self.economy   = ResourceEconomy()
        self.bounty    = BossBountySystem(self.economy)
        self.tick_num  = 0

    def setup_battle(self, player_selections: Dict[str, Dict]):
        """
        player_selections: {agent_id: {"abilities":[id1,id2], "passive":"name"}}
        """
        for agent_id, sel in player_selections.items():
            self.loadouts.player_select(
                agent_id,
                sel.get("abilities", []),
                sel.get("passive", "")
            )
        # Auto-fill any not selected
        self.loadouts.lock_all()
        print("  🔒 Loadouts locked. Battle starting!")
        self.loadouts.render_all()

    def tick(self, controlled_points: Dict[str,str],
             alive_agents: List[str]):
        self.tick_num += 1
        self.economy.tick(controlled_points)
        respawned = self.respawn.tick(self.tick_num)
        self.bounty.tick(self.tick_num)
        for line in self.respawn.flush_log(): print(line)
        for line in self.economy.flush_log():  print(line)
        for line in self.bounty.flush_log():   print(line)
        return respawned

    def on_kill(self, killer_id: str, victim_id: str, team: str,
                death_pos: Tuple[float,float]):
        self.economy.on_kill(killer_id, team)
        self.respawn.on_death(victim_id, TEAM_OF.get(victim_id,"?"),
                              self.tick_num, death_pos, killer_id)

    def on_boss_kill(self, boss_id: str, killer_id: str, team: str):
        self.bounty.on_boss_kill(boss_id, killer_id, team, self.tick_num)

    def purchase(self, team: str, item: str) -> Tuple[bool, str]:
        return self.economy.purchase(team, item)

    def render_all(self):
        self.loadouts.render_all()
        self.respawn.render()
        self.economy.render()
        self.bounty.render(self.tick_num)


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ PLAYER EXPERIENCE ENGINE DEMO ══╗\n")
    pxp = PlayerExperienceEngine()

    # Pre-battle loadout selection
    pxp.setup_battle({
        "Ignis-Prime":  {"abilities":["fire_1","fire_3"],"passive":"Pyromaniac"},
        "AquaVex":      {"abilities":["wat_1","wat_3"],  "passive":"Tide Turner"},
        "Volt-Surge":   {"abilities":["thu_1","thu_3"],  "passive":"Static Charge"},
        "TerraKnight":  {"abilities":["ear_1","ear_2"],  "passive":"Immovable"},
    })

    controlled = {
        "Parliament_Hall":"ALPHA","Clock_Tower":"ALPHA",
        "North_Stadium":"Neutral","South_Stadium":"OMEGA",
        "East_Tower":"OMEGA","West_Tower":"ALPHA"
    }

    print("\n  Simulating 25 ticks...\n")
    for t in range(1, 26):
        respawned = pxp.tick(controlled, ALPHA_AGENTS + OMEGA_AGENTS)
        if respawned:
            print(f"  ♻️  Respawned: {respawned}")

        if t == 4:
            print(f"\n  ⚡ [T{t}] Ignis-Prime kills ZephyrBlade!")
            pxp.on_kill("Ignis-Prime","ZephyrBlade","ALPHA",(80.0,80.0))

        if t == 8:
            print(f"\n  ⚡ [T{t}] ALPHA purchases ultimate_ability!")
            ok, msg = pxp.purchase("ALPHA","ultimate_ability")
            print(msg)
            print(f"\n  ⚡ [T{t}] TerraKnight kills GM_Ironclad!")
            pxp.on_boss_kill("GM_Ironclad","TerraKnight","ALPHA")

        if t == 15:
            print(f"\n  ⚡ [T{t}] OMEGA purchases deploy_jammer!")
            ok, msg = pxp.purchase("OMEGA","deploy_jammer")
            print(msg)
            print(f"\n  ⚡ [T{t}] Voidwalker kills AquaVex!")
            pxp.on_kill("Voidwalker","AquaVex","OMEGA",(100.0,95.0))
            pxp.on_boss_kill("Elite_Void","Voidwalker","OMEGA")

    pxp.render_all()
    print()
