"""
╔══════════════════════════════════════════════════════════════════════════╗
║   SHARED CONSTANTS — Metahuman Swarm Battle Engine                      ║
║   Imported by all backend modules                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import math
from typing import Tuple, Dict, List

MAP_W = 200
MAP_H = 200

LANDMARKS: Dict[str, Tuple[float, float]] = {
    "Parliament_Hall":  (100, 100), "Clock_Tower":      (100,  60),
    "North_Stadium":    (100,  30), "South_Stadium":    (100, 170),
    "East_Tower":       (160, 100), "West_Tower":       ( 40, 100),
    "North_Shore":      ( 50,  10), "South_Shore":      (150, 190),
    "Battle_Ground_A":  ( 60,  60), "Battle_Ground_B":  (140, 140),
    "Road_Junction_N":  (100,  75), "Road_Junction_S":  (100, 125),
    "Road_Junction_E":  (130, 100), "Road_Junction_W":  ( 70, 100),
    "Alpha_Spawn":      ( 22,  22), "Omega_Spawn":      (178, 178),
}

KEY_POINTS = ["Parliament_Hall","Clock_Tower","North_Stadium",
              "South_Stadium","East_Tower","West_Tower"]

ALPHA_AGENTS = ["Ignis-Prime","AquaVex","Volt-Surge","TerraKnight"]
OMEGA_AGENTS = ["Sylvan-Wraith","DustSerpent","ZephyrBlade","Voidwalker"]

ELEMENT_OF = {
    "Ignis-Prime":"Fire",   "AquaVex":"Water",
    "Volt-Surge":"Thunder", "TerraKnight":"Earth",
    "Sylvan-Wraith":"Grass","DustSerpent":"Sand",
    "ZephyrBlade":"Flying", "Voidwalker":"Dark",
}

TEAM_OF = {a:"ALPHA" for a in ALPHA_AGENTS} | {a:"OMEGA" for a in OMEGA_AGENTS}
SPAWN_OF = {"ALPHA": (22.0,22.0), "OMEGA": (178.0,178.0)}

def dist(a,b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2)
def clamp(p):  return (max(0.0,min(float(MAP_W),p[0])),max(0.0,min(float(MAP_H),p[1])))
def midpoint(pts):
    if not pts: return (100.0,100.0)
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))
def nearest_landmark(pos):
    return min(LANDMARKS.keys(), key=lambda k: dist(pos, LANDMARKS[k]))
def hp_bar(val, mx, w=14):
    f = round((val/mx)*w) if mx else 0
    return "█"*f + "░"*(w-f)
