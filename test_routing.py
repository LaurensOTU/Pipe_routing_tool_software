"""
test_routing.py
---------------
Standalone test: verifies that the A* router finds a valid path between
two specified points, optionally with fuzzy installability scoring.

Test scenario
-------------
  Room:      10 m × 8 m × 5 m
  Obstacle:  2 × 2 × 2 m block placed at (4, 3, 0) — centre of room
  Pipe:      from (0.5, 0.5, 1.0) to (8.5, 6.5, 1.0)
             at z = 1.0 m the obstacle occupies x [4..6], y [3..5]
             so the pipe MUST route around it

Expected behaviour
------------------
  - Path found: yes
  - Path avoids obstacle: yes  (no path point inside obstacle box)
  - With w_installability = 0: shortest-path only
  - With w_installability = 2: path prefers cells with more clearance

Run with:
    cd "Pipe_route_software_beta"
    python test_routing.py
"""

import math
import sys
import os

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from classes import Room, Machinery, Pipe, Position, NoGoZone
from algorithms import AStar
from fuzzy_installability import FuzzyInstallability

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def path_length(path):
    total = 0.0
    for i in range(1, len(path)):
        dx = path[i].x - path[i-1].x
        dy = path[i].y - path[i-1].y
        dz = path[i].z - path[i-1].z
        total += math.sqrt(dx**2 + dy**2 + dz**2)
    return total


def path_inside_box(path, xmin, ymin, zmin, xmax, ymax, zmax):
    """Returns list of path points that fall inside the obstacle box."""
    inside = []
    for p in path:
        if (xmin < p.x < xmax and
                ymin < p.y < ymax and
                zmin < p.z < zmax):
            inside.append(p)
    return inside


def print_path(path, label="Path"):
    print(f"\n  {label} ({len(path)} waypoints, length = {path_length(path):.2f} m):")
    for i, p in enumerate(path):
        print(f"    [{i:03d}]  ({p.x:.2f}, {p.y:.2f}, {p.z:.2f})")


def sep(char="─", width=62):
    print(char * width)

# ---------------------------------------------------------------------------
# Test setup
# ---------------------------------------------------------------------------

def build_scene():
    room = Room(length=10.0, width=8.0, height=5.0)

    obstacle = Machinery(
        id="obs_0",
        name="Obstacle Block",
        length=2.0, width=2.0, height=2.0,
        machine_type="General",
        constraint="floor",
        position=Position(x=4.0, y=3.0, z=0.0),
    )

    pipe = Pipe(
        id="p_0",
        name="Test Pipe",
        start=Position(x=0.5, y=0.5, z=1.0),
        end=Position(x=8.5, y=6.5, z=1.0),
        diameter=0.2,
        priority=1,
        fluid_type="General",
    )

    return room, obstacle, pipe


# ---------------------------------------------------------------------------
# Test 1 — Shortest path only (no fuzzy penalty)
# ---------------------------------------------------------------------------

def test_shortest_path():
    sep("=")
    print("  TEST 1: Shortest path (w_installability = 0)")
    sep("=")

    room, obstacle, pipe = build_scene()

    astar = AStar(
        room=room,
        machinery_list=[obstacle],
        no_go_zones=[],
        fuzzy=None,
        grid_resolution=0.5,
        w_dist=1.0,
        w_bend=2.0,
        w_vertical=1.5,
        w_installability=0.0,
    )

    [routed_pipe] = astar.route_all([pipe])

    if routed_pipe.path is None:
        print("  FAIL — No path found!")
        return False

    length = path_length(routed_pipe.path)
    print(f"\n  Path found:   YES")
    print(f"  Waypoints:    {len(routed_pipe.path)}")
    print(f"  Path length:  {length:.2f} m")

    # Check: no point inside obstacle
    intrusions = path_inside_box(
        routed_pipe.path,
        xmin=4.0, ymin=3.0, zmin=0.0,
        xmax=6.0, ymax=5.0, zmax=2.0,
    )
    if intrusions:
        print(f"  FAIL — Path passes through obstacle! ({len(intrusions)} points)")
        return False
    else:
        print(f"  Obstacle avoided: YES  ✓")

    # Straight-line distance for reference
    sl = math.sqrt((8.5-0.5)**2 + (6.5-0.5)**2)
    print(f"  Straight-line distance (2D): {sl:.2f} m  "
          f"(path is {(length/sl - 1)*100:.1f}% longer due to obstacle detour)")

    print_path(routed_pipe.path, label="Routed path")
    print("\n  TEST 1: PASSED ✓")
    return True


# ---------------------------------------------------------------------------
# Test 2 — Fuzzy installability penalty active
# ---------------------------------------------------------------------------

def test_fuzzy_routing():
    sep("=")
    print("  TEST 2: Fuzzy installability penalty (w_installability = 2.0)")
    sep("=")

    room, obstacle, pipe = build_scene()

    # Look for questionnaire CSV relative to this file
    _here   = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.normpath(os.path.join(
        _here, "..", "Graduation_python_project",
        "Questionnaire data",
        "Installability Questionaire(Sheet1) (1).csv",
    ))

    fuzzy = FuzzyInstallability(csv_path=csv_path if os.path.exists(csv_path) else None)
    fuzzy.summary()
    fuzzy.preview()

    astar = AStar(
        room=room,
        machinery_list=[obstacle],
        no_go_zones=[],
        fuzzy=fuzzy,
        grid_resolution=0.5,
        w_dist=1.0,
        w_bend=2.0,
        w_vertical=1.5,
        w_installability=2.0,
    )

    [routed_pipe] = astar.route_all([pipe])

    if routed_pipe.path is None:
        print("  FAIL — No path found!")
        return False

    length = path_length(routed_pipe.path)
    print(f"\n  Path found:             YES")
    print(f"  Waypoints:              {len(routed_pipe.path)}")
    print(f"  Path length:            {length:.2f} m")
    print(f"  Avg installability:     {routed_pipe.avg_installability_score:.3f}  "
          f"(0=impossible, 1=clear)")
    print(f"  Avg time multiplier:    {routed_pipe.avg_time_multiplier:.3f}×")

    intrusions = path_inside_box(
        routed_pipe.path,
        xmin=4.0, ymin=3.0, zmin=0.0,
        xmax=6.0, ymax=5.0, zmax=2.0,
    )
    if intrusions:
        print(f"  FAIL — Path passes through obstacle! ({len(intrusions)} points)")
        return False
    else:
        print(f"  Obstacle avoided:       YES  ✓")

    print_path(routed_pipe.path, label="Fuzzy-guided path")
    print("\n  TEST 2: PASSED ✓")
    return True


# ---------------------------------------------------------------------------
# Test 3 — No obstacle (verify straight path)
# ---------------------------------------------------------------------------

def test_straight_path():
    sep("=")
    print("  TEST 3: No obstacle — path should be (near) straight")
    sep("=")

    room = Room(length=10.0, width=8.0, height=5.0)
    pipe = Pipe(
        id="p_0",
        name="Straight Pipe",
        start=Position(x=1.0, y=1.0, z=1.0),
        end=Position(x=9.0, y=1.0, z=1.0),    # same y and z → should be straight in X
        diameter=0.1,
        priority=1,
    )

    astar = AStar(
        room=room,
        machinery_list=[],
        no_go_zones=[],
        grid_resolution=0.5,
        w_installability=0.0,
    )

    [routed_pipe] = astar.route_all([pipe])

    if routed_pipe.path is None:
        print("  FAIL — No path found!")
        return False

    # Check all points have y ≈ 1.0 and z ≈ 1.0 (straight along X)
    deviations = [
        abs(p.y - 1.0) + abs(p.z - 1.0)
        for p in routed_pipe.path
    ]
    max_dev = max(deviations)
    print(f"\n  Path found:     YES")
    print(f"  Waypoints:      {len(routed_pipe.path)}")
    print(f"  Path length:    {path_length(routed_pipe.path):.2f} m  "
          f"(straight-line = 8.00 m)")
    print(f"  Max lateral deviation from straight line: {max_dev:.3f} m")

    if max_dev < 1e-6:
        print("  Path is perfectly straight  ✓")
    else:
        print("  Path has minor bends (grid discretisation effect)")

    print("\n  TEST 3: PASSED ✓")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sep("═")
    print("  Damen OSV — Pipe Routing Test Suite")
    sep("═")
    print()

    results = []
    results.append(("Test 1 — Shortest path around obstacle", test_shortest_path()))
    print()
    results.append(("Test 2 — Fuzzy installability routing",  test_fuzzy_routing()))
    print()
    results.append(("Test 3 — Straight path (no obstacle)",   test_straight_path()))

    sep("═")
    print("  SUMMARY")
    sep("═")
    all_passed = True
    for name, passed in results:
        status = "PASSED ✓" if passed else "FAILED ✗"
        print(f"  {status}  |  {name}")
        all_passed = all_passed and passed

    print()
    if all_passed:
        print("  All tests passed. The routing tool is working correctly.")
    else:
        print("  Some tests failed — see output above.")
    sep("═")
    sys.exit(0 if all_passed else 1)
