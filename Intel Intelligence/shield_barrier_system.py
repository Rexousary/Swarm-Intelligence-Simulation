"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — SHIELD / BARRIER SYSTEM                                     ║
║   Elemental Barriers · Absorption · Weakness · Charge Mechanics         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from shared_constants import *

# ── Barrier type definitions ───────────────────────────────────────────
BARRIER_DEFS: Dict[str, Dict] = {
    "Fire":    {"absorb":180, "regen":4.0,  "icon":"🔥", "color":"red",
                "weak_to":["Water","Earth"], "strong_vs":["Grass","Flying"],
                "passive":"Enemies in 8u take 4 burn DOT/tick"},
    "Water":   {"absorb":200, "regen":6.0,  "icon":"💧", "color":"blue",
                "weak_to":["Thunder","Grass"],"strong_vs":["Fire","Sand"],
                "passive":"Heals 5 HP/tick while barrier is active"},
    "Thunder": {"absorb":150, "regen":3.0,  "icon":"⚡", "color":"yellow",
                "weak_to":["Earth"],        "strong_vs":["Water","Flying"],
                "passive":"Next attack has +20% crit chance"},
    "Earth":   {"absorb":250, "regen":2.0,  "icon":"🌍", "color":"brown",
                "weak_to":["Water","Grass"],"strong_vs":["Thunder","Fire"],
                "passive":"Reduces knockback by 80%"},
    "Grass":   {"absorb":190, "regen":5.0,  "icon":"🌿", "color":"green",
                "weak_to":["Fire","Flying"],"strong_vs":["Water","Earth"],
                "passive":"Roots attacker on barrier break (2t)"},
    "Sand":    {"absorb":160, "regen":4.0,  "icon":"🏜️", "color":"tan",
                "weak_to":["Water","Grass"],"strong_vs":["Fire","Thunder"],
                "passive":"20% chance to blind attacker on hit"},
    "Flying":  {"absorb":130, "regen":7.0,  "icon":"🌪️", "color":"cyan",
                "weak_to":["Thunder","Earth"],"strong_vs":["Grass","Fighting"],
                "passive":"10% dodge chance while barrier active"},
    "Dark":    {"absorb":170, "regen":3.5,  "icon":"🌑", "color":"purple",
                "weak_to":["Grass","Thunder"],"strong_vs":["Dark","Ghost"],
                "passive":"Absorbs 15% of damage dealt back as HP"},
}

# Weakness multiplier when attacking a barrier with its weak element
BARRIER_WEAK_MULT  = 2.0
BARRIER_STRONG_MULT = 0.5

@dataclass
class BarrierLayer:
    """Single barrier layer — stacking multiple creates a layered shield."""
    element:    str
    max_absorb: float
    current:    float
    regen_rate: float       # absorb restored per tick (when not hit)
    icon:       str
    layer_id:   int
    ticks_since_hit: int = 0
    broken:     bool = False

    def absorb(self, damage: float, attacker_element: str) -> Tuple[float, float, str]:
        """
        Returns (damage_to_barrier, damage_passed_through, note).
        """
        if self.broken: return 0.0, damage, "broken"
        defn      = BARRIER_DEFS[self.element]
        note      = ""
        mult      = 1.0
        if attacker_element in defn["weak_to"]:
            mult = BARRIER_WEAK_MULT
            note = f"💥BARRIER WEAK ({attacker_element}→{self.element})"
        elif attacker_element in defn["strong_vs"]:
            mult = BARRIER_STRONG_MULT
            note = f"🛡️ BARRIER RESISTS"

        dmg_to_barrier = damage * mult
        self.ticks_since_hit = 0

        if dmg_to_barrier >= self.current:
            overflow = dmg_to_barrier - self.current
            self.current = 0.0
            self.broken  = True
            return self.current, overflow / mult, f"💔 BARRIER BROKEN! {note}"
        else:
            self.current -= dmg_to_barrier
            return dmg_to_barrier, 0.0, note

    def tick_regen(self):
        if not self.broken:
            self.ticks_since_hit += 1
            if self.ticks_since_hit >= 3:   # regen starts 3 ticks after last hit
                self.current = min(self.max_absorb, self.current + self.regen_rate)

    def pct(self) -> float:
        return (self.current / self.max_absorb) * 100 if self.max_absorb else 0.0

    def render(self) -> str:
        bar = hp_bar(self.current, self.max_absorb, 12)
        state = "💔BROKEN" if self.broken else f"{self.current:.0f}/{self.max_absorb:.0f}"
        return (f"    L{self.layer_id} {self.icon}{self.element:<8} "
                f"[{bar}] {state:>14} "
                f"Regen:{self.regen_rate:.1f}/t")


class BarrierSystem:
    """
    Manages layered elemental barriers for one agent.
    Up to 3 layers can be stacked — damage must break outer before reaching inner.
    Includes passive ability triggers per element.
    """
    def __init__(self, owner_id: str, element: str):
        self.owner_id  = owner_id
        self.element   = element
        self.layers:   List[BarrierLayer] = []
        self.log:      List[str] = []
        self._layer_seq = 0
        # Apply starter barrier for agent's own element
        self.grant_barrier(element, source="init")

    def grant_barrier(self, element: str, source: str = "ability"):
        if len(self.layers) >= 3:
            self.log.append(f"  ⚠️  [{self.owner_id}] Max barrier layers (3) reached")
            return
        defn = BARRIER_DEFS.get(element)
        if not defn: return
        self._layer_seq += 1
        layer = BarrierLayer(
            element    = element,
            max_absorb = defn["absorb"],
            current    = defn["absorb"],
            regen_rate = defn["regen"],
            icon       = defn["icon"],
            layer_id   = self._layer_seq,
        )
        self.layers.append(layer)
        self.log.append(f"  🛡️  [{self.owner_id}] Barrier L{self._layer_seq} "
                        f"granted ({element} / {defn['absorb']} absorb)")

    def take_damage(self, raw_damage: float,
                    attacker_element: str) -> Tuple[float, float, List[str]]:
        """
        Process damage through barrier layers outer→inner.
        Returns (damage_absorbed_total, damage_to_hp, event_notes).
        """
        notes:       List[str] = []
        remaining    = raw_damage
        total_absorbed = 0.0
        active_layers  = [l for l in self.layers if not l.broken]

        for layer in active_layers:
            if remaining <= 0:
                break
            d_barrier, overflow, note = layer.absorb(remaining, attacker_element)
            total_absorbed += (remaining - overflow)
            remaining       = overflow
            if note:
                notes.append(f"  🛡️  [{self.owner_id}] L{layer.layer_id}: {note} "
                              f"→ -{d_barrier:.1f} from barrier")
            # Passive triggers
            self._check_passive(layer, attacker_element, notes)

        self.log.extend(notes)
        return total_absorbed, remaining, notes

    def _check_passive(self, layer: BarrierLayer, attacker_element: str,
                       notes: List[str]):
        defn = BARRIER_DEFS[layer.element]
        passive = defn.get("passive","")
        if layer.element == "Sand" and random.random() < 0.20:
            notes.append(f"  💨 Sand passive: attacker BLINDED!")
        elif layer.element == "Flying" and random.random() < 0.10:
            notes.append(f"  🌪️  Flying passive: DODGE triggered!")
        elif layer.element == "Grass" and layer.broken:
            notes.append(f"  🌿 Grass passive: barrier break ROOTS attacker (2t)!")
        elif layer.element == "Dark":
            lifedrip = raw_dmg * 0.15 if (raw_dmg := layer.max_absorb * 0.1) else 0
            notes.append(f"  🌑 Dark passive: +{lifedrip:.1f} HP drained from attacker")

    def tick(self):
        """Regen tick for all layers; remove fully broken layers."""
        for layer in self.layers:
            layer.tick_regen()
        # Remove broken layers that have been broken > 5 ticks (they fall off)
        self.layers = [l for l in self.layers
                       if not l.broken or l.ticks_since_hit < 5]

    def total_absorb_remaining(self) -> float:
        return sum(l.current for l in self.layers if not l.broken)

    def has_active_barrier(self) -> bool:
        return any(not l.broken for l in self.layers)

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def render(self) -> str:
        lines = [f"  ╔ BARRIER [{self.owner_id}] — {self.element} — "
                 f"Total:{self.total_absorb_remaining():.0f} absorb remaining"]
        if not self.layers:
            lines.append("    (no barriers)")
        for layer in self.layers:
            lines.append(layer.render())
        lines.append(f"  ╚{'─'*50}")
        return "\n".join(lines)


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ SHIELD / BARRIER SYSTEM DEMO ══╗\n")
    terra = BarrierSystem("TerraKnight", "Earth")
    terra.grant_barrier("Dark", source="Voidwalker buff")
    print(terra.render())

    attacks = [
        ("Ignis-Prime",    "Fire",    55.0),
        ("AquaVex",        "Water",   80.0),
        ("Sylvan-Wraith",  "Grass",   70.0),
        ("Volt-Surge",     "Thunder", 120.0),
    ]
    for attacker, elem, dmg in attacks:
        print(f"\n  ⚔️  {attacker} ({elem}) attacks for {dmg:.0f}")
        absorbed, to_hp, notes = terra.take_damage(dmg, elem)
        for n in notes: print(n)
        print(f"    Absorbed:{absorbed:.1f}  To HP:{to_hp:.1f}")
        for line in terra.flush_log(): print(line)
        terra.tick()
        print(terra.render())
