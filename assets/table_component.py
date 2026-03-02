"""
╔══════════════════════════════════════════════════════════════════════╗
║         BACKEND 3 — TABLE COMPONENT                                 ║
║  Elemental Type Chart · Strategy Tables · Agent Stats · Matchups    ║
╚══════════════════════════════════════════════════════════════════════╝

Renders:
  1. Type Effectiveness Matrix    (8×8 attacker vs defender)
  2. Agent Stats Table            (HP / ATK / DEF / SPD / Range / Role)
  3. Ability Reference Table      (all 3 abilities per agent)
  4. Status Effects Table         (all debuffs + duration + DOT)
  5. Matchup Analyser             (given two elements → full breakdown)
  6. Team vs Team Comparison      (ALPHA vs OMEGA strengths)
  7. Strategy Recommendation      (optimal counters for each situation)
  8. Map Landmark Table           (zone, coords, strategic value)
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math

# ─────────────────────────────────────────────────────────────────────
#  DATA DEFINITIONS (mirrors metahuman_swarm.py)
# ─────────────────────────────────────────────────────────────────────

ELEMENTS = ["Fire", "Water", "Thunder", "Earth", "Grass", "Sand", "Flying", "Dark"]
ELEMENT_EMOJI = {
    "Fire":    "🔥", "Water":   "💧", "Thunder": "⚡",
    "Earth":   "🌍", "Grass":   "🌿", "Sand":    "🏜️ ",
    "Flying":  "🌪️ ", "Dark":    "🌑",
}
TEAM = {
    "Fire": "ALPHA", "Water": "ALPHA", "Thunder": "ALPHA", "Earth": "ALPHA",
    "Grass": "OMEGA", "Sand": "OMEGA", "Flying": "OMEGA", "Dark": "OMEGA",
}

# Type effectiveness: TYPE_CHART[attacker][defender] = multiplier
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Fire":    {"Grass":2.0, "Earth":1.5, "Sand":1.0,  "Water":0.5, "Thunder":1.0,"Flying":1.0,"Dark":1.0, "Fire":1.0},
    "Water":   {"Fire":2.0,  "Sand":1.5,  "Grass":0.5, "Thunder":0.5,"Earth":1.0, "Flying":1.0,"Dark":1.0, "Water":1.0},
    "Thunder": {"Water":2.0, "Flying":2.0,"Earth":0.5, "Grass":1.0, "Fire":1.0,  "Sand":1.0,  "Dark":1.0,  "Thunder":1.0},
    "Earth":   {"Thunder":2.0,"Fire":1.5, "Sand":1.5,  "Grass":0.5, "Flying":0.0,"Water":1.0, "Dark":1.0,  "Earth":1.0},
    "Grass":   {"Water":2.0, "Earth":1.5, "Sand":1.5,  "Fire":0.5,  "Flying":0.5,"Thunder":1.0,"Dark":1.0, "Grass":1.0},
    "Sand":    {"Thunder":1.5,"Flying":1.0,"Water":0.5,"Grass":0.5, "Fire":1.0,  "Earth":1.0, "Dark":1.0,  "Sand":1.0},
    "Flying":  {"Grass":2.0, "Earth":2.0, "Thunder":0.5,"Water":1.0,"Fire":1.0,  "Sand":1.0,  "Dark":1.0,  "Flying":1.0},
    "Dark":    {"Thunder":1.5,"Grass":1.5,"Flying":1.5, "Water":1.0,"Fire":1.0,  "Sand":1.0,  "Earth":1.0, "Dark":1.0},
}

AGENT_STATS: Dict[str, Dict] = {
    "Ignis-Prime":   {"element":"Fire",    "team":"ALPHA","hp":280,"atk":90,"def":55,"spd":8.0, "range":18,"role":"Offense",        "emoji":"🔥"},
    "AquaVex":       {"element":"Water",   "team":"ALPHA","hp":320,"atk":70,"def":80,"spd":6.5, "range":20,"role":"Support/Control","emoji":"💧"},
    "Volt-Surge":    {"element":"Thunder", "team":"ALPHA","hp":250,"atk":95,"def":45,"spd":10.0,"range":22,"role":"Burst DPS",      "emoji":"⚡"},
    "TerraKnight":   {"element":"Earth",   "team":"ALPHA","hp":400,"atk":75,"def":95,"spd":5.0, "range":12,"role":"Tank",           "emoji":"🌍"},
    "Sylvan-Wraith": {"element":"Grass",   "team":"OMEGA","hp":300,"atk":72,"def":70,"spd":7.0, "range":16,"role":"Control",        "emoji":"🌿"},
    "DustSerpent":   {"element":"Sand",    "team":"OMEGA","hp":270,"atk":80,"def":60,"spd":9.0, "range":19,"role":"Debuffer",       "emoji":"🏜️ "},
    "ZephyrBlade":   {"element":"Flying",  "team":"OMEGA","hp":240,"atk":88,"def":40,"spd":12.0,"range":25,"role":"Skirmisher",     "emoji":"🌪️ "},
    "Voidwalker":    {"element":"Dark",    "team":"OMEGA","hp":290,"atk":92,"def":50,"spd":8.5, "range":20,"role":"Assassin",       "emoji":"🌑"},
}

ABILITIES: Dict[str, List[Dict]] = {
    "Ignis-Prime": [
        {"name":"Inferno Burst", "dmg":45,"cd":3,"aoe":8.0, "effect":"burn",    "chance":"60%","desc":"AOE fire explosion"},
        {"name":"Flame Lance",   "dmg":30,"cd":1,"aoe":0.0, "effect":"burn",    "chance":"30%","desc":"Precise fire spear"},
        {"name":"Meteor Crash",  "dmg":80,"cd":8,"aoe":15.0,"effect":"stun",    "chance":"40%","desc":"Meteor from sky"},
    ],
    "AquaVex": [
        {"name":"Tidal Wave",    "dmg":40,"cd":4,"aoe":12.0,"effect":"slow",    "chance":"70%","desc":"Massive slow wave"},
        {"name":"Hydro Blast",   "dmg":25,"cd":1,"aoe":0.0, "effect":"—",       "chance":"—",  "desc":"Pressure jet"},
        {"name":"Deep Freeze",   "dmg":60,"cd":7,"aoe":6.0, "effect":"freeze",  "chance":"50%","desc":"Ice encasement"},
    ],
    "Volt-Surge": [
        {"name":"Chain Lightning","dmg":50,"cd":4,"aoe":10.0,"effect":"paralyze","chance":"50%","desc":"Jumps 3 targets"},
        {"name":"Volt Strike",   "dmg":35,"cd":1,"aoe":0.0, "effect":"paralyze","chance":"20%","desc":"Fast bolt"},
        {"name":"Thunder God",   "dmg":90,"cd":10,"aoe":20.0,"effect":"stun",   "chance":"80%","desc":"Divine storm"},
    ],
    "TerraKnight": [
        {"name":"Rock Avalanche","dmg":55,"cd":5,"aoe":10.0, "effect":"slow",   "chance":"50%","desc":"Boulder roll"},
        {"name":"Ground Slam",   "dmg":40,"cd":2,"aoe":6.0,  "effect":"knockback","chance":"60%","desc":"Shockwave slam"},
        {"name":"Tectonic Shift","dmg":70,"cd":9,"aoe":18.0, "effect":"stun",   "chance":"40%","desc":"Earthquake"},
    ],
    "Sylvan-Wraith": [
        {"name":"Vine Trap",     "dmg":35,"cd":3,"aoe":8.0, "effect":"root",    "chance":"70%","desc":"Vine entangle"},
        {"name":"Thorn Barrage", "dmg":28,"cd":1,"aoe":0.0, "effect":"bleed",   "chance":"40%","desc":"Razor thorns"},
        {"name":"Nature's Wrath","dmg":75,"cd":8,"aoe":16.0,"effect":"root",    "chance":"60%","desc":"Forest eruption"},
    ],
    "DustSerpent": [
        {"name":"Sandstorm",     "dmg":38,"cd":4,"aoe":14.0,"effect":"blind",   "chance":"70%","desc":"Blinding storm"},
        {"name":"Sand Spike",    "dmg":25,"cd":1,"aoe":0.0, "effect":"bleed",   "chance":"30%","desc":"Sand projectile"},
        {"name":"Quicksand Pit", "dmg":65,"cd":8,"aoe":10.0,"effect":"root",    "chance":"80%","desc":"Quicksand trap"},
    ],
    "ZephyrBlade": [
        {"name":"Gale Force",    "dmg":42,"cd":3,"aoe":12.0,"effect":"knockback","chance":"60%","desc":"Wind burst"},
        {"name":"Talon Strike",  "dmg":30,"cd":1,"aoe":0.0, "effect":"bleed",   "chance":"30%","desc":"Aerial dive"},
        {"name":"Hurricane",     "dmg":85,"cd":10,"aoe":22.0,"effect":"stun",   "chance":"50%","desc":"Category 5 storm"},
    ],
    "Voidwalker": [
        {"name":"Shadow Blast",  "dmg":45,"cd":3,"aoe":8.0, "effect":"fear",    "chance":"50%","desc":"Dark eruption"},
        {"name":"Void Strike",   "dmg":35,"cd":1,"aoe":0.0, "effect":"drain",   "chance":"40%","desc":"Life drain"},
        {"name":"Eclipse",       "dmg":80,"cd":9,"aoe":18.0,"effect":"blind",   "chance":"90%","desc":"Battlefield darkness"},
    ],
}

STATUS_EFFECTS: List[Dict] = [
    {"name":"burn",      "dur":3,"dot":8.0, "movement":"-",   "attack":"-",  "icon":"🔥","desc":"Deals 8 DOT/tick"},
    {"name":"slow",      "dur":4,"dot":0,   "movement":"−40%","attack":"-",  "icon":"🐢","desc":"Movement halved"},
    {"name":"freeze",    "dur":3,"dot":0,   "movement":"STOP","attack":"STOP","icon":"🧊","desc":"Full immobilize"},
    {"name":"paralyze",  "dur":2,"dot":0,   "movement":"STOP","attack":"−50%","icon":"⚡","desc":"Partial immobilize"},
    {"name":"root",      "dur":3,"dot":0,   "movement":"STOP","attack":"+",  "icon":"🌿","desc":"Pinned in place"},
    {"name":"blind",     "dur":2,"dot":0,   "movement":"-",   "attack":"−60%","icon":"🕶️ ","desc":"Miss chance 60%"},
    {"name":"fear",      "dur":2,"dot":0,   "movement":"FLEE","attack":"STOP","icon":"😱","desc":"Runs from attacker"},
    {"name":"drain",     "dur":3,"dot":5.0, "movement":"-",   "attack":"−20%","icon":"🌑","desc":"5 DOT, −20% ATK"},
    {"name":"bleed",     "dur":4,"dot":6.0, "movement":"-",   "attack":"-",  "icon":"🩸","desc":"6 DOT/tick"},
    {"name":"stun",      "dur":2,"dot":0,   "movement":"STOP","attack":"STOP","icon":"⭐","desc":"Full disable 2t"},
    {"name":"knockback", "dur":1,"dot":0,   "movement":"PUSH","attack":"-",  "icon":"💨","desc":"Pushed back 20u"},
]

LANDMARKS_TABLE: List[Dict] = [
    {"name":"Parliament_Hall", "x":100,"y":100,"zone":"Central","value":"★★★★★","type":"Key Battle Point",  "cap_bonus":"Team earns +2 score/tick"},
    {"name":"Clock_Tower",     "x":100,"y":60, "zone":"North",  "value":"★★★★☆","type":"Sniper Point",      "cap_bonus":"Range +5 for occupying team"},
    {"name":"North_Stadium",   "x":100,"y":30, "zone":"Far N",  "value":"★★★☆☆","type":"Arena",             "cap_bonus":"ATK +10% in zone"},
    {"name":"South_Stadium",   "x":100,"y":170,"zone":"Far S",  "value":"★★★☆☆","type":"Arena",             "cap_bonus":"ATK +10% in zone"},
    {"name":"East_Tower",      "x":160,"y":100,"zone":"East",   "value":"★★★★☆","type":"Defensive Tower",   "cap_bonus":"DEF +15% in zone"},
    {"name":"West_Tower",      "x":40, "y":100,"zone":"West",   "value":"★★★★☆","type":"Defensive Tower",   "cap_bonus":"DEF +15% in zone"},
    {"name":"Battle_Ground_A", "x":60, "y":60, "zone":"NW",     "value":"★★★☆☆","type":"Open Combat Zone",  "cap_bonus":"Mobs spawn rate reduced"},
    {"name":"Battle_Ground_B", "x":140,"y":140,"zone":"SE",     "value":"★★★☆☆","type":"Open Combat Zone",  "cap_bonus":"Mobs spawn rate reduced"},
    {"name":"North_Shore",     "x":50, "y":10, "zone":"Shore",  "value":"★★☆☆☆","type":"Flank Route",       "cap_bonus":"Flanking bonus +25%"},
    {"name":"South_Shore",     "x":150,"y":190,"zone":"Shore",  "value":"★★☆☆☆","type":"Flank Route",       "cap_bonus":"Flanking bonus +25%"},
]

STRATEGIES: List[Dict] = [
    {"name":"Rush Parliament",  "difficulty":"Easy","phase":"Early", "requires":"Tank + Offense",
     "steps":"1) Tank leads to Parliament · 2) Offense clears defenders · 3) Support holds",
     "strength":"Fast cap","weakness":"Exposed flanks"},
    {"name":"Split Push",       "difficulty":"Medium","phase":"Mid", "requires":"All alive",
     "steps":"1) Split into 2 pairs · 2) Hit East+West Tower simultaneously · 3) Converge at Parliament",
     "strength":"Map pressure","weakness":"Coordination required"},
    {"name":"Peel & Protect",   "difficulty":"Medium","phase":"Any", "requires":"Support + Tank",
     "steps":"1) Tank anchors · 2) Support debuffs · 3) DPS focuses squishiest enemy",
     "strength":"Safe fighting","weakness":"Slow"},
    {"name":"Assassin Dive",    "difficulty":"Hard","phase":"Mid-Late","requires":"Dark + Thunder",
     "steps":"1) Eclipse blinds · 2) Thunder paralyzes backline · 3) DPS bursts isolated target",
     "strength":"Burst potential","weakness":"Needs perfect timing"},
    {"name":"Control the Roads","difficulty":"Easy","phase":"Early","requires":"Control + Debuff",
     "steps":"1) Root at junctions · 2) Sandstorm key roads · 3) Force enemies into traps",
     "strength":"Deny movement","weakness":"Passive — won't win alone"},
    {"name":"Tower Defense",    "difficulty":"Medium","phase":"Late","requires":"Any",
     "steps":"1) Claim East+West towers · 2) DEF buff activates · 3) Force enemies into kill zone",
     "strength":"DEF advantage","weakness":"Gives up center"},
]

# ─────────────────────────────────────────────────────────────────────
#  TABLE RENDERER
# ─────────────────────────────────────────────────────────────────────

class TableRenderer:
    """Renders all game tables to terminal with full formatting."""

    EFFECTIVENESS_LABELS = {
        2.0: "2× 💥",
        1.5: "1.5✅",
        1.0: "1×   ",
        0.5: "0.5🛡️",
        0.0: "0  🚫",
    }

    # ── 1. Type Effectiveness Matrix ──────────────────────────────
    def render_type_chart(self):
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 1 — ELEMENTAL TYPE EFFECTIVENESS MATRIX                      ║
║  Read: ROW attacks → COLUMN defends                                  ║
╚══════════════════════════════════════════════════════════════════════╝
  Legend:  2× 💥 Super Effective  |  1.5✅ Advantage  |  1× Normal
           0.5🛡️ Resisted         |  0 🚫 IMMUNE
""")
        col_w = 9
        header_col = 14
        # Team labels
        alpha_count = len([e for e in ELEMENTS if TEAM[e] == "ALPHA"])
        omega_count = len([e for e in ELEMENTS if TEAM[e] == "OMEGA"])

        # Header row: DEFENDING elements
        team_header = (" " * header_col +
                       "◄──── DEFENDING ────►".center(col_w * len(ELEMENTS)))
        print("  " + team_header)

        alpha_bar = "🔶 ALPHA".center(col_w * alpha_count)
        omega_bar = "🔷 OMEGA".center(col_w * omega_count)
        print("  " + " " * header_col + alpha_bar + omega_bar)

        col_headers = " " * header_col
        for elem in ELEMENTS:
            emoji = ELEMENT_EMOJI.get(elem, "  ")
            col_headers += f"{emoji}{elem[:5]:<{col_w - 2}}"
        print("  " + col_headers)
        print("  " + "─" * (header_col + col_w * len(ELEMENTS)))

        # Rows: ATTACKING elements
        for atk in ELEMENTS:
            emoji = ELEMENT_EMOJI.get(atk, "  ")
            team  = TEAM[atk]
            team_tag = "🔶" if team == "ALPHA" else "🔷"
            row   = f"  {team_tag}{emoji}{atk:<10}"
            for def_elem in ELEMENTS:
                mult = TYPE_CHART.get(atk, {}).get(def_elem, 1.0)
                label = self.EFFECTIVENESS_LABELS.get(mult, f"{mult}×   ")
                row += f"{label:<{col_w}}"
            print(row)

        print()

    # ── 2. Agent Stats Table ──────────────────────────────────────
    def render_agent_stats(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 2 — AGENT STATS REFERENCE                                    ║
╚══════════════════════════════════════════════════════════════════════╝""")
        header = (f"  {'Agent':<18} {'Team':<7} {'Element':<10} {'Role':<18} "
                  f"{'HP':>5} {'ATK':>5} {'DEF':>5} {'SPD':>5} {'Range':>6}")
        print(header)
        print("  " + "─" * 90)

        for team_name in ["ALPHA", "OMEGA"]:
            team_bar = "🔶 Team ALPHA" if team_name == "ALPHA" else "🔷 Team OMEGA"
            print(f"\n  ── {team_bar} {'─'*60}")
            for name, s in AGENT_STATS.items():
                if s["team"] != team_name:
                    continue
                emoji = s["emoji"]
                bar_hp  = self._mini_bar(s["hp"],  400)
                bar_atk = self._mini_bar(s["atk"], 100)
                bar_def = self._mini_bar(s["def"], 100)
                print(f"  {emoji}{name:<16} {s['team']:<7} {s['element']:<10} "
                      f"{s['role']:<18} {s['hp']:>5} {s['atk']:>5} {s['def']:>5} "
                      f"{s['spd']:>5} {s['range']:>6}")
                print(f"    HP:{bar_hp}  ATK:{bar_atk}  DEF:{bar_def}")

        # Summary: team totals
        print(f"\n  {'─'*90}")
        for team_name, team_label in [("ALPHA","🔶 ALPHA"), ("OMEGA","🔷 OMEGA")]:
            team_agents = {n: s for n,s in AGENT_STATS.items() if s["team"] == team_name}
            total_hp  = sum(s["hp"]  for s in team_agents.values())
            avg_atk   = sum(s["atk"] for s in team_agents.values()) / len(team_agents)
            avg_def   = sum(s["def"] for s in team_agents.values()) / len(team_agents)
            avg_spd   = sum(s["spd"] for s in team_agents.values()) / len(team_agents)
            print(f"  {team_label} TOTALS/AVG → "
                  f"Total HP:{total_hp}  Avg ATK:{avg_atk:.1f}  "
                  f"Avg DEF:{avg_def:.1f}  Avg SPD:{avg_spd:.1f}")
        print()

    def _mini_bar(self, val: float, max_val: float, width: int = 12) -> str:
        filled = round((val / max_val) * width)
        return "█" * filled + "░" * (width - filled)

    # ── 3. Ability Reference Table ────────────────────────────────
    def render_ability_table(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 3 — ABILITY REFERENCE SHEET                                  ║
╚══════════════════════════════════════════════════════════════════════╝""")
        header = (f"  {'Agent':<18} {'Ability':<20} {'Dmg':>5} {'CD':>4} "
                  f"{'AOE':>5} {'Effect':<12} {'Chance':>7}  Description")
        print(header)
        print("  " + "─" * 100)

        for team_name in ["ALPHA", "OMEGA"]:
            team_bar = "🔶 Team ALPHA" if team_name == "ALPHA" else "🔷 Team OMEGA"
            print(f"\n  ── {team_bar} {'─'*65}")
            for name, s in AGENT_STATS.items():
                if s["team"] != team_name:
                    continue
                emoji = s["emoji"]
                abilities = ABILITIES.get(name, [])
                for i, ab in enumerate(abilities):
                    agent_col = f"{emoji}{name}" if i == 0 else " " * (len(name)+2)
                    aoe_str = f"{ab['aoe']:.0f}u" if ab['aoe'] > 0 else "Single"
                    print(f"  {agent_col:<18} {ab['name']:<20} {ab['dmg']:>5} "
                          f"{ab['cd']:>4}t {aoe_str:>5} {ab['effect']:<12} "
                          f"{ab['chance']:>7}  {ab['desc']}")
        print()

    # ── 4. Status Effects Table ───────────────────────────────────
    def render_status_effects(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 4 — STATUS EFFECTS REFERENCE                                 ║
╚══════════════════════════════════════════════════════════════════════╝""")
        header = (f"  {'Effect':<12} {'Icon':<5} {'Dur':>4} {'DOT/tick':>9} "
                  f"{'Movement':<10} {'Attack':<10}  Description")
        print(header)
        print("  " + "─" * 85)
        for fx in STATUS_EFFECTS:
            dot_str = f"{fx['dot']:.0f} dmg" if fx['dot'] > 0 else "—"
            print(f"  {fx['name']:<12} {fx['icon']:<5} {fx['dur']:>4}t "
                  f"{dot_str:>9} {fx['movement']:<10} {fx['attack']:<10}  {fx['desc']}")
        print()

    # ── 5. Matchup Analyser ───────────────────────────────────────
    def render_matchup(self, attacker: str, defender: str):
        mult_atk = TYPE_CHART.get(attacker, {}).get(defender, 1.0)
        mult_def = TYPE_CHART.get(defender, {}).get(attacker, 1.0)
        ea = ELEMENT_EMOJI.get(attacker, "")
        ed = ELEMENT_EMOJI.get(defender, "")

        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 5 — MATCHUP ANALYSER: {ea}{attacker} vs {ed}{defender}
╚══════════════════════════════════════════════════════════════════════╝""")

        def eff_label(m):
            return {2.0:"💥 SUPER EFFECTIVE (×2.0)",
                    1.5:"✅ Advantage (×1.5)",
                    1.0:"⚖️  Neutral (×1.0)",
                    0.5:"🛡️  Resisted (×0.5)",
                    0.0:"🚫 IMMUNE (×0)"}.get(m, f"×{m}")

        print(f"\n  {ea}{attacker} attacking {ed}{defender}:  {eff_label(mult_atk)}")
        print(f"  {ed}{defender} attacking {ea}{attacker}:  {eff_label(mult_def)}")

        # Overall verdict
        if mult_atk > mult_def:
            winner = attacker
            print(f"\n  🏆 Verdict: {ea}{attacker} has the TYPE ADVANTAGE in this matchup")
        elif mult_def > mult_atk:
            winner = defender
            print(f"\n  🏆 Verdict: {ed}{defender} has the TYPE ADVANTAGE in this matchup")
        else:
            print(f"\n  🏆 Verdict: EVEN matchup — stats and skill decide this fight")

        # Abilities that matter
        atk_abilities = [ab for ag, abs_ in ABILITIES.items()
                         for ab in abs_
                         if AGENT_STATS.get(ag, {}).get("element") == attacker]
        print(f"\n  Best {ea}{attacker} abilities vs {ed}{defender}:")
        if atk_abilities:
            best = sorted(atk_abilities, key=lambda a: a["dmg"] * mult_atk, reverse=True)[:2]
            for ab in best:
                print(f"    ▶ {ab['name']} → effective dmg: {ab['dmg'] * mult_atk:.0f}  [{ab['effect']}]")
        print()

    # ── 6. Team Comparison ────────────────────────────────────────
    def render_team_comparison(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 6 — TEAM ALPHA vs TEAM OMEGA COMPARISON                      ║
╚══════════════════════════════════════════════════════════════════════╝""")
        alpha = {n: s for n, s in AGENT_STATS.items() if s["team"] == "ALPHA"}
        omega = {n: s for n, s in AGENT_STATS.items() if s["team"] == "OMEGA"}

        stats_compare = [
            ("Total HP",      sum(s["hp"] for s in alpha.values()),
                              sum(s["hp"] for s in omega.values())),
            ("Avg ATK",       sum(s["atk"] for s in alpha.values())/len(alpha),
                              sum(s["atk"] for s in omega.values())/len(omega)),
            ("Avg DEF",       sum(s["def"] for s in alpha.values())/len(alpha),
                              sum(s["def"] for s in omega.values())/len(omega)),
            ("Avg SPD",       sum(s["spd"] for s in alpha.values())/len(alpha),
                              sum(s["spd"] for s in omega.values())/len(omega)),
            ("Max Range",     max(s["range"] for s in alpha.values()),
                              max(s["range"] for s in omega.values())),
            ("Avg Range",     sum(s["range"] for s in alpha.values())/len(alpha),
                              sum(s["range"] for s in omega.values())/len(omega)),
        ]

        print(f"\n  {'Stat':<15} {'🔶 ALPHA':>10} {'🔷 OMEGA':>10}  {'Advantage'}")
        print(f"  {'─'*55}")
        for stat, a_val, o_val in stats_compare:
            bar_a = "█" * int((a_val / max(a_val, o_val, 1)) * 10)
            bar_o = "█" * int((o_val / max(a_val, o_val, 1)) * 10)
            advantage = "🔶 ALPHA" if a_val > o_val else ("🔷 OMEGA" if o_val > a_val else "⚖️  TIE")
            print(f"  {stat:<15} {a_val:>10.1f} {o_val:>10.1f}  {advantage}")

        # Type coverage: how many types does each team have super-effective hits on?
        def coverage_score(team_name):
            elems = [s["element"] for s in AGENT_STATS.values() if s["team"] == team_name]
            covered = set()
            for atk in elems:
                for def_elem, mult in TYPE_CHART.get(atk, {}).items():
                    if mult >= 2.0:
                        covered.add(def_elem)
            return covered

        alpha_cov = coverage_score("ALPHA")
        omega_cov = coverage_score("OMEGA")
        print(f"\n  Super-effective coverage:")
        print(f"    🔶 ALPHA can 2× hit: {', '.join(sorted(alpha_cov))} ({len(alpha_cov)} types)")
        print(f"    🔷 OMEGA can 2× hit: {', '.join(sorted(omega_cov))} ({len(omega_cov)} types)")
        print()

    # ── 7. Strategy Table ─────────────────────────────────────────
    def render_strategy_table(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 7 — STRATEGY RECOMMENDATION TABLE                            ║
╚══════════════════════════════════════════════════════════════════════╝""")
        header = (f"  {'Strategy':<22} {'Difficulty':<12} {'Phase':<10} "
                  f"{'Requires':<25} {'Strength':<20} {'Weakness'}")
        print(header)
        print("  " + "─" * 110)
        for s in STRATEGIES:
            diff_icon = {"Easy":"🟢","Medium":"🟡","Hard":"🔴"}.get(s["difficulty"], "⚪")
            print(f"  {diff_icon}{s['name']:<21} {s['difficulty']:<12} {s['phase']:<10} "
                  f"{s['requires']:<25} {s['strength']:<20} {s['weakness']}")
            print(f"    Steps: {s['steps']}")
        print()

    # ── 8. Landmark / Map Table ───────────────────────────────────
    def render_landmark_table(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  TABLE 8 — MAP LANDMARK REFERENCE                                   ║
╚══════════════════════════════════════════════════════════════════════╝""")
        header = (f"  {'Landmark':<22} {'Coords':>10} {'Zone':<10} "
                  f"{'Value':<12} {'Type':<22} {'Capture Bonus'}")
        print(header)
        print("  " + "─" * 110)
        for lm in sorted(LANDMARKS_TABLE, key=lambda x: x["value"], reverse=True):
            print(f"  {lm['name']:<22} ({lm['x']:3d},{lm['y']:3d})  {lm['zone']:<10} "
                  f"{lm['value']:<12} {lm['type']:<22} {lm['cap_bonus']}")
        print()

    # ── Quick Counter Chart ───────────────────────────────────────
    def render_counter_chart(self):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  BONUS — QUICK COUNTER REFERENCE                                    ║
╚══════════════════════════════════════════════════════════════════════╝""")
        print(f"  {'Element':<10}  {'Strong AGAINST (2×)':<30}  {'Weak TO (×0.5 or immune)':<30}  {'Immune TO'}")
        print(f"  {'─'*100}")
        for elem in ELEMENTS:
            chart = TYPE_CHART.get(elem, {})
            strong  = [f"{ELEMENT_EMOJI.get(d,'')}{d}" for d, m in chart.items() if m >= 2.0]
            weak    = [f"{ELEMENT_EMOJI.get(d,'')}{d}" for d, m in TYPE_CHART.items()
                       if m.get(elem, 1.0) >= 2.0 and d != elem]
            immune_to = [f"{ELEMENT_EMOJI.get(d,'')}{d}" for d, m in TYPE_CHART.items()
                         if m.get(elem, 1.0) == 0.0]
            emoji = ELEMENT_EMOJI.get(elem, "  ")
            team  = TEAM.get(elem, "?")
            team_tag = "🔶" if team == "ALPHA" else "🔷"
            print(f"  {team_tag}{emoji}{elem:<8}  "
                  f"{', '.join(strong) if strong else '—':<30}  "
                  f"{', '.join(weak)   if weak   else '—':<30}  "
                  f"{', '.join(immune_to) if immune_to else '—'}")
        print()

    # ── Render ALL tables ─────────────────────────────────────────
    def render_all(self):
        self.render_type_chart()
        self.render_agent_stats()
        self.render_ability_table()
        self.render_status_effects()
        self.render_team_comparison()
        self.render_strategy_table()
        self.render_landmark_table()
        self.render_counter_chart()
        # Sample matchup
        self.render_matchup("Thunder", "Flying")
        self.render_matchup("Fire", "Water")

# ─────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        TABLE COMPONENT — FULL RENDER                                ║
║  Metahuman Swarm Battle Engine Reference System                     ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    renderer = TableRenderer()
    renderer.render_all()

if __name__ == "__main__":
    main()
