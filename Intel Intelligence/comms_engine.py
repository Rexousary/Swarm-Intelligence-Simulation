"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — COMMUNICATION: ANNOUNCER · CONFIDENCE · SPECTATOR FEED     ║
║   Auto-Broadcast · Agent Tone Shift · Highlight Reel · Observer Mode   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from shared_constants import *

# ─────────────────────────────────────────────────────────────────────
#  1. AUTOMATED STRATEGY ANNOUNCER
# ─────────────────────────────────────────────────────────────────────

ANNOUNCE_TEMPLATES = {
    "key_point_lead": [
        "⚡ {team} has {count} key points — {needed} more = MAP DOMINATION!",
        "🗺️  {team} controls {count}/6 strategic zones. The tide turns!",
        "🔶 {team} is ONE capture away from total map control!",
    ],
    "kill_lead": [
        "💀 {team} leads the kill count {a} to {b} — momentum is THEIRS!",
        "⚔️  {team} on a {streak}-kill streak! The enemy is crumbling!",
        "🩸 {killer} just scored their {count} kill — unstoppable!",
    ],
    "momentum_shift": [
        "📉 {team} lost {count} agents in {ticks} ticks — morale BREAKING!",
        "🔄 MOMENTUM SHIFT! {team} was winning but just lost {count} allies fast!",
        "😨 {team} is in freefall — {alive} agents remain. Can they recover?",
    ],
    "boss_kill": [
        "👑 GRAND MASTER [{boss}] has been DEFEATED by {team}!",
        "🏆 {killer} single-handedly took down [{boss}]! Legendary play!",
        "💥 [{boss}] FALLS! {team} claims the bounty bonus!",
    ],
    "first_blood": [
        "🩸 FIRST BLOOD! {killer} draws first blood against {victim}!",
        "⚡ {killer} strikes FIRST — battle has begun!",
    ],
    "comeback": [
        "🔥 COMEBACK ALERT! {team} was down {deficit} points but is SURGING back!",
        "😤 Don't count {team} out yet — they just turned the tide!",
    ],
    "total_war": [
        "☢️  TOTAL WAR ACTIVATED! All positions exposed! Both teams — engage NOW!",
        "🌋 The tension has reached its PEAK! Full-scale battle commences!",
    ],
    "capture": [
        "🚩 {agent} captures [{landmark}] for {team}!",
        "📍 [{landmark}] falls to {team}! Strategic advantage gained!",
    ],
    "engagement": [
        "⚔️  SQUADS CLASHING near {zone}! [{relay_code}]",
        "🔴 CONTACT! {team_a} and {team_b} are engaging at {zone}!",
    ],
    "weather": [
        "🌦️  WEATHER SHIFT: {weather} rolls in! {affected} agents beware!",
        "☁️  Conditions changing — {weather} is affecting the battlefield!",
    ],
}

@dataclass
class Announcement:
    ann_id:   int
    tick:     int
    timestamp:str
    category: str
    message:  str
    priority: int = 1   # 1=normal 2=important 3=critical

    def render(self) -> str:
        prio_icon = {1:"📢",2:"📣",3:"🔊"}.get(self.priority,"📢")
        return (f"  [{self.timestamp}] {prio_icon} "
                f"T{self.tick:03d} [{self.category:<16}] {self.message}")


class StrategyAnnouncer:
    """
    Auto-generates context-aware broadcast announcements based on game state.
    Subscribes to: kills, captures, weather, engagement, momentum.
    """
    def __init__(self):
        self.announcements: List[Announcement] = []
        self.ann_seq:  int = 0
        self.tick_num: int = 0
        self.first_blood_done: bool = False
        self.last_momentum_tick: Dict[str, int] = {"ALPHA":0,"OMEGA":0}

        # State tracking for momentum detection
        self.recent_deaths: Dict[str, List[int]] = {"ALPHA":[], "OMEGA":[]}
        self.kill_counts:   Dict[str, int] = {"ALPHA":0,"OMEGA":0}
        self.cap_counts:    Dict[str, int] = {"ALPHA":0,"OMEGA":0}
        self.cap_points:    Dict[str, int] = {"ALPHA":0,"OMEGA":0}

    def _make(self, category: str, message: str, priority: int = 1) -> Announcement:
        self.ann_seq += 1
        ts = datetime.now().strftime("%H:%M:%S")
        ann = Announcement(self.ann_seq, self.tick_num, ts,
                           category, message, priority)
        self.announcements.append(ann)
        return ann

    def _template(self, category: str, **kwargs) -> str:
        templates = ANNOUNCE_TEMPLATES.get(category, ["{message}"])
        tmpl = random.choice(templates)
        try:
            return tmpl.format(**kwargs)
        except KeyError:
            return tmpl

    def tick(self, tick: int):
        self.tick_num = tick
        # Cleanup old death records
        for team in self.recent_deaths:
            self.recent_deaths[team] = [
                t for t in self.recent_deaths[team]
                if tick - t < 8
            ]

    # ── Event hooks ────────────────────────────────────────────────

    def on_kill(self, killer_id: str, victim_id: str, killer_team: str,
                victim_team: str, killer_total_kills: int):
        if not self.first_blood_done:
            self.first_blood_done = True
            msg = self._template("first_blood", killer=killer_id, victim=victim_id)
            self._make("FIRST_BLOOD", msg, priority=3)

        self.kill_counts[killer_team] = self.kill_counts.get(killer_team,0) + 1
        self.recent_deaths[victim_team].append(self.tick_num)

        if killer_total_kills in (2, 3, 5):
            msg = self._template("kill_lead", team=killer_team,
                                 a=self.kill_counts[killer_team],
                                 b=self.kill_counts.get(
                                     "OMEGA" if killer_team=="ALPHA" else "ALPHA",0),
                                 streak=killer_total_kills, count=killer_total_kills,
                                 killer=killer_id)
            self._make("KILL_LEAD", msg, priority=2)

        # Momentum shift: 2+ deaths in 5 ticks
        recent = self.recent_deaths[victim_team]
        if len(recent) >= 2 and self.tick_num - self.last_momentum_tick[victim_team] > 10:
            self.last_momentum_tick[victim_team] = self.tick_num
            alive = max(0, 4 - len(recent))
            msg = self._template("momentum_shift", team=victim_team,
                                 count=len(recent), ticks=5, alive=alive)
            self._make("MOMENTUM_SHIFT", msg, priority=3)

    def on_capture(self, agent_id: str, landmark: str, team: str,
                   total_caps: int):
        self.cap_points[team] = total_caps
        msg = self._template("capture", agent=agent_id,
                             landmark=landmark, team=team)
        self._make("CAPTURE", msg, priority=2)
        needed = 5 - total_caps
        if total_caps >= 3:
            msg2 = self._template("key_point_lead", team=team,
                                  count=total_caps, needed=needed)
            self._make("DOMINATION_ALERT", msg2, priority=3)

    def on_boss_kill(self, killer_id: str, boss_id: str, team: str):
        msg = self._template("boss_kill", killer=killer_id,
                             boss=boss_id, team=team)
        self._make("BOSS_KILL", msg, priority=3)

    def on_engagement(self, team_a: str, team_b: str,
                      zone: str, relay_code: str):
        msg = self._template("engagement", team_a=team_a, team_b=team_b,
                             zone=zone, relay_code=relay_code)
        self._make("ENGAGEMENT", msg, priority=2)

    def on_weather_change(self, weather: str, affected_elements: List[str]):
        affected = ", ".join(affected_elements)
        msg = self._template("weather", weather=weather, affected=affected)
        self._make("WEATHER", msg, priority=1)

    def on_total_war(self):
        msg = self._template("total_war")
        self._make("TOTAL_WAR", msg, priority=3)

    def on_comeback(self, team: str, deficit: int):
        msg = self._template("comeback", team=team, deficit=deficit)
        self._make("COMEBACK", msg, priority=2)

    def get_recent(self, n: int = 10) -> List[Announcement]:
        return self.announcements[-n:]

    def render_feed(self, n: int = 15):
        print(f"\n  ╔══ STRATEGY ANNOUNCER FEED ══╗")
        recent = self.get_recent(n)
        if not recent:
            print("  (no announcements)")
        for ann in recent:
            print(ann.render())


# ─────────────────────────────────────────────────────────────────────
#  2. AGENT CONFIDENCE CHAT SYSTEM
# ─────────────────────────────────────────────────────────────────────

BOASTFUL_LINES: Dict[str, List[str]] = {
    "Ignis-Prime":   ["I AM UNSTOPPABLE! 🔥 BURN THEM ALL!",
                      "Did you see that?! Pure FIRE! Another one down!",
                      "They can't contain me! Ignis-Prime DOMINATES!"],
    "AquaVex":       ["The flow is with us. We move as one.",
                      "I've studied their patterns — we have the advantage.",
                      "Controlled. Precise. That is how we win."],
    "Volt-Surge":    ["SPEED KILLS BABY! ⚡ TOO FAST TOO FURIOUS!",
                      "Another one paralyzed! I didn't even see myself move lol!",
                      "The leaderboard won't know what hit it!"],
    "TerraKnight":   ["The earth trembles at my command. As it should.",
                      "Their formation breaks against my wall.",
                      "Victory is inevitable. I am unmovable."],
    "Sylvan-Wraith": ["The forest feasts tonight.",
                      "Their corpses will nourish my roots.",
                      "Nature's wrath cannot be stopped."],
    "DustSerpent":   ["They couldn't see me through the storm. Predictable.",
                      "I set the trap 5 ticks ago. They just now realized it.",
                      "The desert takes what it wants."],
    "ZephyrBlade":   ["I WAS EVERYWHERE! Did you SEE that Hurricane?!",
                      "Nobody can ground me! NOBODY!",
                      "Flying > everything. I've scientifically proven this."],
    "Voidwalker":    ["The void consumes all. As I predicted.",
                      "They saw me coming. It didn't matter.",
                      "Eclipse. Fear. Victory. In that order."],
}

DISTRESS_LINES: Dict[str, List[str]] = {
    "Ignis-Prime":   ["...I miscalculated. Need to regroup.",
                      "They're hitting harder than expected. Falling back."],
    "AquaVex":       ["We've lost too many. Defensive formation — NOW.",
                      "I can't hold this alone. Please, someone..."],
    "Volt-Surge":    ["okay okay okay i messed up. where is everyone??",
                      "my stamina is gone and im surrounded. help??"],
    "TerraKnight":   ["...They broke through. I have failed.",
                      "I cannot hold. The wall... is falling."],
    "Sylvan-Wraith": ["The roots are not enough. We are outnumbered.",
                      "Retreat into the undergrowth..."],
    "DustSerpent":   ["My cover is blown. All traps are triggered.",
                      "I have nothing left. The storm has passed."],
    "ZephyrBlade":   ["i got clipped by EARTH and now im grounded this is humiliating",
                      "...not flying so high anymore."],
    "Voidwalker":    ["The void retreats. For now.",
                      "Even darkness can be extinguished."],
}

QUIET_LINES: Dict[str, List[str]] = {
    "Ignis-Prime":   ["...", "Standing by."],
    "AquaVex":       ["Watching. Waiting.", "..."],
    "Volt-Surge":    ["...", "not feeling it rn"],
    "TerraKnight":   ["...", "Holding position."],
    "Sylvan-Wraith": ["...", "Still."],
    "DustSerpent":   ["...", "In the dust."],
    "ZephyrBlade":   ["...", "low"],
    "Voidwalker":    ["...", "."],
}

NORMAL_LINES: Dict[str, List[str]] = {
    "Ignis-Prime":   ["Pushing forward — who's with me?",
                      "Stay aggressive. We can't let up."],
    "AquaVex":       ["Maintaining position. How's everyone's HP?",
                      "I'll support the push — let me know when you're ready."],
    "Volt-Surge":    ["scouting ahead — back in 2 ticks",
                      "their flyer is getting annoying, someone help with that?"],
    "TerraKnight":   ["Holding center. Call if you need a shield.",
                      "Route through West Tower looks clear."],
    "Sylvan-Wraith": ["Patience. We move on my signal.",
                      "Their formation is weak on the right flank."],
    "DustSerpent":   ["Sandstorm deployed at North Junction. Don't walk through it.",
                      "I've mapped their patrol pattern. We strike in 3 ticks."],
    "ZephyrBlade":   ["spotted 2 of them near Clock Tower, heading your way",
                      "I'll flank — you engage from front"],
    "Voidwalker":    ["I'll take the healer. Stay out of my way.",
                      "Eclipse on my mark."],
}

@dataclass
class ConfidenceChatMessage:
    agent_id: str
    team:     str
    tone:     str   # boastful|distress|quiet|normal
    message:  str
    tick:     int
    timestamp:str

    def render(self) -> str:
        tone_icons = {"boastful":"😤","distress":"😱","quiet":"😶","normal":"😐"}
        icon = tone_icons.get(self.tone,"💬")
        team_icon = "🔶" if self.team == "ALPHA" else "🔷"
        return (f"  [{self.timestamp}] {team_icon}{icon} "
                f"{self.agent_id:<18} [{self.tone:<8}] {self.message}")


class AgentConfidenceChat:
    """
    Generates context-aware chat lines based on agent personality/confidence.
    Integrates with PersonalityDriftEngine tone output.
    """
    def __init__(self):
        self.messages:    List[ConfidenceChatMessage] = []
        self.tick_num:    int = 0
        self.last_spoke:  Dict[str, int] = {}
        self.cooldown:    int = 4   # min ticks between messages per agent

    def tick(self, tick: int):
        self.tick_num = tick

    def agent_speaks(self, agent_id: str, tone: str) -> Optional[ConfidenceChatMessage]:
        """Generate a chat message for an agent based on their tone."""
        if self.tick_num - self.last_spoke.get(agent_id, -99) < self.cooldown:
            return None

        tone_library = {
            "boastful": BOASTFUL_LINES,
            "distress":  DISTRESS_LINES,
            "quiet":     QUIET_LINES,
            "normal":    NORMAL_LINES,
        }
        library = tone_library.get(tone, NORMAL_LINES)
        lines   = library.get(agent_id, ["..."])
        message = random.choice(lines)
        team    = TEAM_OF.get(agent_id, "?")
        ts      = f"{self.tick_num:04d}"

        msg = ConfidenceChatMessage(agent_id, team, tone, message,
                                    self.tick_num, ts)
        self.messages.append(msg)
        self.last_spoke[agent_id] = self.tick_num
        return msg

    def auto_trigger(self, tone_map: Dict[str, str]) -> List[ConfidenceChatMessage]:
        """Given current tone for each agent, randomly trigger chatter."""
        spoken = []
        for agent_id, tone in tone_map.items():
            # Probability of speaking this tick based on tone
            prob = {"boastful":0.35,"distress":0.50,"quiet":0.05,"normal":0.15}.get(tone,0.15)
            if __import__("random").random() < prob:
                msg = self.agent_speaks(agent_id, tone)
                if msg:
                    spoken.append(msg)
        return spoken

    def render_chat(self, team: Optional[str] = None, last_n: int = 20):
        msgs = self.messages[-last_n:]
        if team:
            msgs = [m for m in msgs if m.team == team]
        print(f"\n  ╔══ AGENT CONFIDENCE CHAT {'('+team+')' if team else '(ALL)'} ══╗")
        for m in msgs:
            print(m.render())
        if not msgs:
            print("  (no messages)")


# ─────────────────────────────────────────────────────────────────────
#  3. SPECTATOR FEED
# ─────────────────────────────────────────────────────────────────────

HIGHLIGHT_THRESHOLDS = {
    "multi_kill_min":    2,     # 2+ kills in 3 ticks = highlight
    "boss_kill":         True,
    "total_war":         True,
    "comeback_deficit":  2,     # behind by 2+ points then win = comeback
    "ultimate_used":     True,
    "perfect_dodge":     True,
    "barrier_shatter":   True,
}

@dataclass
class HighlightClip:
    clip_id:    int
    tick:       int
    category:   str
    title:      str
    description:str
    actors:     List[str]
    priority:   int = 1   # 1=good 2=great 3=epic

    def render(self) -> str:
        stars = "⭐" * self.priority
        return (f"  🎬 [{self.clip_id:04d}] T{self.tick:03d} {stars} "
                f"[{self.category:<16}] {self.title}\n"
                f"          {self.description}")


class SpectatorFeed:
    """
    Read-only observer channel with curated highlights.
    Subscribes to all game events and generates highlight clips.
    Accessible to spectators only — not visible to players.
    """
    def __init__(self):
        self.highlights:  List[HighlightClip] = []
        self.clip_seq:    int = 0
        self.tick_num:    int = 0
        self.recent_kills: List[Dict] = []   # for multi-kill detection
        self.spectator_log: List[str] = []

    def _make_clip(self, category: str, title: str, desc: str,
                   actors: List[str], priority: int = 1) -> HighlightClip:
        self.clip_seq += 1
        clip = HighlightClip(self.clip_seq, self.tick_num,
                             category, title, desc, actors, priority)
        self.highlights.append(clip)
        self.spectator_log.append(f"  🎬 CLIP [{self.clip_seq:04d}] [{category}] {title}")
        return clip

    def tick(self, tick: int):
        self.tick_num = tick
        self.recent_kills = [k for k in self.recent_kills
                             if tick - k["tick"] < 4]

    def on_kill(self, killer_id: str, victim_id: str, damage: float,
                is_crit: bool = False, was_ultimate: bool = False):
        self.recent_kills.append({
            "killer": killer_id, "victim": victim_id,
            "tick": self.tick_num, "dmg": damage
        })
        same_killer = [k for k in self.recent_kills if k["killer"] == killer_id]
        if len(same_killer) >= 2:
            label = {2:"DOUBLE KILL",3:"TRIPLE KILL",4:"QUAD KILL"}.get(
                len(same_killer),"MULTI KILL")
            self._make_clip(
                "MULTI_KILL", f"{label}! {killer_id}",
                f"{killer_id} eliminated {len(same_killer)} enemies in rapid succession!",
                [killer_id], priority=min(3, len(same_killer)))
        if was_ultimate:
            self._make_clip(
                "ULTIMATE", f"ULTIMATE KILL — {killer_id}",
                f"{killer_id} used their ULTIMATE to eliminate {victim_id} for {damage:.0f} dmg!",
                [killer_id, victim_id], priority=3)
        elif is_crit:
            self._make_clip(
                "CRIT_KILL", f"Critical Finish — {killer_id}",
                f"{killer_id} landed a CRITICAL HIT on {victim_id} ({damage:.0f} dmg)!",
                [killer_id, victim_id], priority=2)

    def on_boss_kill(self, killer_id: str, boss_id: str, team: str):
        self._make_clip(
            "BOSS_KILL", f"GRAND MASTER SLAIN — {boss_id}",
            f"Team {team}'s [{killer_id}] defeated Island Grand Master [{boss_id}]!",
            [killer_id, boss_id], priority=3)

    def on_total_war(self):
        self._make_clip(
            "TOTAL_WAR", "☢️  TOTAL WAR ACTIVATED",
            "Tension hits 100! All positions fully exposed — FINAL BATTLE BEGINS!",
            ["ALL"], priority=3)

    def on_ultimate_used(self, agent_id: str, ultimate_name: str, targets: int):
        self._make_clip(
            "ULTIMATE", f"{agent_id} activates [{ultimate_name}]!",
            f"{agent_id} unleashes their ULTIMATE — {targets} targets in range!",
            [agent_id], priority=2)

    def on_perfect_dodge(self, agent_id: str, attacker_id: str, damage_avoided: float):
        self._make_clip(
            "DODGE", f"PERFECT DODGE — {agent_id}",
            f"{agent_id} dodged a {damage_avoided:.0f} dmg attack from {attacker_id}!",
            [agent_id, attacker_id], priority=1)

    def on_barrier_shatter(self, agent_id: str, barrier_element: str):
        self._make_clip(
            "BARRIER_BREAK", f"Barrier SHATTERED — {agent_id}",
            f"{agent_id}'s {barrier_element} barrier was completely destroyed!",
            [agent_id], priority=1)

    def on_comeback(self, team: str, from_deficit: int):
        self._make_clip(
            "COMEBACK", f"COMEBACK — Team {team}!",
            f"Team {team} was down {from_deficit} objectives and is SURGING back!",
            [team], priority=3)

    def render_highlight_reel(self, last_n: int = 10):
        clips = sorted(self.highlights, key=lambda c: c.priority, reverse=True)[:last_n]
        print(f"\n  ╔══ SPECTATOR HIGHLIGHT REEL ({len(self.highlights)} clips total) ══╗")
        for clip in clips:
            print(clip.render())
        if not clips:
            print("  (no highlights yet)")

    def render_spectator_feed(self, last_n: int = 20):
        print(f"\n  ╔══ SPECTATOR FEED (Live) ══╗")
        for line in self.spectator_log[-last_n:]:
            print(line)

    def flush_log(self) -> List[str]:
        out = self.spectator_log[:]
        self.spectator_log.clear()
        return out


# ─────────────────────────────────────────────────────────────────────
#  COMBINED COMMS ENGINE
# ─────────────────────────────────────────────────────────────────────

class CommsEngine:
    def __init__(self):
        self.announcer   = StrategyAnnouncer()
        self.agent_chat  = AgentConfidenceChat()
        self.spectator   = SpectatorFeed()
        self.tick_num    = 0

    def tick(self, tick: int, tone_map: Dict[str, str]):
        self.tick_num = tick
        self.announcer.tick(tick)
        self.agent_chat.tick(tick)
        self.spectator.tick(tick)
        # Auto-trigger agent chat
        msgs = self.agent_chat.auto_trigger(tone_map)
        return msgs

    def on_kill(self, killer_id: str, victim_id: str, damage: float,
                killer_team: str, victim_team: str, killer_total_kills: int,
                is_crit: bool = False, was_ultimate: bool = False):
        self.announcer.on_kill(killer_id, victim_id, killer_team,
                               victim_team, killer_total_kills)
        self.spectator.on_kill(killer_id, victim_id, damage, is_crit, was_ultimate)

    def on_capture(self, agent_id: str, landmark: str, team: str, total_caps: int):
        self.announcer.on_capture(agent_id, landmark, team, total_caps)

    def on_boss_kill(self, killer_id: str, boss_id: str, team: str):
        self.announcer.on_boss_kill(killer_id, boss_id, team)
        self.spectator.on_boss_kill(killer_id, boss_id, team)

    def on_ultimate(self, agent_id: str, ult_name: str, targets: int):
        self.spectator.on_ultimate_used(agent_id, ult_name, targets)

    def on_total_war(self):
        self.announcer.on_total_war()
        self.spectator.on_total_war()

    def render_all(self):
        self.announcer.render_feed()
        self.agent_chat.render_chat()
        self.spectator.render_highlight_reel()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ COMMS ENGINE DEMO ══╗\n")
    comms = CommsEngine()
    tone_map = {a:"normal" for a in ALPHA_AGENTS + OMEGA_AGENTS}

    events = [
        (2,  "first_blood",  "Ignis-Prime", "Sylvan-Wraith", 88.0, False, False),
        (4,  "capture",      "Volt-Surge",  "Clock_Tower",   0.0,  False, False),
        (6,  "kill",         "Ignis-Prime", "DustSerpent",   77.0, True,  False),
        (7,  "kill",         "Ignis-Prime", "ZephyrBlade",   55.0, False, False),  # double kill
        (10, "capture",      "TerraKnight", "Parliament_Hall",0.0, False, False),
        (12, "boss_kill",    "AquaVex",     "GM_Ironclad",  900.0, False, False),
        (14, "ultimate",     "Volt-Surge",  "Thunder God",   180.0,False, True),
        (14, "kill_ult",     "Volt-Surge",  "Voidwalker",   180.0, False, True),
        (18, "capture",      "AquaVex",     "North_Stadium", 0.0,  False, False),
        (20, "total_war",    "",            "",              0.0,  False, False),
    ]

    for t in range(1, 25):
        # Shift tones for drama
        if t >= 7:
            tone_map["Ignis-Prime"]   = "boastful"
            tone_map["Sylvan-Wraith"] = "distress"
            tone_map["DustSerpent"]   = "quiet"
        if t >= 14:
            tone_map["Volt-Surge"] = "boastful"
            tone_map["Voidwalker"] = "distress"

        msgs = comms.tick(t, tone_map)
        for m in msgs:
            print(m.render())

        for ev in events:
            ev_t, ev_type = ev[0], ev[1]
            if t != ev_t: continue
            actor, target, dmg, is_crit, was_ult = ev[2], ev[3], ev[4], ev[5], ev[6]
            team = TEAM_OF.get(actor, "ALPHA")
            enemy_team = "OMEGA" if team == "ALPHA" else "ALPHA"

            if ev_type in ("kill","first_blood","kill_ult"):
                kills_so_far = sum(1 for e in events
                                   if e[1] in ("kill","first_blood","kill_ult")
                                   and e[2] == actor and e[0] <= t)
                comms.on_kill(actor, target, dmg, team, enemy_team,
                              kills_so_far, is_crit, was_ult)
            elif ev_type == "capture":
                caps = sum(1 for e in events
                           if e[1]=="capture" and TEAM_OF.get(e[2],"?")==team and e[0]<=t)
                comms.on_capture(actor, target, team, caps)
            elif ev_type == "boss_kill":
                comms.on_boss_kill(actor, target, team)
            elif ev_type == "ultimate":
                comms.on_ultimate(actor, target, 3)
            elif ev_type == "total_war":
                comms.on_total_war()

    comms.render_all()
    print()
