"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — CRITICAL HIT & DODGE ENGINE                                 ║
║   Crit Chance · Crit Multiplier · Dodge · Block · Parry                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from shared_constants import *

# ── Per-element base stats ─────────────────────────────────────────────
ELEMENT_CRIT_STATS: Dict[str, Dict] = {
    "Fire":    {"crit_chance":0.18, "crit_mult":1.80, "dodge":0.05, "block":0.00, "parry":0.08},
    "Water":   {"crit_chance":0.10, "crit_mult":1.50, "dodge":0.10, "block":0.12, "parry":0.05},
    "Thunder": {"crit_chance":0.25, "crit_mult":2.20, "dodge":0.12, "block":0.00, "parry":0.03},
    "Earth":   {"crit_chance":0.08, "crit_mult":1.60, "dodge":0.02, "block":0.30, "parry":0.15},
    "Grass":   {"crit_chance":0.12, "crit_mult":1.70, "dodge":0.15, "block":0.05, "parry":0.10},
    "Sand":    {"crit_chance":0.20, "crit_mult":1.90, "dodge":0.20, "block":0.03, "parry":0.05},
    "Flying":  {"crit_chance":0.22, "crit_mult":2.00, "dodge":0.30, "block":0.00, "parry":0.07},
    "Dark":    {"crit_chance":0.28, "crit_mult":2.50, "dodge":0.18, "block":0.00, "parry":0.12},
}

@dataclass
class CombatResult:
    raw_damage:      float
    final_damage:    float
    is_crit:         bool   = False
    is_dodge:        bool   = False
    is_block:        bool   = False
    is_parry:        bool   = False
    crit_multiplier: float  = 1.0
    note:            str    = ""

    def render(self) -> str:
        if self.is_dodge: return f"  💨 DODGED! (0 damage)"
        if self.is_block:
            return (f"  🛡️  BLOCKED! {self.raw_damage:.1f}→{self.final_damage:.1f} dmg "
                    f"(mitigated {self.raw_damage-self.final_damage:.1f})")
        if self.is_parry:
            return f"  ⚔️  PARRIED! Counter-damage: {self.final_damage:.1f}"
        if self.is_crit:
            return (f"  💥 CRITICAL HIT! ×{self.crit_multiplier:.1f} "
                    f"→ {self.final_damage:.1f} dmg")
        return f"  ⚔️  Normal hit: {self.final_damage:.1f} dmg"


class CritDodgeEngine:
    """
    Resolves attack outcomes including crits, dodges, blocks, and parries.
    Tracks streaks, modifiers, and per-agent combat history.
    """
    def __init__(self):
        # Per-agent modifiers (buffs/debuffs to crit/dodge)
        self.crit_mods:  Dict[str, float] = {}   # agent_id → bonus crit chance
        self.dodge_mods: Dict[str, float] = {}
        # Streak tracking
        self.crit_streaks:  Dict[str, int] = {}   # consecutive crits
        self.dodge_streaks: Dict[str, int] = {}
        # History
        self.history: List[Dict] = []
        self.stats:   Dict[str, Dict] = {}   # per agent combat stats

    def _get_stats(self, agent_id: str) -> Dict:
        if agent_id not in self.stats:
            self.stats[agent_id] = {
                "hits":0,"crits":0,"dodges":0,"blocks":0,"parries":0,
                "total_dmg_dealt":0.0,"total_dmg_taken":0.0
            }
        return self.stats[agent_id]

    def add_crit_modifier(self, agent_id: str, bonus: float, source: str=""):
        self.crit_mods[agent_id] = self.crit_mods.get(agent_id, 0.0) + bonus

    def add_dodge_modifier(self, agent_id: str, bonus: float, source: str=""):
        self.dodge_mods[agent_id] = self.dodge_mods.get(agent_id, 0.0) + bonus

    def resolve(self, attacker_id: str, attacker_element: str,
                defender_id: str,  defender_element: str,
                raw_damage: float,
                attacker_buffs: List[str] = None,
                defender_debuffs: List[str] = None) -> CombatResult:
        """
        Full attack resolution pipeline:
        Dodge check → Block check → Parry check → Crit check → Damage calc
        """
        atk_stats  = ELEMENT_CRIT_STATS.get(attacker_element, {})
        def_stats  = ELEMENT_CRIT_STATS.get(defender_element, {})

        # ── Dodge roll ─────────────────────────────────────────────
        dodge_chance = (def_stats.get("dodge", 0.05) +
                        self.dodge_mods.get(defender_id, 0.0))
        # Blind reduces dodge
        if defender_debuffs and "blind" in defender_debuffs:
            dodge_chance *= 0.2
        # Flying gets 50% more dodge in open field
        if defender_element == "Flying" and random.random() < 0.5:
            dodge_chance *= 1.5
        dodge_chance = min(dodge_chance, 0.60)  # hard cap 60%

        if random.random() < dodge_chance:
            self.dodge_streaks[defender_id] = self.dodge_streaks.get(defender_id,0)+1
            self._get_stats(defender_id)["dodges"] += 1
            self.history.append({"tick":"?","type":"dodge","attacker":attacker_id,
                                  "defender":defender_id,"dmg":0})
            return CombatResult(raw_damage, 0.0, is_dodge=True,
                                note=f"Dodge×{self.dodge_streaks[defender_id]}")

        self.dodge_streaks[defender_id] = 0

        # ── Block roll ─────────────────────────────────────────────
        block_chance = def_stats.get("block", 0.0)
        if random.random() < block_chance:
            # Block reduces damage by 40–70%
            mitigation  = random.uniform(0.40, 0.70)
            # Earth block is stronger vs physical (non-elemental)
            if defender_element == "Earth":
                mitigation = min(0.85, mitigation + 0.15)
            final_dmg   = raw_damage * (1 - mitigation)
            self._get_stats(defender_id)["blocks"] += 1
            return CombatResult(raw_damage, final_dmg, is_block=True,
                                note=f"Block {mitigation*100:.0f}% mitigated")

        # ── Parry roll ─────────────────────────────────────────────
        parry_chance = def_stats.get("parry", 0.0)
        if random.random() < parry_chance:
            # Parry returns 30–50% of incoming damage as counter-damage
            counter = raw_damage * random.uniform(0.30, 0.50)
            self._get_stats(defender_id)["parries"] += 1
            return CombatResult(raw_damage, counter, is_parry=True,
                                note=f"Parry → counter {counter:.1f}")

        # ── Crit roll ──────────────────────────────────────────────
        crit_chance = (atk_stats.get("crit_chance", 0.10) +
                       self.crit_mods.get(attacker_id, 0.0))
        crit_mult   = atk_stats.get("crit_mult", 1.5)

        # Streak bonus: every 3 non-crits → +10% crit next hit
        streak = self.crit_streaks.get(attacker_id, 0)
        if streak >= 3:
            crit_chance = min(0.80, crit_chance + 0.10 * (streak // 3))

        # Attacker buffs
        if attacker_buffs and "sharp" in attacker_buffs:
            crit_chance += 0.15
        if defender_debuffs and "slow" in defender_debuffs:
            crit_chance += 0.08   # easier to crit slowed targets

        is_crit      = random.random() < min(crit_chance, 0.75)
        final_mult   = crit_mult if is_crit else 1.0

        # ── Backstab bonus (Dark element) ──────────────────────────
        if attacker_element == "Dark" and is_crit:
            final_mult += 0.50
            note = f"BACKSTAB ×{final_mult:.1f}"
        else:
            note = f"×{final_mult:.1f}"

        final_dmg = raw_damage * final_mult

        if is_crit:
            self.crit_streaks[attacker_id]  = 0
            self._get_stats(attacker_id)["crits"] += 1
        else:
            self.crit_streaks[attacker_id] = self.crit_streaks.get(attacker_id,0)+1

        self._get_stats(attacker_id)["hits"]            += 1
        self._get_stats(attacker_id)["total_dmg_dealt"] += final_dmg
        self._get_stats(defender_id)["total_dmg_taken"] += final_dmg

        self.history.append({"type":"crit" if is_crit else "hit",
                              "attacker":attacker_id,"defender":defender_id,
                              "raw":raw_damage,"final":final_dmg})
        return CombatResult(raw_damage, final_dmg, is_crit=is_crit,
                            crit_multiplier=final_mult, note=note)

    def render_stats(self):
        print(f"\n  ╔══ COMBAT STATS ══╗")
        print(f"  {'Agent':<18} {'Hits':>5} {'Crits':>6} {'CritRate':>9} "
              f"{'Dodges':>7} {'Blocks':>7} {'Parries':>8} {'Dmg Dealt':>11}")
        print(f"  {'─'*80}")
        for agent_id, s in self.stats.items():
            hits     = s["hits"]
            crit_rate = f"{s['crits']/hits*100:.1f}%" if hits else "0%"
            print(f"  {agent_id:<18} {hits:>5} {s['crits']:>6} {crit_rate:>9} "
                  f"{s['dodges']:>7} {s['blocks']:>7} {s['parries']:>8} "
                  f"{s['total_dmg_dealt']:>11.1f}")
        print()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ CRITICAL HIT & DODGE ENGINE DEMO ══╗\n")
    engine = CritDodgeEngine()
    engine.add_crit_modifier("Volt-Surge", 0.15, "Thunder passive")
    engine.add_dodge_modifier("ZephyrBlade", 0.10, "Flying bonus")

    matchups = [
        ("Volt-Surge","Thunder","TerraKnight","Earth", 60.0),
        ("Voidwalker", "Dark",  "AquaVex",   "Water", 45.0),
        ("ZephyrBlade","Flying","Ignis-Prime","Fire",  38.0),
        ("Ignis-Prime","Fire",  "Sylvan-Wraith","Grass",55.0),
    ]
    for i in range(3):
        print(f"  ── Round {i+1} ──")
        for atk_id, atk_el, def_id, def_el, dmg in matchups:
            result = engine.resolve(atk_id, atk_el, def_id, def_el, dmg)
            print(f"  {atk_id} → {def_id}: {result.render()}")

    engine.render_stats()
