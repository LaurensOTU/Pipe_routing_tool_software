"""
export_utils.py
----------------
Utilities for exporting the 3D scene to CAD-friendly formats like .obj.
"""

import math
from classes import Room, Machinery, Pipe, NoGoZone, Position, WalkingSpace, RoutingTray
from typing import List, Optional

def export_to_obj(
    room: Room,
    machinery_list: List[Machinery] = [],
    pipes: List[Pipe] = [],
    zones: List[NoGoZone] = [],
    walking_spaces: List[WalkingSpace] = [],
    routing_trays: List[RoutingTray] = [],
) -> str:
    """
    Generates the content of an .obj file for the current 3D scene.
    Includes machinery, pipes (as cylinders and centerlines), and zones.
    """
    lines = []
    lines.append("# Damen OSV Pipe Routing Export")
    lines.append(f"# Room: {room.length} x {room.width} x {room.height}")
    
    v_offset = 1

    def add_box(xn, yn, zn, xx, yx, zx, name):
        nonlocal v_offset
        lines.append(f"g {name}")
        vertices = [
            (xn, yn, zn), (xx, yn, zn), (xx, yx, zn), (xn, yx, zn),
            (xn, yn, zx), (xx, yn, zx), (xx, yx, zx), (xn, yx, zx)
        ]
        for v in vertices:
            lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
        
        faces = [
            (1, 2, 3), (1, 3, 4), (5, 6, 7), (5, 7, 8),
            (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
            (3, 4, 8), (3, 8, 7), (4, 1, 5), (4, 5, 8)
        ]
        for f in faces:
            lines.append(f"f {f[0]+v_offset-1} {f[1]+v_offset-1} {f[2]+v_offset-1}")
        v_offset += 8

    def add_cylinder(p1, p2, r, name, sides=12):
        nonlocal v_offset
        lines.append(f"g {name}")
        
        dx, dy, dz = p2.x - p1.x, p2.y - p1.y, p2.z - p1.z
        if abs(dx) > 1e-5:
            v1, v2 = (0, r, 0), (0, 0, r)
        elif abs(dy) > 1e-5:
            v1, v2 = (r, 0, 0), (0, 0, r)
        else:
            v1, v2 = (r, 0, 0), (0, r, 0)

        # Start and End circles
        for p in [p1, p2]:
            for s in range(sides):
                angle = 2 * math.pi * s / sides
                vx = p.x + math.cos(angle) * v1[0] + math.sin(angle) * v2[0]
                vy = p.y + math.cos(angle) * v1[1] + math.sin(angle) * v2[1]
                vz = p.z + math.cos(angle) * v1[2] + math.sin(angle) * v2[2]
                lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")
        
        # Side faces
        for s in range(sides):
            s_next = (s + 1) % sides
            v1_idx, v2_idx = v_offset + s, v_offset + s_next
            v3_idx, v4_idx = v_offset + sides + s, v_offset + sides + s_next
            lines.append(f"f {v1_idx} {v2_idx} {v4_idx}")
            lines.append(f"f {v1_idx} {v4_idx} {v3_idx}")
            
        v_offset += 2 * sides

    # 1. Room Floor
    add_box(0, 0, -0.01, room.length, room.width, 0, "Room_Floor")

    # 2. Machinery
    for m in machinery_list:
        if m.position:
            add_box(m.position.x, m.position.y, m.position.z,
                    m.position.x + m.length, m.position.y + m.width, m.position.z + m.height,
                    f"Machinery_{m.name.replace(' ', '_')}")

    # 3. No-Go Zones
    for z in zones:
        add_box(z.x_min, z.y_min, z.z_min, z.x_max, z.y_max, z.z_max, f"NoGoZone_{z.id}")

    # 4. Walking Spaces
    for w in walking_spaces:
        add_box(w.x_min, w.y_min, 0, w.x_max, w.y_max, w.height, f"WalkingSpace_{w.name.replace(' ', '_')}")

    # 5. Routing Trays
    for t in routing_trays:
        add_box(t.x_min, t.y_min, t.z_min, t.x_max, t.y_max, t.z_max, f"RoutingTray_{t.name.replace(' ', '_')}")

    # 6. Pipes
    for p in pipes:
        if not p.path or len(p.path) < 2:
            continue
        
        pipe_name = p.name.replace(' ', '_')
        r = p.diameter / 2.0
        for i in range(1, len(p.path)):
            add_cylinder(p.path[i-1], p.path[i], r, f"Pipe_{pipe_name}_Seg_{i}")
            
        # Centerline
        lines.append(f"g Pipe_{pipe_name}_Centerline")
        current_pipe_v_start = v_offset
        for pos in p.path:
            lines.append(f"v {pos.x:.4f} {pos.y:.4f} {pos.z:.4f}")
        for i in range(len(p.path) - 1):
            lines.append(f"l {current_pipe_v_start + i} {current_pipe_v_start + i + 1}")
        v_offset += len(p.path)

    return "\n".join(lines)
