from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Literal

@dataclass
class Room:
    length: float
    width: float
    height: float

@dataclass
class Position:
    x: float
    y: float
    z: float

@dataclass
class Machinery:
    id: str
    name: str
    length: float
    width: float
    height: float
    machine_type: Literal["General", "Switchboard", "Hot Surface"] = "General"
    constraint: Literal["free", "wall", "floor"] = "free"
    position: Optional[Position] = None
    # For GA: fixed position or not
    is_locked: bool = False

@dataclass
class NoGoZone:
    id: str
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

@dataclass
class Pipe:
    id: str
    name: str
    start: Position
    end: Position
    diameter: float
    priority: int  # 1 is highest priority
    fluid_type: Literal["General", "Fuel", "Water", "Electric"] = "General"
    path: Optional[List[Position]] = None
    # Fuzzy installability metrics — populated after routing
    avg_installability_score: float = 1.0   # 0.0 (impossible) → 1.0 (clear)
    avg_time_multiplier: float = 1.0         # 1.0 = baseline install time
