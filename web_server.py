"""
FastAPI Web Server - Real-time battle server
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional
import asyncio
import uuid

from web_arena import WebBattleArena
from multiplayer_controller import MultiplayerController, SessionManager
from tournament_manager import TournamentManager
from web_swarm_brain import StrategyMarketplace

app = FastAPI(title="Swarm Intelligence Battle API")

# CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global managers
active_battles: Dict[str, WebBattleArena] = {}
session_manager = SessionManager()
tournament_manager = TournamentManager()
strategy_marketplace = StrategyMarketplace()

@app.post("/battle/create")
async def create_battle(num_mobs: int = 12):
    """Create new battle arena."""
    battle_id = str(uuid.uuid4())
    arena = WebBattleArena(battle_id, num_mobs)
    active_battles[battle_id] = arena
    return {"battle_id": battle_id, "status": "created"}

@app.get("/battle/{battle_id}/state")
async def get_battle_state(battle_id: str):
    """Get current battle state."""
    arena = active_battles.get(battle_id)
    if not arena:
        raise HTTPException(status_code=404, detail="Battle not found")
    return arena.tick_battle()

@app.post("/battle/{battle_id}/pause")
async def toggle_pause(battle_id: str):
    """Pause/resume battle."""
    arena = active_battles.get(battle_id)
    if not arena:
        raise HTTPException(status_code=404, detail="Battle not found")
    paused = arena.toggle_pause()
    return {"paused": paused}

@app.websocket("/battle/{battle_id}/connect")
async def battle_websocket(websocket: WebSocket, battle_id: str):
    """WebSocket endpoint for real-time battle updates."""
    await websocket.accept()
    
    arena = active_battles.get(battle_id)
    if not arena:
        await websocket.send_json({"error": "Battle not found"})
        await websocket.close()
        return
    
    arena.add_client(websocket)
    player_id = str(uuid.uuid4())
    
    # Assign player to agent
    player_agent = next((a for a in arena.alpha if a.is_player), arena.alpha[0])
    controller = session_manager.create_session(arena, player_id, player_agent)
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "player_id": player_id,
            "agent": player_agent.to_dict()
        })
        
        # Game loop
        while not arena.winner:
            # Receive player commands
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                result = controller.execute_command(data)
                await websocket.send_json({"type": "command_result", "data": result})
            except asyncio.TimeoutError:
                pass
            
            # Tick battle
            state = arena.tick_battle()
            await arena.broadcast_state(state)
            await asyncio.sleep(0.05)  # 20 ticks per second
        
        # Send final state
        await websocket.send_json({"type": "battle_end", "winner": arena.winner})
        
    except WebSocketDisconnect:
        arena.remove_client(websocket)
        session_manager.remove_session(player_id)

@app.post("/matchmaking/join")
async def join_queue(player_id: str):
    """Join matchmaking queue."""
    tournament_manager.add_to_queue(player_id)
    match = tournament_manager.create_match()
    if match:
        return {"status": "matched", "match": match.to_dict()}
    return {"status": "queued", "position": len(tournament_manager.queue)}

@app.get("/leaderboard")
async def get_leaderboard(limit: int = 10):
    """Get top players."""
    return tournament_manager.get_leaderboard(limit)

@app.get("/player/{player_id}/history")
async def get_match_history(player_id: str):
    """Get player match history."""
    return tournament_manager.get_match_history(player_id)

@app.post("/strategy/upload")
async def upload_strategy(author: str, name: str, config: Dict):
    """Upload strategy to marketplace."""
    strategy_marketplace.upload_strategy(author, name, config)
    return {"status": "uploaded", "strategy": f"{author}_{name}"}

@app.get("/strategy/top")
async def get_top_strategies(limit: int = 10):
    """Get top strategies."""
    return strategy_marketplace.get_top_strategies(limit)

@app.get("/strategy/{strategy_id}")
async def download_strategy(strategy_id: str):
    """Download strategy."""
    config = strategy_marketplace.download_strategy(strategy_id)
    if not config:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return config

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000)
