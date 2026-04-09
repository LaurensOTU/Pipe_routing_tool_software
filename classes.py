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
class WalkingSpace:
    """
    Crew walkway / gangway.  Engineers mark the XY footprint; the height is
    always 0 → 2.1 m (head-clearance requirement).  Pipes may NOT enter this
    volume.
    """
    id: str
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    height: float = 2.1   # fixed: DNV / class requirement

@dataclass
class RoutingTray:
    """
    Dedicated pipe / cable tray.  Engineers define the full 3-D bounding box.
    The A* router treats the tray interior as an obstacle (pipes run alongside,
    not through) and gives a cost discount to cells immediately adjacent.
    """
    id: str
    name: str
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
    diameter: float = 0.1          # metres
    priority: int = 1              # 1 = routed first
    fluid_type: str = "General"    # "General" | "Fuel" | "Water" | "Electric"
    path: Optional[List[Position]] = field(default=None)

    # Populated by AStar.route_all() after routing
    avg_installability_score: float = 1.0   # 0.0 (impossible) → 1.0 (clear)
    avg_time_multiplier: float = 1.0         # 1.0 = baseline installation time