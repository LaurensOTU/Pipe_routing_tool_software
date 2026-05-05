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

# ---------------------------------------------------------------------------
# Pipe content type sets — used for class rule enforcement
# ---------------------------------------------------------------------------
# All content types that carry liquid (switchboard exclusion applies)
LIQUID_CONTENTS: frozenset = frozenset([
    "General Fluid", "Fuel / Flammable Oil", "HP Fuel (Injection)",
    "Lubricating Oil", "Seawater / Ballast", "Bilge", "Freshwater / Cooling",
])
# Flammable liquid types (hot surface 500 mm buffer applies)
FLAMMABLE_CONTENTS: frozenset = frozenset([
    "Fuel / Flammable Oil", "HP Fuel (Injection)", "Lubricating Oil",
])


class PrecomputedGrid:
    """
    Cached BFS clearance map and static obstacle set for a fixed room layout.

    Build once with AStar.build_precomputed_grid() after the room and machinery
    are finalised. Pass as precomputed_grid= to AStar.__init__() to skip the
    expensive BFS on every subsequent routing call — only the A* search runs.

    The grid is invalidated whenever the room geometry, machinery positions,
    no-go zones, walking spaces, or routing trays change.
    """

    def __init__(
        self,
        obstacles: set,
        obstacle_grid: np.ndarray,
        clearance_map: np.ndarray,
        grid_resolution: float,
        layout_hash: str,
    ):
        self.obstacles       = obstacles
        self.obstacle_grid   = obstacle_grid
        self.clearance_map   = clearance_map
        self.grid_resolution = grid_resolution
        self.layout_hash     = layout_hash


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
        w_wall_ceiling: float = 0.0,
        precomputed_grid: "PrecomputedGrid" = None,
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
        self.w_wall_ceiling   = w_wall_ceiling

        # Offset for the 0.5m space below the engine room (z_min = -0.5)
        self.z_min_world = -0.5

        if precomputed_grid is not None:
            self.obstacles     = precomputed_grid.obstacles
            self.obstacle_grid = precomputed_grid.obstacle_grid
            self.clearance_map = precomputed_grid.clearance_map
            print("[AStar] Using precomputed grid — BFS skipped.")
        else:
            gx_max = self._to_grid(self.room.length, "x") + 1
            gy_max = self._to_grid(self.room.width, "y") + 1
            gz_max = self._to_grid(self.room.height, "z") + 1
            self.obstacle_grid = np.zeros((gx_max, gy_max, gz_max), dtype=bool)
            self.obstacles: Set[Tuple[int, int, int]] = set()
            self._mark_obstacles()

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
        x0, x1 = self._to_grid(xmin, "x"), self._to_grid(xmax, "x")
        y0, y1 = self._to_grid(ymin, "y"), self._to_grid(ymax, "y")
        z0, z1 = self._to_grid(zmin, "z"), self._to_grid(zmax, "z")
        
        # Clamp to grid bounds
        x0, x1 = max(0, x0), min(self.obstacle_grid.shape[0] - 1, x1)
        y0, y1 = max(0, y0), min(self.obstacle_grid.shape[1] - 1, y1)
        z0, z1 = max(0, z0), min(self.obstacle_grid.shape[2] - 1, z1)

        self.obstacle_grid[x0:x1+1, y0:y1+1, z0:z1+1] = True
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
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
        gx_max, gy_max, gz_max = self.obstacle_grid.shape

        # Distance in grid cells (initialise to infinity for free cells)
        dist = np.full((gx_max, gy_max, gz_max), np.inf, dtype=float)

        # Seed: all obstacle cells start at distance 0
        from collections import deque
        queue = deque()
        
        # Use numpy to find all obstacle indices (much faster than iterating)
        ox, oy, oz = np.where(self.obstacle_grid)
        for i in range(len(ox)):
            dist[ox[i], oy[i], oz[i]] = 0.0
            queue.append((ox[i], oy[i], oz[i]))

        # BFS wavefront propagation (uses Chebyshev distance for speed)
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

    def _get_penalty_grid(self, pipe_radius_mm: float) -> np.ndarray:
        """Pre-calculate the fuzzy penalty for every cell in the grid."""
        if self.clearance_map is None or self.fuzzy is None or self.w_installability == 0:
            return np.zeros(self.obstacle_grid.shape, dtype=float)
        
        # Vectorized calculation
        eff_cl = np.maximum(50.0, self.clearance_map - pipe_radius_mm)
        inst_scores = self.fuzzy.get_score_vectorized(eff_cl)
        return self.w_installability * (1.0 - inst_scores)

    # ------------------------------------------------------------------
    # Class rule enforcement — per-pipe obstacle additions
    # ------------------------------------------------------------------

    def _apply_class_rules_to_grid(
        self, pipe: Pipe, already_routed: List[Pipe], obs_grid: np.ndarray
    ):
        """Apply class rules directly to the obstacle grid."""
        content = getattr(pipe, "pipe_content", "General Fluid")
        max_gx, max_gy, max_gz = [s - 1 for s in obs_grid.shape]

        # Rule 1 — Switchboard
        if content in LIQUID_CONTENTS:
            for m in self.machinery_list:
                if m.machine_type == "Switchboard" and m.position:
                    sx0 = max(0, self._to_grid(m.position.x,            "x"))
                    sx1 = min(max_gx, self._to_grid(m.position.x + m.length, "x"))
                    sy0 = max(0, self._to_grid(m.position.y,            "y"))
                    sy1 = min(max_gy, self._to_grid(m.position.y + m.width,  "y"))
                    gz_top = max(0, self._to_grid(m.position.z + m.height, "z"))
                    obs_grid[sx0:sx1+1, sy0:sy1+1, gz_top:] = True

        # Rule 2 — Hot surface
        if content in FLAMMABLE_CONTENTS:
            buf = int(math.ceil(0.5 / self.grid_resolution))
            for m in self.machinery_list:
                if m.machine_type == "Hot Surface" and m.position:
                    mx0 = max(0, self._to_grid(m.position.x,            "x") - buf)
                    mx1 = min(max_gx, self._to_grid(m.position.x + m.length, "x") + buf)
                    my0 = max(0, self._to_grid(m.position.y,            "y") - buf)
                    my1 = min(max_gy, self._to_grid(m.position.y + m.width,  "y") + buf)
                    mz0 = max(0, self._to_grid(m.position.z,            "z") - buf)
                    mz1 = min(max_gz, self._to_grid(m.position.z + m.height, "z") + buf)
                    obs_grid[mx0:mx1+1, my0:my1+1, mz0:mz1+1] = True

        # Rule 3 — Bilge / seawater separation
        if content == "Bilge":
            conflict_types: Set[str] = {"Seawater / Ballast"}
        elif content == "Seawater / Ballast":
            conflict_types = {"Bilge"}
        else:
            conflict_types = set()

        if conflict_types:
            sep = max(3, int(math.ceil(0.3 / self.grid_resolution)))
            for p in already_routed:
                p_content = getattr(p, "pipe_content", "General Fluid")
                if p_content in conflict_types and p.path:
                    for pos in p.path:
                        gx = self._to_grid(pos.x, "x")
                        gy = self._to_grid(pos.y, "y")
                        gz = self._to_grid(pos.z, "z")
                        x0, x1 = max(0, gx-sep), min(max_gx, gx+sep)
                        y0, y1 = max(0, gy-sep), min(max_gy, gy+sep)
                        z0, z1 = max(0, gz-sep), min(max_gz, gz+sep)
                        obs_grid[x0:x1+1, y0:y1+1, z0:z1+1] = True

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

        # Optimization 2: Use NumPy array for obstacles
        current_obs = self.obstacle_grid.copy()
        parallel_friendly: Set[Tuple[int, int, int]] = set()
        
        max_gx, max_gy, max_gz = [s - 1 for s in current_obs.shape]

        for p in already_routed:
            if p.path:
                safety_dist_m = (pipe.diameter + p.diameter) / 2.0
                safety_dist_g = safety_dist_m / self.grid_resolution
                r_int = int(math.ceil(safety_dist_g))
                
                # Pre-calculate relative offsets for the safety buffer
                offsets = []
                for dx in range(-r_int, r_int + 1):
                    for dy in range(-r_int, r_int + 1):
                        for dz in range(-r_int, r_int + 1):
                            dist_sq = dx*dx + dy*dy + dz*dz
                            if math.sqrt(dist_sq) < (safety_dist_g * 0.95):
                                offsets.append((dx, dy, dz))

                for pos in p.path:
                    pg = (self._to_grid(pos.x, "x"),
                          self._to_grid(pos.y, "y"),
                          self._to_grid(pos.z, "z"))
                    
                    for dx, dy, dz in offsets:
                        nx, ny, nz = pg[0]+dx, pg[1]+dy, pg[2]+dz
                        if 0 <= nx <= max_gx and 0 <= ny <= max_gy and 0 <= nz <= max_gz:
                            current_obs[nx, ny, nz] = True

                    # Mark neighbors as bundling-friendly
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            for dz in [-1, 0, 1]:
                                if dx == 0 and dy == 0 and dz == 0: continue
                                nx, ny, nz = pg[0]+dx, pg[1]+dy, pg[2]+dz
                                if 0 <= nx <= max_gx and 0 <= ny <= max_gy and 0 <= nz <= max_gz:
                                    if not current_obs[nx, ny, nz]:
                                        parallel_friendly.add((nx, ny, nz))

        self._apply_class_rules_to_grid(pipe, already_routed, current_obs)

        # Ensure start and goal are reachable
        current_obs[start] = False
        current_obs[goal]  = False

        pipe_radius_mm = (pipe.diameter / 2.0) * 1000.0
        # Optimization 3: Pre-calculate penalty grid
        penalty_grid = self._get_penalty_grid(pipe_radius_mm)

        directions = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]

        # Priority queue: (f_score, tie_break, g_score, node, last_dir)
        # Optimization 1: Removed full path from PQ
        counter = 0
        pq = [(0, counter, 0, start, (0, 0, 0))]
        
        # Optimization 2: Use NumPy for visited g-scores
        visited_g = np.full(current_obs.shape, np.inf, dtype=float)
        visited_g[start] = 0.0
        
        came_from = {}

        while pq:
            f, _, g, current, last_dir = heapq.heappop(pq)

            if current == goal:
                # Optimization 1: Reconstruct path using parent pointers
                path = []
                curr_node = goal
                while curr_node in came_from:
                    path.append(curr_node)
                    curr_node = came_from[curr_node]
                path.append(start)
                path.reverse()
                
                world_path = [Position(self._to_world(n[0], "x"),
                                      self._to_world(n[1], "y"),
                                      self._to_world(n[2], "z"))
                             for n in path]
                return world_path, "Success"

            if g > visited_g[current]:
                continue

            for dx, dy, dz in directions:
                nb = (current[0]+dx, current[1]+dy, current[2]+dz)

                if not (0 <= nb[0] <= max_gx and
                        0 <= nb[1] <= max_gy and
                        0 <= nb[2] <= max_gz):
                    continue

                if current_obs[nb]:
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

                # Suction penalty
                if pipe.suction_type == "Suction":
                    move_cost += nb[2] * self.w_suction

                # Optimization 3: Use pre-calculated penalty
                move_cost += penalty_grid[nb]

                # Parallel bundling discount
                if nb in parallel_friendly:
                    move_cost = max(0.1, move_cost - self.w_parallel)

                # Wall and ceiling preference discount
                is_near_wall = (nb[0] <= 1 or nb[0] >= max_gx - 1 or 
                                nb[1] <= 1 or nb[1] >= max_gy - 1)
                is_near_ceiling = (nb[2] >= max_gz - 1)
                
                if is_near_wall or is_near_ceiling:
                    move_cost = max(0.1, move_cost - self.w_wall_ceiling)

                new_g = g + move_cost
                if new_g < visited_g[nb]:
                    visited_g[nb] = new_g
                    came_from[nb] = current
                    h = self._heuristic(nb, goal)
                    counter += 1
                    heapq.heappush(
                        pq, (new_g + h, counter, new_g, nb, new_dir)
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

            # Compute per-path installability averages
            if path and self.fuzzy is not None and self.clearance_map is not None:
                pipe_radius_mm = (pipe.diameter / 2.0) * 1000.0
                scores: List[float] = []
                multipliers: List[float] = []
                for pos in path:
                    gx = self._to_grid(pos.x, "x")
                    gy = self._to_grid(pos.y, "y")
                    gz = self._to_grid(pos.z, "z")
                    if (0 <= gx < self.clearance_map.shape[0] and
                        0 <= gy < self.clearance_map.shape[1] and
                        0 <= gz < self.clearance_map.shape[2]):
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

            pipe.class_flags = self.check_class_flags(pipe)
            routed.append(pipe)

        return routed

    # ------------------------------------------------------------------
    # Post-routing class compliance checks
    # ------------------------------------------------------------------

    def check_class_flags(self, pipe: Pipe) -> List[str]:
        """
        Run post-routing class compliance checks on a single routed pipe.
        Returns a list of human-readable warning strings; empty = compliant.

        Checks
        ------
        5. Expansion loop (LR Pt 5, Ch 12, 3.2)     — straight run > 20 m
        6. Support span  (DNV Pt 4, Ch 6, Sec 10)    — span exceeds DN-based max
        8. HP Fuel annotation (SOLAS II-2, Reg 4)    — double-wall required
           Hot surface proximity (BV Pt C, Ch 1, Sec 10) — sanity verify
        """
        flags: List[str] = []
        if not pipe.path or len(pipe.path) < 2:
            return flags

        content = getattr(pipe, "pipe_content", "General Fluid")

        # ----------------------------------------------------------------
        # Measure the longest uninterrupted straight segment in the path
        # ----------------------------------------------------------------
        max_straight = 0.0
        seg_len       = 0.0
        prev_dir: Optional[Tuple[float, float, float]] = None

        for i in range(1, len(pipe.path)):
            dx = pipe.path[i].x - pipe.path[i - 1].x
            dy = pipe.path[i].y - pipe.path[i - 1].y
            dz = pipe.path[i].z - pipe.path[i - 1].z
            step = math.sqrt(dx*dx + dy*dy + dz*dz)
            if step < 1e-9:
                continue
            cur_dir = (round(dx/step, 2), round(dy/step, 2), round(dz/step, 2))
            if cur_dir == prev_dir:
                seg_len += step
            else:
                max_straight = max(max_straight, seg_len)
                seg_len  = step
                prev_dir = cur_dir
        max_straight = max(max_straight, seg_len)

        # ----------------------------------------------------------------
        # Flag 5 — Expansion loop required for runs > 20 m
        # ----------------------------------------------------------------
        if max_straight > 20.0:
            flags.append(
                f"⚠️ Expansion: longest straight run {max_straight:.1f} m > 20 m — "
                f"Ω-loop or bellows required (LR Pt 5, Ch 12, 3.2)"
            )

        # ----------------------------------------------------------------
        # Flag 6 — Pipe support span check (DN-based maximum)
        # ----------------------------------------------------------------
        dn_mm = pipe.diameter * 1000.0
        if   dn_mm <= 50:  max_span = 3.0
        elif dn_mm <= 100: max_span = 4.0
        elif dn_mm <= 150: max_span = 5.0
        else:              max_span = 6.0

        if max_straight > max_span:
            flags.append(
                f"⚠️ Support: run of {max_straight:.1f} m exceeds max span "
                f"{max_span:.1f} m for ⌀{dn_mm:.0f} mm — supports required "
                f"(DNV Pt 4, Ch 6, Sec 10)"
            )

        # ----------------------------------------------------------------
        # Flag 8 — HP Fuel double-wall annotation
        # ----------------------------------------------------------------
        if content == "HP Fuel (Injection)":
            flags.append(
                "📋 Spec: Double-walled (jacketed) pipe with AMS-connected leak "
                "detection alarm required (SOLAS II-2, Reg 4)"
            )

        # ----------------------------------------------------------------
        # Sanity check — flammable pipe proximity to hot surface
        # (should not occur if _apply_class_rules was active, but flags
        #  start/end endpoints that may bypass the exclusion zone)
        # ----------------------------------------------------------------
        if content in FLAMMABLE_CONTENTS:
            flagged_machines: Set[str] = set()
            for m in self.machinery_list:
                if m.machine_type == "Hot Surface" and m.position and m.id not in flagged_machines:
                    cx = m.position.x + m.length / 2.0
                    cy = m.position.y + m.width  / 2.0
                    cz = m.position.z + m.height / 2.0
                    half_diag = math.sqrt(
                        (m.length / 2)**2 + (m.width / 2)**2 + (m.height / 2)**2
                    )
                    for pos in pipe.path:
                        d = math.sqrt(
                            (pos.x - cx)**2 + (pos.y - cy)**2 + (pos.z - cz)**2
                        ) - half_diag
                        if d < 0.5:
                            flags.append(
                                f"🔴 Violation: flammable pipe within 500 mm of "
                                f"'{m.name}' — steel shielding required "
                                f"(BV Pt C, Ch 1, Sec 10 [11])"
                            )
                            flagged_machines.add(m.id)
                            break

        return flags

    # ------------------------------------------------------------------
    # Pre-computation helper
    # ------------------------------------------------------------------

    @classmethod
    def build_precomputed_grid(
        cls,
        room,
        machinery_list,
        no_go_zones,
        walking_spaces=None,
        routing_trays=None,
        fuzzy=None,
        grid_resolution: float = 0.1,
        layout_hash: str = "",
    ) -> "PrecomputedGrid":
        """
        Build the static obstacle set and BFS clearance map for the current
        room layout without running any A* routing.

        Returns a PrecomputedGrid that can be passed as precomputed_grid= to
        AStar.__init__() on every subsequent routing call, completely skipping
        the BFS step and significantly reducing re-routing time when only
        weight sliders have changed.

        Parameters
        ----------
        layout_hash : str
            An opaque fingerprint of the layout inputs (room + machinery +
            zones).  Stored in the returned grid so the caller can detect
            staleness without recomputing the grid.
        """
        tmp = cls(
            room=room,
            machinery_list=machinery_list,
            no_go_zones=no_go_zones,
            walking_spaces=walking_spaces,
            routing_trays=routing_trays,
            fuzzy=fuzzy,
            grid_resolution=grid_resolution,
            w_installability=1.0,   # forces clearance map to always be built
        )
        return PrecomputedGrid(
            obstacles=tmp.obstacles,
            obstacle_grid=tmp.obstacle_grid,
            clearance_map=tmp.clearance_map,
            grid_resolution=grid_resolution,
            layout_hash=layout_hash,
        )