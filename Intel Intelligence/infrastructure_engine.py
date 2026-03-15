"""
╔══════════════════════════════════════════════════════════════════════════╗
║   BACKEND — INFRASTRUCTURE: SAVE/LOAD · EVENT BUS · WEBSOCKET FEED     ║
║   State Serialization · Pub-Sub · Async Real-Time Push                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import json, time, asyncio, threading, queue
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from collections import defaultdict
from shared_constants import *

# ─────────────────────────────────────────────────────────────────────
#  1. SAVE / LOAD STATE SYSTEM
# ─────────────────────────────────────────────────────────────────────

SAVE_VERSION = "1.0"

@dataclass
class AgentSnapshot:
    agent_id:    str
    team:        str
    element:     str
    hp:          float
    max_hp:      float
    position:    List[float]
    alive:       bool
    level:       int
    xp:          int
    kills:       int
    state:       str    # behaviour state name

@dataclass
class TeamSnapshot:
    team_name:   str
    score:       int
    strategy:    str
    agents:      List[AgentSnapshot] = field(default_factory=list)

@dataclass
class MapSnapshot:
    controlled_points: Dict[str, str]
    weather:           str
    day_phase:         str
    game_hour:         int
    blocked_roads:     List[str]
    tension:           float

@dataclass
class FullGameState:
    save_id:     str
    version:     str
    tick:        int
    timestamp:   str
    alpha:       TeamSnapshot
    omega:       TeamSnapshot
    map_state:   MapSnapshot
    active_flares:   List[Dict] = field(default_factory=list)
    active_effects:  Dict[str, List[str]] = field(default_factory=dict)
    xp_records:      Dict[str, int] = field(default_factory=dict)
    match_events:    List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "save_id":    self.save_id,
            "version":    self.version,
            "tick":       self.tick,
            "timestamp":  self.timestamp,
            "alpha": {
                "team_name": self.alpha.team_name,
                "score":     self.alpha.score,
                "strategy":  self.alpha.strategy,
                "agents": [vars(a) for a in self.alpha.agents],
            },
            "omega": {
                "team_name": self.omega.team_name,
                "score":     self.omega.score,
                "strategy":  self.omega.strategy,
                "agents": [vars(a) for a in self.omega.agents],
            },
            "map_state": vars(self.map_state),
            "active_flares":  self.active_flares,
            "active_effects": self.active_effects,
            "xp_records":     self.xp_records,
            "match_events":   self.match_events[-50:],  # last 50
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'FullGameState':
        alpha_agents = [AgentSnapshot(**a) for a in d["alpha"]["agents"]]
        omega_agents = [AgentSnapshot(**a) for a in d["omega"]["agents"]]
        alpha_team   = TeamSnapshot(d["alpha"]["team_name"],
                                    d["alpha"]["score"],
                                    d["alpha"]["strategy"],
                                    alpha_agents)
        omega_team   = TeamSnapshot(d["omega"]["team_name"],
                                    d["omega"]["score"],
                                    d["omega"]["strategy"],
                                    omega_agents)
        map_state    = MapSnapshot(**d["map_state"])
        return cls(
            save_id  = d["save_id"],
            version  = d["version"],
            tick     = d["tick"],
            timestamp= d["timestamp"],
            alpha    = alpha_team,
            omega    = omega_team,
            map_state= map_state,
            active_flares  = d.get("active_flares", []),
            active_effects = d.get("active_effects", {}),
            xp_records     = d.get("xp_records", {}),
            match_events   = d.get("match_events", []),
        )


class SaveLoadSystem:
    """
    Serializes and deserializes full game state to/from JSON.
    Supports auto-save every N ticks and manual checkpoints.
    """
    def __init__(self, auto_save_interval: int = 10):
        self.auto_save_interval = auto_save_interval
        self.checkpoints: List[FullGameState] = []
        self.save_paths:  List[str] = []
        self.tick_num:    int = 0
        self.last_auto_save: int = 0

    def create_state(self, tick: int,
                     alpha_data: Dict, omega_data: Dict,
                     map_data: Dict, **extras) -> FullGameState:
        """Build a FullGameState from runtime data dicts."""
        save_id = f"SAVE_{tick:05d}_{int(time.time())}"
        alpha = TeamSnapshot(
            team_name="ALPHA",
            score=alpha_data.get("score", 0),
            strategy=alpha_data.get("strategy","Balanced"),
            agents=[AgentSnapshot(
                agent_id=a["id"], team="ALPHA",
                element=ELEMENT_OF.get(a["id"],"?"),
                hp=a["hp"], max_hp=a["max_hp"],
                position=list(a["pos"]),
                alive=a["hp"] > 0,
                level=a.get("level",1), xp=a.get("xp",0),
                kills=a.get("kills",0), state=a.get("state","ROAM")
            ) for a in alpha_data.get("agents", [])]
        )
        omega = TeamSnapshot(
            team_name="OMEGA",
            score=omega_data.get("score",0),
            strategy=omega_data.get("strategy","Balanced"),
            agents=[AgentSnapshot(
                agent_id=a["id"], team="OMEGA",
                element=ELEMENT_OF.get(a["id"],"?"),
                hp=a["hp"], max_hp=a["max_hp"],
                position=list(a["pos"]),
                alive=a["hp"] > 0,
                level=a.get("level",1), xp=a.get("xp",0),
                kills=a.get("kills",0), state=a.get("state","ROAM")
            ) for a in omega_data.get("agents", [])]
        )
        map_state = MapSnapshot(
            controlled_points = map_data.get("controlled_points",{}),
            weather           = map_data.get("weather","clear"),
            day_phase         = map_data.get("day_phase","day"),
            game_hour         = map_data.get("game_hour",8),
            blocked_roads     = map_data.get("blocked_roads",[]),
            tension           = map_data.get("tension",0.0),
        )
        return FullGameState(
            save_id   = save_id,
            version   = SAVE_VERSION,
            tick      = tick,
            timestamp = datetime.now().isoformat(),
            alpha     = alpha,
            omega     = omega,
            map_state = map_state,
            **extras
        )

    def save(self, state: FullGameState,
             path: Optional[str] = None) -> str:
        path = path or f"saves/{state.save_id}.json"
        import os; os.makedirs("saves", exist_ok=True)
        with open(path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        self.checkpoints.append(state)
        self.save_paths.append(path)
        print(f"  💾 STATE SAVED: [{state.save_id}] tick:{state.tick} → {path}")
        return path

    def load(self, path: str) -> FullGameState:
        with open(path) as f:
            data = json.load(f)
        state = FullGameState.from_dict(data)
        print(f"  📂 STATE LOADED: [{state.save_id}] tick:{state.tick} "
              f"from {path}")
        return state

    def auto_save_check(self, tick: int, state_builder: Callable) -> Optional[str]:
        self.tick_num = tick
        if tick - self.last_auto_save >= self.auto_save_interval:
            state = state_builder()
            path  = self.save(state)
            self.last_auto_save = tick
            return path
        return None

    def list_saves(self):
        print(f"\n  💾 Available checkpoints ({len(self.checkpoints)}):")
        for state in self.checkpoints[-10:]:
            print(f"    [{state.save_id}] tick:{state.tick:4d}  "
                  f"ALPHA:{state.alpha.score}  OMEGA:{state.omega.score}  "
                  f"Tension:{state.map_state.tension:.1f}")

    def rollback_to(self, tick: int) -> Optional[FullGameState]:
        candidates = [s for s in self.checkpoints if s.tick <= tick]
        if candidates:
            chosen = max(candidates, key=lambda s: s.tick)
            print(f"  ⏪ ROLLBACK to tick {chosen.tick} [{chosen.save_id}]")
            return chosen
        print(f"  ❌ No checkpoint at or before tick {tick}")
        return None


# ─────────────────────────────────────────────────────────────────────
#  2. EVENT BUS / PUB-SUB SYSTEM
# ─────────────────────────────────────────────────────────────────────

# All event types in the system
EVENT_TYPES = [
    "kill", "death", "capture", "boss_kill", "boss_spawn",
    "weather_change", "engagement", "total_war", "flare_fired",
    "barrier_broken", "hivemind_formed", "hivemind_broken",
    "level_up", "ultimate_used", "first_strike",
    "road_blocked", "road_restored", "tick",
    "game_start", "game_end", "player_joined", "player_left",
]

@dataclass
class GameEvent:
    event_type: str
    tick:       int
    timestamp:  str
    data:       Dict = field(default_factory=dict)
    source_id:  str  = ""

    def render(self) -> str:
        return (f"  📡 [{self.timestamp}] T{self.tick:03d} "
                f"[{self.event_type:<18}] src:{self.source_id:<18} "
                f"data:{self.data}")


class EventBus:
    """
    Central pub-sub event bus.
    All backends subscribe to relevant events.
    When an event fires, all subscribers are notified.
    """
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_queue: queue.Queue = queue.Queue()
        self.history:     List[GameEvent] = []
        self.tick_num:    int = 0
        self.stats:       Dict[str, int] = defaultdict(int)

    def subscribe(self, event_type: str, callback: Callable,
                  subscriber_name: str = ""):
        """Subscribe a callback to an event type. Use '*' for all events."""
        self.subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Callable):
        self.subscribers["*"].append(callback)

    def publish(self, event_type: str, source_id: str = "",
                tick: Optional[int] = None, **data):
        """Fire an event — immediately calls all subscribers."""
        ts  = datetime.now().strftime("%H:%M:%S.%f")[:12]
        evt = GameEvent(
            event_type = event_type,
            tick       = tick or self.tick_num,
            timestamp  = ts,
            data       = data,
            source_id  = source_id,
        )
        self.history.append(evt)
        self.stats[event_type] += 1

        # Notify direct subscribers
        for cb in self.subscribers.get(event_type, []):
            try:
                cb(evt)
            except Exception as e:
                print(f"  ⚠️  EventBus callback error [{event_type}]: {e}")

        # Notify wildcard subscribers
        for cb in self.subscribers.get("*", []):
            try:
                cb(evt)
            except Exception as e:
                print(f"  ⚠️  EventBus wildcard error: {e}")

        # Also enqueue for WebSocket feed
        self.event_queue.put(evt)
        return evt

    def advance_tick(self, tick: int):
        self.tick_num = tick
        self.publish("tick", "ENGINE", tick=tick)

    def get_events(self, event_type: str,
                   since_tick: int = 0) -> List[GameEvent]:
        return [e for e in self.history
                if e.event_type == event_type and e.tick >= since_tick]

    def render_stats(self):
        print(f"\n  ╔══ EVENT BUS STATS ══╗")
        print(f"  Total events fired: {len(self.history)}")
        for etype, count in sorted(self.stats.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * min(count, 30)
            print(f"  {etype:<22} {count:5d}  {bar}")

    def render_recent(self, n: int = 10, event_type: Optional[str] = None):
        events = self.history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        print(f"\n  ╔══ RECENT EVENTS {'('+event_type+')' if event_type else ''} ══╗")
        for evt in events[-n:]:
            print(evt.render())


# ─────────────────────────────────────────────────────────────────────
#  3. WEBSOCKET REAL-TIME FEED  (simulation layer)
# ─────────────────────────────────────────────────────────────────────

# Note: In production, replace with `websockets` or `fastapi` WebSocket.
# This module simulates the push feed with an async queue system.

@dataclass
class WsMessage:
    msg_type:  str    # "state_update"|"event"|"chat"|"alert"|"tick"
    payload:   Dict
    tick:      int
    timestamp: str
    channel:   str = "broadcast"  # broadcast|team_alpha|team_omega|spectator

    def to_json(self) -> str:
        return json.dumps({
            "type":      self.msg_type,
            "tick":      self.tick,
            "timestamp": self.timestamp,
            "channel":   self.channel,
            "payload":   self.payload,
        })

    def render(self) -> str:
        return (f"  📤 WS [{self.channel:<12}] T{self.tick:03d} "
                f"[{self.msg_type:<16}] "
                f"{str(self.payload)[:60]}...")


class WebSocketFeed:
    """
    Simulates a WebSocket server that pushes game events to clients.
    In production, connect to FastAPI/websockets library.
    Channels: broadcast (all), team_alpha, team_omega, spectator
    """
    def __init__(self, event_bus: EventBus):
        self.event_bus    = event_bus
        self.message_log: List[WsMessage] = []
        self.tick_num:    int = 0
        self.connected_clients: Dict[str, List[str]] = defaultdict(list)
        self.msg_seq:     int = 0
        self._setup_subscriptions()

    def _setup_subscriptions(self):
        """Wire event bus events to WebSocket push messages."""
        BROADCAST_EVENTS = {
            "kill", "capture", "boss_kill", "engagement",
            "total_war", "weather_change", "game_end"
        }
        ALPHA_ONLY_EVENTS  = {"flare_fired"}
        SPECTATOR_EVENTS   = {"level_up", "ultimate_used", "first_strike",
                              "hivemind_formed", "barrier_broken"}

        def on_broadcast_event(evt: GameEvent):
            self._push(evt.event_type, evt.data, evt.tick, "broadcast")

        def on_alpha_event(evt: GameEvent):
            if evt.data.get("team") == "ALPHA":
                self._push(evt.event_type, evt.data, evt.tick, "team_alpha")

        def on_spectator_event(evt: GameEvent):
            self._push(evt.event_type, evt.data, evt.tick, "spectator")

        def on_tick(evt: GameEvent):
            # Push minimal state update every tick
            self._push("tick_update", {"tick": evt.tick}, evt.tick, "broadcast")

        for ev in BROADCAST_EVENTS:
            self.event_bus.subscribe(ev, on_broadcast_event)
        for ev in ALPHA_ONLY_EVENTS:
            self.event_bus.subscribe(ev, on_alpha_event)
        for ev in SPECTATOR_EVENTS:
            self.event_bus.subscribe(ev, on_spectator_event)
        self.event_bus.subscribe("tick", on_tick)

    def _push(self, msg_type: str, payload: Dict,
              tick: int, channel: str):
        self.msg_seq += 1
        ts  = datetime.now().strftime("%H:%M:%S")
        msg = WsMessage(msg_type, payload, tick, ts, channel)
        self.message_log.append(msg)
        # In production: await websocket.send(msg.to_json())
        return msg

    def push_chat(self, sender: str, message: str,
                  channel: str = "broadcast"):
        self._push("chat", {"sender": sender, "message": message},
                   self.tick_num, channel)

    def push_alert(self, message: str, priority: int = 1,
                   channel: str = "broadcast"):
        self._push("alert", {"message": message, "priority": priority},
                   self.tick_num, channel)

    def push_state_snapshot(self, state_data: Dict,
                             channel: str = "broadcast"):
        self._push("state_update", state_data, self.tick_num, channel)

    def get_messages_for(self, channel: str,
                          since_tick: int = 0) -> List[WsMessage]:
        return [m for m in self.message_log
                if (m.channel == channel or m.channel == "broadcast")
                and m.tick >= since_tick]

    def render_message_log(self, channel: Optional[str] = None,
                            last_n: int = 20):
        msgs = self.message_log
        if channel:
            msgs = [m for m in msgs
                    if m.channel in (channel, "broadcast")]
        print(f"\n  ╔══ WEBSOCKET FEED {'['+channel+']' if channel else '[ALL]'} ══╗")
        print(f"  Total messages: {len(self.message_log)}  "
              f"Seq: {self.msg_seq}")
        for m in msgs[-last_n:]:
            print(m.render())

    def render_channel_stats(self):
        from collections import Counter
        channels = Counter(m.channel for m in self.message_log)
        msg_types = Counter(m.msg_type for m in self.message_log)
        print(f"\n  📊 WebSocket Channel Stats:")
        for ch, count in channels.most_common():
            print(f"    {ch:<15} {count:4d} messages")
        print(f"  📊 Message Types:")
        for mt, count in msg_types.most_common():
            print(f"    {mt:<20} {count:4d}")


# ─────────────────────────────────────────────────────────────────────
#  INFRASTRUCTURE ENGINE  (ties all three together)
# ─────────────────────────────────────────────────────────────────────

class InfrastructureEngine:
    def __init__(self):
        self.event_bus   = EventBus()
        self.ws_feed     = WebSocketFeed(self.event_bus)
        self.save_system = SaveLoadSystem(auto_save_interval=10)
        self.tick_num    = 0

    def tick(self, tick: int):
        self.tick_num      = tick
        self.ws_feed.tick_num = tick
        self.event_bus.advance_tick(tick)

    def fire(self, event_type: str, source_id: str = "", **data):
        return self.event_bus.publish(event_type, source_id, **data)

    def render_all(self):
        self.event_bus.render_stats()
        self.ws_feed.render_message_log(last_n=15)
        self.ws_feed.render_channel_stats()
        self.save_system.list_saves()


# ── Demo ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══ INFRASTRUCTURE ENGINE DEMO ══╗\n")
    infra = InfrastructureEngine()

    # Wire up example subscribers
    kill_log = []
    cap_log  = []
    infra.event_bus.subscribe("kill",
        lambda e: kill_log.append(f"KILL: {e.data}"))
    infra.event_bus.subscribe("capture",
        lambda e: cap_log.append(f"CAP: {e.data}"))

    print("  Running 20-tick simulation...\n")
    for t in range(1, 21):
        infra.tick(t)

        if t == 3:
            infra.fire("kill", "Ignis-Prime",
                       killer="Ignis-Prime", victim="Sylvan-Wraith",
                       damage=88.0, team="ALPHA")
        if t == 5:
            infra.fire("capture", "Volt-Surge",
                       agent="Volt-Surge", landmark="Clock_Tower", team="ALPHA")
        if t == 7:
            infra.fire("weather_change", "ENGINE",
                       weather="thunderstorm", affected=["Thunder","Water","Fire"])
        if t == 10:
            infra.fire("boss_kill", "AquaVex",
                       killer="AquaVex", boss="GM_Ironclad", team="ALPHA")
        if t == 12:
            infra.fire("engagement", "ENGINE",
                       team_a="ALPHA", team_b="OMEGA",
                       zone="Parliament_Core",
                       relay_code="[ENGAGE:ALPHA:OMEGA:Parliament_Core:012]")
        if t == 15:
            infra.fire("ultimate_used", "Volt-Surge",
                       agent="Volt-Surge", ultimate="Thunder God", targets=3)
        if t == 18:
            infra.fire("total_war", "ENGINE")
        if t == 20:
            infra.fire("game_end", "ENGINE",
                       winner="ALPHA", ticks=20)

        # Simulate auto-save
        if t % 10 == 0:
            dummy_state = infra.save_system.create_state(
                tick=t,
                alpha_data={
                    "score": t//2, "strategy":"Aggressive",
                    "agents":[
                        {"id":"Ignis-Prime","hp":200,"max_hp":280,
                         "pos":(100.0,100.0),"kills":2,"state":"ATTACK"},
                        {"id":"AquaVex","hp":280,"max_hp":320,
                         "pos":(95.0,105.0),"kills":0,"state":"SUPPORT"},
                    ]
                },
                omega_data={
                    "score": t//4, "strategy":"Defensive",
                    "agents":[
                        {"id":"Voidwalker","hp":180,"max_hp":290,
                         "pos":(110.0,95.0),"kills":1,"state":"RETREAT"},
                    ]
                },
                map_data={
                    "controlled_points":{"Parliament_Hall":"ALPHA","Clock_Tower":"ALPHA"},
                    "weather":"thunderstorm","day_phase":"day",
                    "game_hour":12,"blocked_roads":[],"tension":45.0
                }
            )
            infra.save_system.save(dummy_state)

        # Push chat via WS
        if t == 8:
            infra.ws_feed.push_chat("Ignis-Prime",
                                    "Did you SEE that?! FIRE WINS!", "team_alpha")
        if t == 10:
            infra.ws_feed.push_alert("⚡ Grand Master DEFEATED — bounty claimed!", 3)

    # Show results
    print(f"\n  Kill log captures: {len(kill_log)}")
    print(f"  Cap log captures:  {len(cap_log)}")
    for line in kill_log: print(f"    {line}")
    for line in cap_log:  print(f"    {line}")

    infra.render_all()
    print()
