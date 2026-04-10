"""
algorithms.py
-------------
A* pipe routing algorithm with integrated fuzzy installability penalty.

The Genetic Algorithm machinery placement has been removed — engineers
now place machinery manually via the Streamlit UI.

Key addition: before routing, a clearance map is pre-computed across the
3-D grid. Each cell's clearance (mm to nearest obstacle) is fuzzified to
produce an installability penalty, which is added to the A* move cost.
This guides the router to prefer paths through more accessible space.
"""

from classes import Room, Machinery, Pipe, NoGoZone, Position, WalkingSpace, RoutingTray
from fuzzy_installability import FuzzyInstallability
from typing import List, Optional, Tuple, Set
import math
import heapq
import numpy as np


class AStar:
    """
    3-D A* pipe router with fuzzy installability cost penalty.

    Parameters
    ----------
    room              : Room — engine room dimensions
    machinery_list    : List[Machinery] — placed machines (obstacles)
    no_go_zones       : List[NoGoZone] — hard forbidden regions
    walking_spaces    : List[WalkingSpace] — crew walkways (pipes forbidden 0→2.1 m)
    routing_trays     : List[RoutingTray] — preferred tray zones (cost discount)
    fuzzy             : FuzzyInstallability — pre-built fuzzy module (optional)
    grid_resolution   : float — cell size in metres (default 0.1 m for pathfinding)
    w_dist            : float — base movement cost weight
    w_bend            : float — penalty per direction change
    w_vertical        : float — penalty per vertical step
    w_installability  : float — penalty weight for poor installability
                        0.0 = pure shortest path, >0 = prefer accessible routes
    w_parallel        : float — cost discount per step next to an existing pipe
                        0.0 = no preference, >0 = prefer bundling pipes
    """

    def __init__(
        self,
        room: Room,
        machinery_list: List[Machinery],
        no_go_zones: List[NoGoZone],
        walking_spaces: List[WalkingSpace] = None,
        routing_trays: List[RoutingTray] = None,
        fuzzy: FuzzyInstallability = None,
        grid_resolution: float = 0.1,
        w_dist: float = 1.0,
        w_bend: float = 2.0,
        w_vertical: float = 1.5,
        w_installability: float = 0.0,
        w_parallel: float = 0.5,
        w_suction: float = 2.0,
    ):
        self.room             = room
        self.machinery_list   = machinery_list
        self.no_go_zones      = no_go_zones
        self.walking_spaces   = walking_spaces or []
        self.routing_trays    = routing_trays or []
        self.fuzzy            = fuzzy
        self.grid_resolution  = grid_resolution
        self.w_dist           = w_dist
        self.w_bend           = w_bend
        self.w_vertical       = w_vertical
        self.w_installability = w_installability
        self.w_parallel       = w_parallel
        self.w_suction        = w_suction

        # Offset for the 0.5m space below the engine room (z_min = -0.5)
        self.z_min_world = -0.5

        # Build static obstacle set (machinery + no-go zones + walking spaces + trays)
        self.obstacles: Set[Tuple[int, int, int]] = set()
        self._mark_obstacles()

        # Pre-compute clearance map if fuzzy penalty is active
        self.clearance_map: Optional[np.ndarray] = None
        if self.w_installability > 0 and self.fuzzy is not None:
            self._build_clearance_map()

    # ------------------------------------------------------------------
    # Grid utilities
    # ------------------------------------------------------------------

    def _to_grid(self, val: float, axis: str = "x") -> int:
        if axis == "z":
            return int(round((val - self.z_min_world) / self.grid_resolution))
        return int(round(val / self.grid_resolution))

    def _to_world(self, val: int, axis: str = "x") -> float:
        if axis == "z":
            return val * self.grid_resolution + self.z_min_world
        return val * self.grid_resolution

    # ------------------------------------------------------------------
    # Obstacle marking
    # ------------------------------------------------------------------

    def _mark_obstacles(self):
        """Fill obstacle set from machinery, no-go zones, walking spaces, and routing trays."""
        for m in self.machinery_list:
            if m.position:
                self._fill_box(
                    m.position.x, m.position.y, m.position.z,
                    m.position.x + m.length,
                    m.position.y + m.width,
                    m.position.z + m.height,
                )
        for z in self.no_go_zones:
            self._fill_box(z.x_min, z.y_min, z.z_min,
                           z.x_max, z.y_max, z.z_max)
        for w in self.walking_spaces:
            self._fill_box(w.x_min, w.y_min, 0.0,
                           w.x_max, w.y_max, w.height)
        for t in self.routing_trays:
            self._fill_box(t.x_min, t.y_min, t.z_min,
                           t.x_max, t.y_max, t.z_max)

    def _fill_box(self, xmin, ymin, zmin, xmax, ymax, zmax):
        for x in range(self._to_grid(xmin, "x"), self._to_grid(xmax, "x") + 1):
            for y in range(self._to_grid(ymin, "y"), self._to_grid(ymax, "y") + 1):
                for z in range(self._to_grid(zmin, "z"), self._to_grid(zmax, "z") + 1):
                    self.obstacles.add((x, y, z))

    # ------------------------------------------------------------------
    # Clearance map (BFS-based, no scipy required)
    # ------------------------------------------------------------------

    def _build_clearance_map(self):
        """
        Compute minimum Euclidean distance (in mm) from every free grid cell
        to the nearest obstacle cell, using a multi-source BFS.

        Result stored in self.clearance_map[gx, gy, gz] as float (mm).
        Cells that ARE obstacles get clearance = 0.
        """
        gx_max = self._to_grid(self.room.length, "x") + 1
        gy_max = self._to_grid(self.room.width, "y") + 1
        gz_max = self._to_grid(self.room.height, "z") + 1

        # Distance in grid cells (initialise to infinity for free cells)
        dist = np.full((gx_max, gy_max, gz_max), np.inf, dtype=float)

        # Seed: all obstacle cells start at distance 0
        from collections import deque
        queue = deque()
        for (ox, oy, oz) in self.obstacles:
            if 0 <= ox < gx_max and 0 <= oy < gy_max and 0 <= oz < gz_max:
                if dist[ox, oy, oz] == np.inf:
                    dist[ox, oy, oz] = 0.0
                    queue.append((ox, oy, oz))

        # Also seed boundary walls (treat room edge as distance 0)
        for gx in range(gx_max):
            for gy in range(gy_max):
                for gz in range(gz_max):
                    is_wall = (gx == 0 or gx == gx_max - 1 or
                               gy == 0 or gy == gy_max - 1 or
                               gz == 0 or gz == gz_max - 1)
                    if is_wall and dist[gx, gy, gz] == np.inf:
                        dist[gx, gy, gz] = 0.0
                        queue.append((gx, gy, gz))

        # BFS wavefront propagation (uses Chebyshev distance for speed)
        # For true Euclidean we do a simple BFS with 26-connectivity
        dirs26 = [
            (dx, dy, dz)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for dz in (-1, 0, 1)
            if not (dx == 0 and dy == 0 and dz == 0)
        ]
        step_dist = {(dx, dy, dz): math.sqrt(dx**2 + dy**2 + dz**2)
                     for (dx, dy, dz) in dirs26}

        while queue:
            cx, cy, cz = queue.popleft()
            cd = dist[cx, cy, cz]
            for (dx, dy, dz) in dirs26:
                nx, ny, nz = cx + dx, cy + dy, cz + dz
                if 0 <= nx < gx_max and 0 <= ny < gy_max and 0 <= nz < gz_max:
                    nd = cd + step_dist[(dx, dy, dz)]
                    if nd < dist[nx, ny, nz]:
                        dist[nx, ny, nz] = nd
                        queue.append((nx, ny, nz))

        # Convert grid-cell distance to mm
        self.clearance_map = dist * self.grid_resolution * 1000.0
        print(f"[AStar] Clearance map built: {gx_max}×{gy_max}×{gz_max} cells, "
              f"max clearance = {self.clearance_map[self.clearance_map < 1e8].max():.0f} mm")

    # ------------------------------------------------------------------
    # Fuzzy installability cost
    # ------------------------------------------------------------------

    def _installability_cost(self, cell: Tuple[int, int, int],
                              pipe_radius_mm: float) -> float:
        """
        Return the installability penalty for moving through this cell.
        Returns 0.0 if fuzzy scoring is disabled.
        """
        if self.clearance_map is None or self.fuzzy is None:
            return 0.0

        gx, gy, gz = cell
        shape = self.clearance_map.shape
        if not (0 <= gx < shape[0] and 0 <= gy < shape[1] and 0 <= gz < shape[2]):
            return self.w_installability  # treat out-of-bounds as worst case

        raw_clearance_mm    = self.clearance_map[gx, gy, gz]
        effective_clearance = max(50.0, raw_clearance_mm - pipe_radius_mm)
        _, _, inst_score    = self.fuzzy.get_score(effective_clearance)

        # Penalty: (1 - score) ranges 1.0 (impossible) → 0.0 (clear)
        return self.w_installability * (1.0 - inst_score)

    # ------------------------------------------------------------------
    # A* core
    # ------------------------------------------------------------------

    def _heuristic(self, node: Tuple[int, int, int],
                   goal: Tuple[int, int, int]) -> float:
        """Manhattan distance heuristic."""
        return (abs(node[0] - goal[0]) +
                abs(node[1] - goal[1]) +
                abs(node[2] - goal[2]))

    def find_path(self, pipe: Pipe,
                  already_routed: List[Pipe]) -> Tuple[Optional[List[Position]], str]:
        """
        Find the optimal path for one pipe using A*.
        Returns (path, status_message).
        """
        start = (self._to_grid(pipe.start.x, "x"),
                 self._to_grid(pipe.start.y, "y"),
                 self._to_grid(pipe.start.z, "z"))
        goal  = (self._to_grid(pipe.end.x, "x"),
                 self._to_grid(pipe.end.y, "y"),
                 self._to_grid(pipe.end.z, "z"))

        # Copy static obstacles, then add previously routed pipe paths
        current_obs = self.obstacles.copy()
        parallel_friendly: Set[Tuple[int, int, int]] = set()
        
        for p in already_routed:
            if p.path:
                for pos in p.path:
                    pg = (self._to_grid(pos.x, "x"),
                          self._to_grid(pos.y, "y"),
                          self._to_grid(pos.z, "z"))
                    current_obs.add(pg)
                    # Mark neighbors as bundling-friendly
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            for dz in [-1, 0, 1]:
                                if dx == 0 and dy == 0 and dz == 0: continue
                                nb_bundle = (pg[0]+dx, pg[1]+dy, pg[2]+dz)
                                parallel_friendly.add(nb_bundle)

        # Check if start or end are strictly blocked (but allow if they are on the very edge)
        # We handle this by removing start/goal from current_obs for THIS pipe's search.
        if start in current_obs:
            current_obs.remove(start)
        if goal in current_obs:
            current_obs.remove(goal)

        # Grid bounds
        max_gx = self._to_grid(self.room.length, "x")
        max_gy = self._to_grid(self.room.width, "y")
        max_gz = self._to_grid(self.room.height, "z")

        pipe_radius_mm = (pipe.diameter / 2.0) * 1000.0  # diameter in m → radius in mm

        # 6-connected directions
        directions = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]

        # Priority queue: (f_score, tie_break, g_score, node, path, last_dir)
        counter = 0
        pq = [(0, counter, 0, start, [start], (0, 0, 0))]
        visited: dict = {start: 0.0}

        while pq:
            f, _, g, current, path, last_dir = heapq.heappop(pq)

            if current == goal:
                world_path = [Position(self._to_world(n[0], "x"),
                                      self._to_world(n[1], "y"),
                                      self._to_world(n[2], "z"))
                             for n in path]
                return world_path, "Success"

            if g > visited.get(current, math.inf):
                continue

            for dx, dy, dz in directions:
                nb = (current[0]+dx, current[1]+dy, current[2]+dz)

                # Bounds check
                if not (0 <= nb[0] <= max_gx and
                        0 <= nb[1] <= max_gy and
                        0 <= nb[2] <= max_gz):
                    continue

                # Obstacle check
                if nb in current_obs:
                    continue

                # --- Cost components ---
                move_cost = self.w_dist

                # Bend penalty
                new_dir = (dx, dy, dz)
                if last_dir != (0, 0, 0) and new_dir != last_dir:
                    move_cost += self.w_bend

                # Vertical penalty
                if dz != 0:
                    move_cost += self.w_vertical

                # Suction penalty: favor lower z
                if pipe.suction_type == "Suction":
                    height_penalty = (nb[2]) * self.w_suction 
                    move_cost += height_penalty

                # Fuzzy installability penalty
                move_cost += self._installability_cost(nb, pipe_radius_mm)

                # Parallel bundling discount (makes cells next to other pipes cheaper)
                if nb in parallel_friendly:
                    move_cost = max(0.1, move_cost - self.w_parallel)

                new_g = g + move_cost
                if new_g < visited.get(nb, math.inf):
                    visited[nb] = new_g
                    h = self._heuristic(nb, goal)
                    counter += 1
                    heapq.heappush(
                        pq,
                        (new_g + h, counter, new_g, nb, path + [nb], new_dir),
                    )

        return None, "No path found (Insufficient space)"

    # ------------------------------------------------------------------
    # Route all pipes
    # ------------------------------------------------------------------

    def route_all(self, pipes: List[Pipe]) -> List[Pipe]:
        """
        Route every pipe in priority order (priority 1 = first).
        """
        sorted_pipes = sorted(pipes, key=lambda p: p.priority)
        routed: List[Pipe] = []

        for pipe in sorted_pipes:
            path, status = self.find_path(pipe, routed)
            pipe.path = path
            pipe.routing_status = status

            # Compute per-path installability averages when fuzzy is active
            if path and self.fuzzy is not None and self.clearance_map is not None:
                pipe_radius_mm = (pipe.diameter / 2.0) * 1000.0
                scores: List[float] = []
                multipliers: List[float] = []
                for pos in path:
                    gx = self._to_grid(pos.x, "x")
                    gy = self._to_grid(pos.y, "y")
                    gz = self._to_grid(pos.z, "z")
                    shape = self.clearance_map.shape
                    if (0 <= gx < shape[0] and
                            0 <= gy < shape[1] and
                            0 <= gz < shape[2]):
                        raw_cl = float(self.clearance_map[gx, gy, gz])
                        eff_cl = max(50.0, raw_cl - pipe_radius_mm)
                        _, mult, score = self.fuzzy.get_score(eff_cl)
                        scores.append(score)
                        multipliers.append(mult)
                if scores:
                    pipe.avg_installability_score = round(
                        sum(scores) / len(scores), 3)
                    pipe.avg_time_multiplier = round(
                        sum(multipliers) / len(multipliers), 3)

            routed.append(pipe)

        return routed