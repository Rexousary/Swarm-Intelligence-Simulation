"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — DYNAMIC WEATHER ENGINE + DAY/NIGHT CYCLE                   ║
║   Weather States · Elemental Modifiers · Vision · Radar Effects         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from shared_constants import *

# ── Weather types ──────────────────────────────────────────────────────
WEATHER_TYPES: Dict[str, Dict] = {
    "clear": {
        "icon":"☀️ ","label":"Clear",       "duration":(15,25),
        "element_mods":  {},
        "vision_mult":   1.0,  "speed_mult": 1.0,
        "radar_range":   1.0,  "dot_mult":   1.0,
        "fog_density":   0.0,
        "desc": "Standard conditions. No modifiers.",
    },
    "rain": {
        "icon":"🌧️ ","label":"Rain",        "duration":(10,18),
        "element_mods":  {"Water":{"atk":1.30,"spd":1.10},
                          "Fire": {"atk":0.70,"spd":0.90},
                          "Thunder":{"atk":0.80}},
        "vision_mult":   0.75, "speed_mult": 0.90,
        "radar_range":   0.80, "dot_mult":   0.80,
        "fog_density":   0.20,
        "desc": "Buffs Water, nerfs Fire. Reduces vision & radar.",
    },
    "thunderstorm": {
        "icon":"⛈️ ","label":"Thunderstorm","duration":(8,14),
        "element_mods":  {"Thunder":{"atk":1.50,"spd":1.20,"crit":0.15},
                          "Water":  {"atk":1.10},
                          "Fire":   {"atk":0.60},
                          "Earth":  {"atk":0.80}},
        "vision_mult":   0.60, "speed_mult": 0.85,
        "radar_range":   0.60, "dot_mult":   1.20,
        "fog_density":   0.35,
        "random_strike_chance": 0.05,   # AOE lightning bolt per tick
        "desc": "Major Thunder buffs. Random lightning strikes open-field agents.",
    },
    "sandstorm": {
        "icon":"🏜️ ","label":"Sandstorm",   "duration":(8,15),
        "element_mods":  {"Sand":  {"atk":1.40,"spd":1.15,"dodge":0.15},
                          "Grass": {"atk":0.75},
                          "Flying":{"atk":0.80,"spd":0.75}},
        "vision_mult":   0.40, "speed_mult": 0.80,
        "radar_range":   0.50, "dot_mult":   1.0,
        "fog_density":   0.50,
        "blind_chance":  0.25,   # % chance per tick to blind any open-field agent
        "desc": "Buffs Sand. Blinds open-field agents. Halves radar range.",
    },
    "fog": {
        "icon":"🌫️ ","label":"Dense Fog",  "duration":(10,20),
        "element_mods":  {"Dark":{"dodge":0.20,"atk":1.20},
                          "Flying":{"spd":0.70}},
        "vision_mult":   0.35, "speed_mult": 0.90,
        "radar_range":   0.45, "dot_mult":   1.0,
        "fog_density":   0.70,
        "desc": "Heavily restricts vision. Benefits Dark agents.",
    },
    "heatwave": {
        "icon":"🔥 ","label":"Heatwave",    "duration":(12,20),
        "element_mods":  {"Fire":  {"atk":1.35,"crit":0.10},
                          "Water": {"atk":0.85},
                          "Earth": {"atk":1.10}},
        "vision_mult":   1.10, "speed_mult": 0.95,
        "radar_range":   1.10, "dot_mult":   1.40,
        "fog_density":   0.05,
        "stamina_drain": 1.5,   # extra stamina drain per tick
        "desc": "Boosts Fire. Increases all DOT damage. Drains stamina faster.",
    },
    "blizzard": {
        "icon":"❄️ ","label":"Blizzard",    "duration":(8,12),
        "element_mods":  {"Water": {"atk":1.20, "freeze_chance":0.10},
                          "Fire":  {"atk":0.65,"spd":0.75},
                          "Flying":{"spd":0.60}},
        "vision_mult":   0.50, "speed_mult": 0.70,
        "radar_range":   0.55, "dot_mult":   0.70,
        "fog_density":   0.45,
        "freeze_chance": 0.08,   # all agents have 8% chance of being frozen each tick
        "desc": "Slows all. Random freeze chance. Buffs Water's freeze abilities.",
    },
}

# ── Weather transition probabilities (current → next) ─────────────────
WEATHER_TRANSITIONS: Dict[str, List[Tuple[str, float]]] = {
    "clear":       [("clear",0.35),("rain",0.25),("thunderstorm",0.10),
                    ("sandstorm",0.10),("fog",0.10),("heatwave",0.07),("blizzard",0.03)],
    "rain":        [("clear",0.30),("thunderstorm",0.35),("fog",0.20),("blizzard",0.10),("rain",0.05)],
    "thunderstorm":[("rain",0.40),("clear",0.40),("fog",0.15),("blizzard",0.05)],
    "sandstorm":   [("clear",0.50),("heatwave",0.30),("sandstorm",0.15),("fog",0.05)],
    "fog":         [("clear",0.50),("rain",0.25),("fog",0.15),("blizzard",0.10)],
    "heatwave":    [("clear",0.45),("sandstorm",0.30),("heatwave",0.15),("thunderstorm",0.10)],
    "blizzard":    [("clear",0.40),("fog",0.30),("rain",0.20),("blizzard",0.10)],
}

# ── Time of day ────────────────────────────────────────────────────────
DAY_PHASES = {
    "dawn":      {"hours":(5,8),   "icon":"🌅","vision_mult":0.85,
                  "element_mods":{"Flying":{"atk":1.15,"spd":1.10}},
                  "desc":"Flying agents gain speed & power at dawn"},
    "day":       {"hours":(8,17),  "icon":"☀️ ","vision_mult":1.0,
                  "element_mods":{},
                  "desc":"Standard visibility. No modifiers."},
    "dusk":      {"hours":(17,20), "icon":"🌆","vision_mult":0.80,
                  "element_mods":{"Fire":{"atk":1.10},"Dark":{"dodge":0.08}},
                  "desc":"Fire gains power. Dark begins to stir."},
    "night":     {"hours":(20,5),  "icon":"🌙","vision_mult":0.50,
                  "element_mods":{"Dark":{"atk":1.30,"dodge":0.20,"crit":0.10},
                                   "Fire":{"atk":0.85},"Grass":{"atk":0.80}},
                  "desc":"Night favors Dark. Vision radius halved for others."},
}

TICKS_PER_HOUR = 3   # 3 game ticks = 1 in-game hour


@dataclass
class WeatherState:
    weather_type: str
    ticks_remaining: int
    intensity: float = 1.0   # 0.5–1.5 modifier on all effects

    @property
    def defn(self): return WEATHER_TYPES[self.weather_type]
    @property
    def icon(self):  return self.defn["icon"]
    @property
    def label(self): return self.defn["label"]

    def get_element_mod(self, element: str, stat: str) -> float:
        mods = self.defn["element_mods"]
        return mods.get(element, {}).get(stat, 1.0)

    def vision_radius(self, base: float) -> float:
        return base * self.defn["vision_mult"] * self.intensity

    def radar_range_mult(self) -> float:
        return self.defn["radar_range"] * self.intensity

    def render(self) -> str:
        return (f"  {self.icon} {self.label:<14} "
                f"TTL:{self.ticks_remaining:3d}t  "
                f"Intensity:×{self.intensity:.2f}  "
                f"Vision:×{self.defn['vision_mult']:.2f}  "
                f"Radar:×{self.defn['radar_range']:.2f}  "
                f"Speed:×{self.defn['speed_mult']:.2f}")


class WeatherEngine:
    """
    Manages dynamic weather transitions and day/night cycle.
    Provides per-element modifiers to all other backends.
    """
    def __init__(self, start_weather: str = "clear", start_hour: int = 8):
        self.current       = self._make_weather(start_weather)
        self.history:      List[str] = []
        self.tick_num:     int  = 0
        self.game_hour:    int  = start_hour
        self.game_minute:  int  = 0
        self.day_number:   int  = 1
        self.log:          List[str] = []
        self.event_queue:  List[Dict] = []   # weather events to broadcast

    def _make_weather(self, weather_type: str) -> WeatherState:
        defn = WEATHER_TYPES[weather_type]
        dur_min, dur_max = defn["duration"]
        intensity = random.uniform(0.75, 1.25)
        return WeatherState(
            weather_type     = weather_type,
            ticks_remaining  = random.randint(dur_min, dur_max),
            intensity        = intensity,
        )

    def _advance_time(self):
        self.game_minute += (60 // TICKS_PER_HOUR)
        if self.game_minute >= 60:
            self.game_minute -= 60
            self.game_hour   += 1
            if self.game_hour >= 24:
                self.game_hour -= 24
                self.day_number += 1
                self.log.append(f"  🌅 Day {self.day_number} has begun!")

    def _get_day_phase(self) -> Tuple[str, Dict]:
        h = self.game_hour
        for phase, info in DAY_PHASES.items():
            lo, hi = info["hours"]
            if lo <= hi:
                if lo <= h < hi: return phase, info
            else:   # wraps midnight (night: 20–5)
                if h >= lo or h < hi: return phase, info
        return "day", DAY_PHASES["day"]

    def tick(self) -> Dict:
        """Advance one game tick. Returns dict of active modifiers."""
        self.tick_num += 1
        self._advance_time()
        self.current.ticks_remaining -= 1

        # Transition weather if expired
        if self.current.ticks_remaining <= 0:
            old_label = self.current.label
            transitions = WEATHER_TRANSITIONS.get(self.current.weather_type, [])
            roll        = random.random()
            cumulative  = 0.0
            new_type    = "clear"
            for (wtype, prob) in transitions:
                cumulative += prob
                if roll <= cumulative:
                    new_type = wtype
                    break
            self.current = self._make_weather(new_type)
            msg = (f"  🌦️  WEATHER CHANGED: {old_label} → "
                   f"{self.current.icon}{self.current.label} "
                   f"(intensity ×{self.current.intensity:.2f})")
            self.log.append(msg)
            self.history.append(f"T{self.tick_num:04d}: {old_label} → {self.current.label}")
            self.event_queue.append({"type":"weather_change",
                                     "from":old_label,"to":self.current.label,
                                     "tick":self.tick_num})

        phase_name, phase_info = self._get_day_phase()
        return self._build_modifier_dict(phase_name, phase_info)

    def _build_modifier_dict(self, phase_name: str, phase_info: Dict) -> Dict:
        """Returns combined weather+time modifiers for all elements."""
        result = {
            "weather":      self.current.weather_type,
            "weather_icon": self.current.icon,
            "phase":        phase_name,
            "phase_icon":   phase_info["icon"],
            "time":         f"{self.game_hour:02d}:{self.game_minute:02d}",
            "day":          self.day_number,
            "vision_mult":  (self.current.defn["vision_mult"] *
                             phase_info["vision_mult"] *
                             self.current.intensity),
            "speed_mult":   self.current.defn["speed_mult"],
            "radar_mult":   self.current.defn["radar_range"],
            "dot_mult":     self.current.defn["dot_mult"],
            "fog_density":  self.current.defn["fog_density"],
            "element_mods": {},
        }
        # Merge weather + phase element mods
        all_elements = set(list(self.current.defn["element_mods"].keys()) +
                           list(phase_info["element_mods"].keys()))
        for el in all_elements:
            w_mod = self.current.defn["element_mods"].get(el, {})
            p_mod = phase_info["element_mods"].get(el, {})
            merged = {}
            for stat in set(list(w_mod.keys()) + list(p_mod.keys())):
                w_val = w_mod.get(stat, 1.0)
                p_val = p_mod.get(stat, 1.0)
                # If both modify the same stat, multiply them
                merged[stat] = w_val * p_val
            result["element_mods"][el] = merged

        # Special event rolls
        events = []
        if self.current.weather_type == "thunderstorm":
            if random.random() < self.current.defn.get("random_strike_chance", 0):
                strike_x = random.uniform(0, MAP_W)
                strike_y = random.uniform(0, MAP_H)
                events.append({"type":"lightning_strike",
                                "pos":(strike_x, strike_y), "dmg":30.0})
                self.log.append(f"  ⚡ LIGHTNING STRIKE at "
                                f"({strike_x:.0f},{strike_y:.0f})!")
        if self.current.weather_type == "sandstorm":
            if random.random() < self.current.defn.get("blind_chance", 0):
                events.append({"type":"sandblind", "affected":"open_field"})
        if self.current.weather_type == "blizzard":
            if random.random() < self.current.defn.get("freeze_chance", 0):
                events.append({"type":"blizzard_freeze"})
                self.log.append(f"  ❄️  BLIZZARD FREEZE — open-field agents risk freeze!")

        result["events"] = events
        return result

    def get_agent_modifiers(self, element: str, modifiers: Dict) -> Dict:
        """Get final stat multipliers for a specific element given current conditions."""
        el_mods = modifiers.get("element_mods", {}).get(element, {})
        return {
            "atk_mult":   el_mods.get("atk", 1.0),
            "spd_mult":   el_mods.get("spd", 1.0) * modifiers.get("speed_mult", 1.0),
            "dodge_bonus":el_mods.get("dodge", 0.0),
            "crit_bonus": el_mods.get("crit", 0.0),
            "vision":     modifiers.get("vision_mult", 1.0) * 25.0,
        }

    def flush_log(self) -> List[str]:
        out = self.log[:]
        self.log.clear()
        return out

    def flush_events(self) -> List[Dict]:
        out = self.event_queue[:]
        self.event_queue.clear()
        return out

    def render_status(self, modifiers: Dict):
        phase = modifiers["phase"]
        phase_info = DAY_PHASES[phase]
        print(f"\n  ╔══ WEATHER & TIME STATUS ══╗")
        print(f"  ║  {modifiers['phase_icon']} Day {modifiers['day']}  "
              f"{modifiers['time']}  Phase: {phase.upper()}")
        print(f"  ║  {self.current.render()}")
        print(f"  ║  Vision:×{modifiers['vision_mult']:.2f}  "
              f"Radar:×{modifiers['radar_mult']:.2f}  "
              f"DOT:×{modifiers['dot_mult']:.2f}  "
              f"Fog:{modifiers['fog_density']*100:.0f}%")
        if modifiers["element_mods"]:
            print(f"  ║  Element Modifiers:")
            for el, mods in modifiers["element_mods"].items():
                mod_str = " | ".join(f"{k}:×{v:.2f}" for k,v in mods.items())
                print(f"  ║    {ELEMENT_OF.get(el,el)}: {mod_str}")
        print(f"  ╚{'═'*40}")
        print(f"  📜 {self.current.defn['desc']}")
        print(f"  📜 {phase_info['desc']}")

    def render_history(self):
        print(f"\n  📅 Weather History ({len(self.history)} changes):")
        for entry in self.history[-10:]:
            print(f"    {entry}")


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ WEATHER ENGINE + DAY/NIGHT DEMO ══╗\n")
    engine = WeatherEngine(start_weather="clear", start_hour=6)

    for t in range(1, 60):
        mods = engine.tick()
        for line in engine.flush_log():
            print(line)
        events = engine.flush_events()
        for ev in events:
            print(f"  📡 EVENT: {ev}")

        if t in (1, 15, 30, 45, 59):
            engine.render_status(mods)
            # Show specific agent mods
            for elem in ["Fire","Thunder","Dark","Flying"]:
                ag_mods = engine.get_agent_modifiers(elem, mods)
                print(f"    {elem}: ATK×{ag_mods['atk_mult']:.2f}  "
                      f"SPD×{ag_mods['spd_mult']:.2f}  "
                      f"Dodge+{ag_mods['dodge_bonus']*100:.0f}%  "
                      f"Vision:{ag_mods['vision']:.1f}u")

    engine.render_history()
    print()
