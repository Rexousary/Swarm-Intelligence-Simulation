"""
Example: Using all inherited classes together
Demonstrates the full web-based game architecture
"""
import asyncio
from web_arena import WebBattleArena
from multiplayer_controller import MultiplayerController, SessionManager
from custom_agent import CustomAgent, AgentLoadout
from tournament_manager import TournamentManager, BracketTournament
from web_swarm_brain import WebSwarmBrain, StrategyMarketplace
from Swarm_engine import Element, Team, Ability

def example_custom_agent():
    """Example: Create custom agent with unique abilities."""
    print("\n=== Custom Agent Example ===")
    
    # Define custom abilities
    custom_abilities = [
        Ability("Plasma Cannon", 85, 4, 160, 40, "High damage AoE"),
        Ability("Force Field", 0, 6, 0, 0, "Absorb 60 damage", {"shield": 60}),
        Ability("Warp Strike", 50, 3, 200, 0, "Teleport attack", {"speed": 2.5})
    ]
    
    # Create custom agent
    agent = CustomAgent("Nexus", Element.THUNDER, Team.ALPHA, 100, 100,
                       custom_abilities=custom_abilities)
    agent.set_skin("cyber_ninja")
    
    print(f"Created: {agent.name} with {len(agent.abilities)} custom abilities")
    print(f"Skin: {agent.cosmetic_skin}")
    return agent

def example_custom_strategy():
    """Example: Register and use custom strategies."""
    print("\n=== Custom Strategy Example ===")
    
    arena = WebBattleArena("demo_battle", num_mobs=10)
    brain = WebSwarmBrain(Team.ALPHA, arena.alpha)
    
    # Register custom strategies
    brain.register_strategy("guerrilla", {
        "aggression": 0.7,
        "cohesion": 0.3,
        "formation": "spread",
        "priority": "offensive"
    })
    
    brain.register_strategy("turtle", {
        "aggression": 0.1,
        "cohesion": 0.9,
        "formation": "fortify",
        "priority": "defensive"
    })
    
    # Apply strategy
    brain.apply_strategy("guerrilla")
    print(f"Applied strategy: guerrilla")
    print(f"Formation: {brain.formation}")
    
    # Enable adaptive learning
    brain.learning_enabled = True
    brain.adaptive_strategy_switch()
    print("Adaptive learning enabled")

def example_tournament():
    """Example: Create and manage tournament."""
    print("\n=== Tournament Example ===")
    
    manager = TournamentManager()
    
    # Add players to queue
    players = ["Alice", "Bob", "Charlie", "Diana"]
    for player in players:
        manager.add_to_queue(player)
    
    # Create matches
    match1 = manager.create_match()
    match2 = manager.create_match()
    
    if match1:
        print(f"Match 1: {match1.player1} vs {match1.player2}")
        # Simulate match completion
        manager.complete_match(match1.match_id, match1.player1, (100, 75), {})
    
    if match2:
        print(f"Match 2: {match2.player1} vs {match2.player2}")
        manager.complete_match(match2.match_id, match2.player2, (90, 85), {})
    
    # Show leaderboard
    leaderboard = manager.get_leaderboard(5)
    print("\nLeaderboard:")
    for entry in leaderboard:
        print(f"  {entry['player']}: {entry['rating']} pts ({entry['wins']}W-{entry['losses']}L)")

def example_bracket_tournament():
    """Example: Single elimination bracket."""
    print("\n=== Bracket Tournament Example ===")
    
    players = ["Player1", "Player2", "Player3", "Player4", 
               "Player5", "Player6", "Player7", "Player8"]
    
    tournament = BracketTournament("summer_championship", players)
    
    print(f"Tournament: {tournament.tournament_id}")
    print(f"Round 1 matches: {len(tournament.rounds[0])}")
    
    # Simulate round 1
    for match in tournament.rounds[0]:
        winner = match.player1  # Simplified
        tournament.advance_winner(match.match_id, winner)
        print(f"  {match.player1} vs {match.player2} → Winner: {winner}")
    
    if tournament.winner:
        print(f"\nTournament Winner: {tournament.winner}")

def example_strategy_marketplace():
    """Example: Share strategies in marketplace."""
    print("\n=== Strategy Marketplace Example ===")
    
    marketplace = StrategyMarketplace()
    
    # Upload strategies
    marketplace.upload_strategy("ProGamer", "rush_meta", {
        "aggression": 0.95,
        "cohesion": 0.25,
        "formation": "wedge"
    })
    
    marketplace.upload_strategy("Tactician", "defensive_wall", {
        "aggression": 0.15,
        "cohesion": 0.85,
        "formation": "fortify"
    })
    
    # Rate strategies
    marketplace.rate_strategy("ProGamer_rush_meta", 5)
    marketplace.rate_strategy("ProGamer_rush_meta", 4)
    marketplace.rate_strategy("Tactician_defensive_wall", 5)
    
    # Download strategy
    config = marketplace.download_strategy("ProGamer_rush_meta")
    print(f"Downloaded strategy: {config}")
    
    # Show top strategies
    top = marketplace.get_top_strategies(3)
    print("\nTop Strategies:")
    for strat in top:
        print(f"  {strat['name']} by {strat['author']} - ⭐{strat['rating']:.1f} ({strat['downloads']} downloads)")

def example_loadout_system():
    """Example: Save and load agent loadouts."""
    print("\n=== Loadout System Example ===")
    
    loadout_manager = AgentLoadout()
    
    # Create loadouts
    assassin_loadout = [
        Ability("Shadow Strike", 75, 3, 140, 0, "Stealth attack"),
        Ability("Smoke Bomb", 0, 5, 0, 60, "Escape tool", {"stealth": 4}),
        Ability("Backstab", 120, 8, 80, 0, "Critical hit")
    ]
    
    tank_loadout = [
        Ability("Shield Bash", 40, 2, 100, 30, "Stun enemies"),
        Ability("Iron Wall", 0, 10, 0, 0, "Massive defense", {"defense": 100}),
        Ability("Taunt", 10, 4, 150, 80, "Force aggro")
    ]
    
    # Save loadouts
    loadout_manager.save_loadout("assassin_build", assassin_loadout)
    loadout_manager.save_loadout("tank_build", tank_loadout)
    
    # List and load
    print(f"Available loadouts: {loadout_manager.list_loadouts()}")
    
    loaded = loadout_manager.get_loadout("assassin_build")
    print(f"Loaded assassin build: {[ab.name for ab in loaded]}")

async def example_web_battle():
    """Example: Run a web-enabled battle."""
    print("\n=== Web Battle Example ===")
    
    # Create web arena
    arena = WebBattleArena("example_001", num_mobs=15)
    print(f"Battle ID: {arena.battle_id}")
    
    # Create session manager
    session_mgr = SessionManager()
    
    # Create player sessions
    player1 = session_mgr.create_session(arena, "player_1", arena.alpha[0])
    player2 = session_mgr.create_session(arena, "player_2", arena.alpha[1])
    
    print(f"Player 1 controls: {player1.player.name}")
    print(f"Player 2 controls: {player2.player.name}")
    
    # Simulate some commands
    cmd1 = {"type": "move", "dx": 1, "dy": 0}
    cmd2 = {"type": "ability", "ability_idx": 0, "target": "Verdant"}
    
    result1 = player1.execute_command(cmd1)
    result2 = player2.execute_command(cmd2)
    
    print(f"Command results: {result1}, {result2}")
    
    # Run a few ticks
    for _ in range(5):
        state = arena.tick_battle()
        print(f"Tick {state['tick']}: Alpha={state['alpha_score']}, Beta={state['beta_score']}")
        await asyncio.sleep(0.1)

def main():
    """Run all examples."""
    print("=" * 60)
    print("  Swarm Intelligence Web Game - Examples")
    print("=" * 60)
    
    example_custom_agent()
    example_custom_strategy()
    example_tournament()
    example_bracket_tournament()
    example_strategy_marketplace()
    example_loadout_system()
    
    # Async example
    print("\nRunning async web battle example...")
    asyncio.run(example_web_battle())
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()
