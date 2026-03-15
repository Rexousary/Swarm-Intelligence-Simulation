"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — STATUS EFFECT STACKING SYSTEM                               ║
║   Interactions · Combos · Counter-Effects · Stacking Rules              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from shared_constants import *

# ── Base effect definitions ────────────────────────────────────────────
EFFECT_DEFS: Dict[str, Dict] = {
    "burn":       {"duration":4, "dot":8.0,  "move_pen":0.0,  "atk_pen":0.0,  "icon":"🔥"},
    "bleed":      {"duration":5, "dot":6.0,  "move_pen":0.0,  "atk_pen":0.0,  "icon":"🩸"},
    "slow":       {"duration":4, "dot":0.0,  "move_pen":0.40, "atk_pen":0.0,  "icon":"🐢"},
    "freeze":     {"duration":3, "dot":0.0,  "move_pen":1.0,  "atk_pen":1.0,  "icon":"🧊"},
    "paralyze":   {"duration":2, "dot":0.0,  "move_pen":1.0,  "atk_pen":0.50, "icon":"⚡"},
    "root":       {"duration":3, "dot":0.0,  "move_pen":1.0,  "atk_pen":0.0,  "icon":"🌿"},
    "blind":      {"duration":2, "dot":0.0,  "move_pen":0.0,  "atk_pen":0.60, "icon":"🕶️"},
    "fear":       {"duration":2, "dot":0.0,  "move_pen":0.5,  "atk_pen":1.0,  "icon":"😱"},
    "drain":      {"duration":3, "dot":5.0,  "move_pen":0.0,  "atk_pen":0.20, "icon":"🌑"},
    "stun":       {"duration":2, "dot":0.0,  "move_pen":1.0,  "atk_pen":1.0,  "icon":"⭐"},
    "knockback":  {"duration":1, "dot":0.0,  "move_pen":0.0,  "atk_pen":0.0,  "icon":"💨"},
    # ── Combo effects (only created via interactions) ──────────────
    "hemorrhage": {"duration":6, "dot":18.0, "move_pen":0.2,  "atk_pen":0.10, "icon":"💢"},
    "shatter":    {"duration":1, "dot":0.0,  "move_pen":0.0,  "atk_pen":0.0,  "icon":"💥", "burst_dmg":120.0},
    "voltburn":   {"duration":4, "dot":12.0, "move_pen":0.3,  "atk_pen":0.30, "icon":"🌩️"},
    "sandblind":  {"duration":5, "dot":3.0,  "move_pen":0.20, "atk_pen":0.70, "icon":"🏜️"},
    "frostroot":  {"duration":5, "dot":4.0,  "move_pen":1.0,  "atk_pen":0.25, "icon":"❄️"},
    "voidburn":   {"duration":5, "dot":14.0, "move_pen":0.15, "atk_pen":0.15, "icon":"🌀"},
    "petrify":    {"duration":4, "dot":0.0,  "move_pen":1.0,  "atk_pen":1.0,  "icon":"🗿"},
}

# ── Combo interaction rules ────────────────────────────────────────────
# (effect_a, effect_b) → (combo_name, burst_dmg_bonus, log_msg)
COMBOS: Dict[Tuple[str,str], Tuple[str, float, str]] = {
    ("burn",    "bleed"):   ("hemorrhage", 0.0,  "🔥🩸 HEMORRHAGE — fire meets open wounds!"),
    ("freeze",  "earth"):   ("shatter",   120.0, "🧊💥 SHATTER — frozen target crumbles!"),
    ("burn",    "thunder"): ("voltburn",   20.0, "🔥⚡ VOLTBURN — electrified flames!"),
    ("blind",   "sand"):    ("sandblind",   5.0, "🕶️🏜️ SANDBLIND — eyes filled with sand!"),
    ("freeze",  "root"):    ("frostroot",  10.0, "🧊🌿 FROSTROOT — ice-locked and entangled!"),
    ("drain",   "burn"):    ("voidburn",   15.0, "🌑🔥 VOIDBURN — life force seared away!"),
    ("slow",    "root"):    ("petrify",     0.0, "🐢🌿 PETRIFY — completely immobilized!"),
}

# ── Counter-effect cancellations ───────────────────────────────────────
# effect_applied cancels existing_effect
COUNTERS: Dict[str, str] = {
    "water_applied": "burn",     # Water application extinguishes burn
    "burn":          "freeze",   # Burn melts freeze
    "freeze":        "burn",     # Freeze snuffs burn
    "thunder_hit":   "root",     # Thunder strike breaks root
}

@dataclass
class ActiveEffect:
    name:         str
    duration:     int       # ticks remaining
    dot:          float
    move_penalty: float     # 0.0–1.0 fraction of speed removed
    atk_penalty:  float     # 0.0–1.0 fraction of atk removed
    icon:         str
    stacks:       int = 1
    burst_dmg:    float = 0.0   # instant damage on application (shatter etc.)
    source_id:    str = ""

    @property
    def is_immobilizing(self): return self.move_penalty >= 1.0
    @property
    def is_silencing(self):    return self.atk_penalty  >= 1.0

    def effective_dot(self):   return self.dot * min(self.stacks, 3)
    def effective_move_pen(self): return min(1.0, self.move_penalty * self.stacks)
    def effective_atk_pen(self):  return min(1.0, self.atk_penalty  * self.stacks)

    def render(self) -> str:
        stk = f"×{self.stacks}" if self.stacks > 1 else "  "
        return (f"{self.icon}{self.name:<12}{stk} "
                f"[{self.duration}t] "
                f"DOT:{self.effective_dot():4.1f} "
                f"MV:-{self.effective_move_pen()*100:.0f}% "
                f"ATK:-{self.effective_atk_pen()*100:.0f}%")


class StatusEffectManager:
    """
    Manages all active status effects on one agent.
    Handles stacking, combos, counters, and tick processing.
    """
    def __init__(self, owner_id: str):
        self.owner_id   = owner_id
        self.effects:   List[ActiveEffect] = []
        self.combo_log: List[str] = []
        self.burst_pending: float = 0.0   # burst dmg to apply this tick

    # ── Apply a new effect ─────────────────────────────────────────
    def apply(self, effect_name: str, source_id: str,
              force: bool = False) -> Optional[ActiveEffect]:
        defn = EFFECT_DEFS.get(effect_name)
        if not defn: return None

        # Counter: does this effect cancel something?
        cancelled = self._try_cancel(effect_name)

        # Check if same effect already active → stack it
        existing = next((e for e in self.effects if e.name == effect_name), None)
        if existing and not force:
            existing.stacks = min(existing.stacks + 1, 3)
            existing.duration = max(existing.duration,
                                    defn["duration"])  # refresh duration
            fx = existing
        else:
            fx = ActiveEffect(
                name         = effect_name,
                duration     = defn["duration"],
                dot          = defn.get("dot", 0.0),
                move_penalty = defn.get("move_pen", 0.0),
                atk_penalty  = defn.get("atk_pen", 0.0),
                icon         = defn.get("icon", "?"),
                burst_dmg    = defn.get("burst_dmg", 0.0),
                source_id    = source_id,
            )
            self.effects.append(fx)
            if fx.burst_dmg > 0:
                self.burst_pending += fx.burst_dmg

        # Check for combos
        self._check_combos(effect_name, source_id)
        return fx

    def _try_cancel(self, new_effect: str) -> Optional[str]:
        cancelled = COUNTERS.get(new_effect)
        if cancelled:
            before = len(self.effects)
            self.effects = [e for e in self.effects if e.name != cancelled]
            if len(self.effects) < before:
                self.combo_log.append(
                    f"  ✨ [{self.owner_id}] {new_effect} CANCELLED {cancelled}!")
                return cancelled
        return None

    def _check_combos(self, new_effect: str, source_id: str):
        active_names = {e.name for e in self.effects}
        for (a, b), (combo_name, bonus_dmg, msg) in COMBOS.items():
            if new_effect in (a, b) and (a in active_names and b in active_names):
                # Remove source effects, apply combo
                self.effects = [e for e in self.effects
                                if e.name not in (a, b)]
                combo_defn = EFFECT_DEFS.get(combo_name, {})
                combo_fx = ActiveEffect(
                    name         = combo_name,
                    duration     = combo_defn.get("duration", 4),
                    dot          = combo_defn.get("dot", 0.0),
                    move_penalty = combo_defn.get("move_pen", 0.0),
                    atk_penalty  = combo_defn.get("atk_pen", 0.0),
                    icon         = combo_defn.get("icon","💥"),
                    burst_dmg    = combo_defn.get("burst_dmg", 0.0) + bonus_dmg,
                    source_id    = source_id,
                )
                self.effects.append(combo_fx)
                if combo_fx.burst_dmg > 0:
                    self.burst_pending += combo_fx.burst_dmg
                self.combo_log.append(f"  ⚡ COMBO [{self.owner_id}] {msg} "
                                      f"(+{bonus_dmg:.0f} burst dmg)")

    # ── Per-tick processing ────────────────────────────────────────
    def tick(self) -> Tuple[float, float, float]:
        """Returns (total_dot, move_penalty, atk_penalty) for this tick."""
        total_dot  = 0.0
        max_mv_pen = 0.0
        max_at_pen = 0.0
        burst      = self.burst_pending
        self.burst_pending = 0.0

        still_active = []
        for fx in self.effects:
            total_dot  += fx.effective_dot()
            max_mv_pen  = max(max_mv_pen, fx.effective_move_pen())
            max_at_pen  = max(max_at_pen, fx.effective_atk_pen())
            fx.duration -= 1
            if fx.duration > 0:
                still_active.append(fx)
            else:
                self.combo_log.append(f"  ⏰ [{self.owner_id}] {fx.icon}{fx.name} expired")
        self.effects = still_active
        return total_dot + burst, max_mv_pen, max_at_pen

    def has(self, name: str) -> bool:
        return any(e.name == name for e in self.effects)

    def clear(self, name: str):
        self.effects = [e for e in self.effects if e.name != name]

    def flush_log(self) -> List[str]:
        out = self.combo_log[:]
        self.combo_log.clear()
        return out

    def render(self) -> str:
        if not self.effects:
            return f"  [{self.owner_id}] No active effects"
        lines = [f"  [{self.owner_id}] Active Effects ({len(self.effects)}):"]
        for fx in self.effects:
            lines.append(f"    {fx.render()}")
        return "\n".join(lines)


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ STATUS EFFECT STACKING SYSTEM DEMO ══╗\n")
    mgr = StatusEffectManager("TerraKnight")
    log = []

    print("  → Applying burn...")
    mgr.apply("burn", "Ignis-Prime")
    print("  → Applying bleed... (should trigger HEMORRHAGE combo)")
    mgr.apply("bleed", "Voidwalker")
    print("  → Applying slow...")
    mgr.apply("slow", "DustSerpent")
    print("  → Applying root... (should trigger PETRIFY combo with slow)")
    mgr.apply("root", "Sylvan-Wraith")
    print("  → Stacking burn again (×2)...")
    mgr.apply("burn", "Ignis-Prime")

    for line in mgr.flush_log(): print(line)
    print(mgr.render())

    print("\n  ── Ticking 3 times ──")
    for t in range(3):
        dot, mv, atk = mgr.tick()
        print(f"  Tick {t+1}: DOT={dot:.1f}  MV_PEN={mv*100:.0f}%  ATK_PEN={atk*100:.0f}%")
        for line in mgr.flush_log(): print(line)

    print("\n  → Applying freeze + burn = VOLTBURN? No — burn+thunder. Testing freeze+root=FROSTROOT...")
    mgr2 = StatusEffectManager("ZephyrBlade")
    mgr2.apply("freeze", "AquaVex")
    mgr2.apply("root",   "Sylvan-Wraith")
    for line in mgr2.flush_log(): print(line)
    print(mgr2.render())
    print()
