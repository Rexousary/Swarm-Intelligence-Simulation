# 🌐 Web-Based Swarm Intelligence Battle Game

Complete web implementation extending the core `Swarm engine.Py` with multiplayer, tournaments, and real-time gameplay.

---

## 📁 Project Structure

```
Swarm-Intelligence-Simulation/
├── Swarm engine.Py          # Core game engine (base classes)
├── web_arena.py              # WebBattleArena (extends BattleArena)
├── multiplayer_controller.py # MultiplayerController (extends PlayerController)
├── custom_agent.py           # CustomAgent (extends MetaAgent)
├── tournament_manager.py     # Tournament & matchmaking system
├── web_swarm_brain.py        # WebSwarmBrain (extends SwarmBrain)
├── web_server.py             # FastAPI server with WebSocket
├── client.html               # Browser-based game client
└── requirements.txt          # Python dependencies
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the Server

```bash
python web_server.py
```

Server runs on `http://localhost:8000`

### 3. Open Client

Open `client.html` in your browser or visit:
```
http://localhost:8000/docs  # API documentation
```

### 4. Play!

- Click "New Battle" to create a game
- Use WASD or Arrow keys to move
- Press 1, 2, 3 to use abilities
- Click ability buttons or use keyboard shortcuts

---

## 🏗️ Architecture Overview

### Inheritance Hierarchy

```
BattleArena
    └── WebBattleArena (adds WebSocket broadcasting, pause, spectator mode)

PlayerController
    └── MultiplayerController (adds validation, command queue, sessions)

MetaAgent
    └── CustomAgent (adds custom abilities, AI scripts, skins)

SwarmBrain
    └── WebSwarmBrain (adds custom strategies, learning, marketplace)
```

### New Components

**TournamentManager**: Matchmaking, brackets, leaderboards, replays  
**SessionManager**: Multi-player session handling  
**StrategyMarketplace**: Share and download community strategies

---

## 🎮 API Endpoints

### Battle Management
- `POST /battle/create` - Create new battle
- `GET /battle/{id}/state` - Get current state
- `POST /battle/{id}/pause` - Pause/resume
- `WS /battle/{id}/connect` - WebSocket connection

### Matchmaking
- `POST /matchmaking/join` - Join queue
- `GET /leaderboard` - Top players
- `GET /player/{id}/history` - Match history

### Strategy Marketplace
- `POST /strategy/upload` - Upload strategy
- `GET /strategy/top` - Top strategies
- `GET /strategy/{id}` - Download strategy

---

## 🔧 Extending the System

### Create Custom Agent

```python
from custom_agent import CustomAgent
from Swarm_engine import Element, Team, Ability

# Define custom abilities
custom_abilities = [
    Ability("Mega Blast", 100, 5, 150, 50, "Huge damage"),
    Ability("Shield Wall", 0, 8, 0, 0, "Block damage", {"shield": 80}),
    Ability("Speed Boost", 0, 3, 0, 0, "Move faster", {"speed": 2.0})
]

# Create agent with custom loadout
agent = CustomAgent("MyHero", Element.FIRE, Team.ALPHA, 100, 100, 
                   custom_abilities=custom_abilities)
```

### Define Custom AI Script

```python
def my_ai_logic(context):
    """Custom AI decision making."""
    if context["hp_pct"] < 0.3:
        return "retreat"
    elif len(context["enemies"]) > 2:
        return "defend"
    else:
        return "attack"

agent = CustomAgent("SmartBot", Element.WATER, Team.ALPHA, 100, 100,
                   ai_script=my_ai_logic)
```

### Register Custom Strategy

```python
from web_swarm_brain import WebSwarmBrain

brain = WebSwarmBrain(Team.ALPHA, agents)
brain.register_strategy("blitz", {
    "aggression": 1.0,
    "cohesion": 0.2,
    "formation": "wedge",
    "priority": "offensive"
})
brain.apply_strategy("blitz")
```

### Create Tournament

```python
from tournament_manager import BracketTournament

players = ["player1", "player2", "player3", "player4"]
tournament = BracketTournament("championship_2024", players)

# Advance winners
tournament.advance_winner("match_id", "player1")
```

---

## 🎯 WebSocket Message Format

### Client → Server

```json
{
  "type": "move",
  "dx": 1,
  "dy": 0
}

{
  "type": "ability",
  "ability_idx": 0,
  "target": "enemy_name"
}

{
  "type": "strategy",
  "strategy": "rush"
}
```

### Server → Client

```json
{
  "type": "game_state",
  "data": {
    "tick": 42,
    "alpha_agents": [...],
    "beta_agents": [...],
    "events": [...],
    "winner": null
  }
}
```

---

## 🔐 Security Features

- Command validation (rate limiting, bounds checking)
- Sandboxed AI script execution
- WebSocket connection management
- Input sanitization

---

## 🎨 Customization

### Add New Element

Edit `Swarm engine.Py`:
```python
class Element(Enum):
    CUSTOM = "custom"

ELEMENT_ABILITIES[Element.CUSTOM] = [...]
```

### Add New Map

```python
MAP_ZONES.append(
    MapZone("Custom_Zone", 400, 300, 80, 9, True, False)
)
```

---

## 📊 Performance

- 20 ticks per second (50ms per tick)
- Supports 100+ concurrent battles
- WebSocket auto-reconnect
- Efficient state serialization

---

## 🐛 Troubleshooting

**WebSocket won't connect:**
- Check server is running on port 8000
- Verify firewall settings
- Use `ws://` not `wss://` for local testing

**Agents not moving:**
- Ensure commands are validated
- Check tick rate in browser console
- Verify agent is alive

---

## 📝 License

MIT License - Extend freely!

---

**Built on top of MetaSwarm Engine** 🐝⚡
