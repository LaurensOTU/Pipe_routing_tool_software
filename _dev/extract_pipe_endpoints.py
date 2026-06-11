"""
extract_pipe_endpoints.py
--------------------------
Extracts start and end points for each pipe system from the Cadmatic
engine room model, using the already-exported er_object_export.json.

For each system (grouped by Cadmatic sid code), the two component centres
that are furthest apart are taken as the start and end of the pipe run.
Outputs a pipe list JSON ready to load directly into the routing tool.

Run from: Pipe_route_software_beta/
    python extract_pipe_endpoints.py
"""

import json
import os
import numpy as np

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
ER_DIR       = os.path.join(SCRIPT_DIR, "..", "..", "Data", "Engine room model")
OBJECT_JSON  = os.path.join(ER_DIR, "er_object_export.json")
OUT_JSON     = os.path.join(ER_DIR, "er_552205_pipes.json")
OUT_READABLE = os.path.join(ER_DIR, "er_552205_pipe_endpoints.txt")

# Cadmatic coordinate origin (mm) — same as used in converter and scorer
ORIGIN_MM = (27248.0, -9867.0, -15.0)

STRUCT_SID    = {"6002", "6005"}
STRUCT_LAYERS = {"NUPAS-SHELL-FRAMES", "NUPAS-SHELL-PLATES"}

PIPE_NAMES = {
    "132": "Fuel Oil HFO",
    "133": "Fuel Oil MDO",
    "141": "Fuel Oil Service",
    "154": "Fuel Oil Transfer",
    "163": "Lube Oil",
    "311": "Bilge",
    "312": "Bilge Oily Water",
    "321": "Ballast",
    "322": "Sounding/Air Vent",
    "331": "Fire Fighting Main",
    "333": "Fire Fighting Local",
    "371": "Sea Water Cooling",
    "372": "Sea Water Cooling (alt)",
    "373": "Sea Water Cooling (branch)",
    "380": "Overboard/Discharge",
    "540": "Exhaust Gas",
}

# Pipe content type per system — drives class rule enforcement in router
PIPE_CONTENT = {
    "132": "Fuel Oil",       "133": "Fuel Oil",
    "141": "Fuel Oil",       "154": "Fuel Oil",
    "163": "Lube Oil",       "311": "Bilge",
    "312": "Bilge",          "321": "Ballast",
    "322": "General Fluid",  "331": "Fire Fighting",
    "333": "Fire Fighting",  "371": "General Fluid",
    "372": "General Fluid",  "373": "General Fluid",
    "380": "General Fluid",  "540": "Exhaust Gas",
}

# Approximate pipe diameters per system (metres) — adjust if known
PIPE_DIAMETER = {
    "132": 0.10,  "133": 0.10,
    "141": 0.08,  "154": 0.08,
    "163": 0.08,  "311": 0.10,
    "312": 0.08,  "321": 0.15,
    "322": 0.05,  "331": 0.10,
    "333": 0.08,  "371": 0.15,
    "372": 0.15,  "373": 0.10,
    "380": 0.15,  "540": 0.20,
}


def cadmatic_mm_to_room_m(x_mm, y_mm, z_mm):
    return (
        round((x_mm - ORIGIN_MM[0]) / 1000.0, 3),
        round((y_mm - ORIGIN_MM[1]) / 1000.0, 3),
        round((z_mm - ORIGIN_MM[2]) / 1000.0, 3),
    )


def furthest_pair(points: np.ndarray):
    """
    Find the two points with maximum Euclidean distance.
    Uses a fast 2-pass approach (O(n)) — finds approximate diameter.
    For n < 200 components, falls back to exact O(n²) search.
    """
    n = len(points)
    if n == 1:
        return points[0], points[0]
    if n <= 200:
        # Exact search
        best_dist = -1
        p1, p2 = points[0], points[1]
        for i in range(n):
            for j in range(i + 1, n):
                d = np.linalg.norm(points[i] - points[j])
                if d > best_dist:
                    best_dist = d
                    p1, p2 = points[i], points[j]
        return p1, p2
    else:
        # Approximate: pick extremes along principal axis
        centroid = points.mean(axis=0)
        dists = np.linalg.norm(points - centroid, axis=1)
        seed = points[np.argmax(dists)]
        dists2 = np.linalg.norm(points - seed, axis=1)
        p1 = points[np.argmax(dists2)]
        dists3 = np.linalg.norm(points - p1, axis=1)
        p2 = points[np.argmax(dists3)]
        return p1, p2


def main():
    print("=" * 60)
    print("  Pipe Endpoint Extraction — Cadmatic ER 552205")
    print("=" * 60)

    with open(OBJECT_JSON) as f:
        all_objects = json.load(f)

    # Group pipe objects by sid
    pipe_objects = {}
    for obj in all_objects:
        sid   = obj["user_text"].get("sid", "")
        layer = obj["layer"]
        if sid in STRUCT_SID or layer in STRUCT_LAYERS:
            continue
        if sid and not sid.startswith("6"):
            pipe_objects.setdefault(sid, []).append(obj)

    # Build pipe list
    pipes = []
    readable_lines = []
    readable_lines.append(
        f"{'#':<3}  {'SID':<5}  {'System':<28}  "
        f"{'Start (x,y,z) m':<28}  {'End (x,y,z) m':<28}  "
        f"{'Span m':>7}  {'n':>4}"
    )
    readable_lines.append("-" * 110)

    for idx, sid in enumerate(sorted(pipe_objects.keys())):
        name    = PIPE_NAMES.get(sid, f"System {sid}")
        objs    = pipe_objects[sid]
        n       = len(objs)

        # Component centres in room-local metres
        centres = []
        for obj in objs:
            bb = obj["bbox"]
            cx_mm = (bb["x_min"] + bb["x_max"]) / 2
            cy_mm = (bb["y_min"] + bb["y_max"]) / 2
            cz_mm = (bb["z_min"] + bb["z_max"]) / 2
            x, y, z = cadmatic_mm_to_room_m(cx_mm, cy_mm, cz_mm)
            centres.append([x, y, z])

        pts = np.array(centres)
        p_start, p_end = furthest_pair(pts)
        span = round(float(np.linalg.norm(p_end - p_start)), 2)

        pipe_entry = {
            "id":           f"pipe_{idx}",
            "name":         f"{name} ({sid})",
            "start":        {"x": float(p_start[0]),
                             "y": float(p_start[1]),
                             "z": float(p_start[2])},
            "end":          {"x": float(p_end[0]),
                             "y": float(p_end[1]),
                             "z": float(p_end[2])},
            "diameter":     PIPE_DIAMETER.get(sid, 0.10),
            "priority":     idx + 1,
            "pipe_type":    "Closed",
            "suction_type": "Pressurised",
            "path":         None,
            "pipe_content": PIPE_CONTENT.get(sid, "General Fluid"),
        }
        pipes.append(pipe_entry)

        s = p_start
        e = p_end
        readable_lines.append(
            f"{idx:<3}  {sid:<5}  {name:<28}  "
            f"({s[0]:5.2f},{s[1]:5.2f},{s[2]:5.2f})          "
            f"({e[0]:5.2f},{e[1]:5.2f},{e[2]:5.2f})          "
            f"{span:>7.2f}m  {n:>4}"
        )

        print(f"  sid={sid}  {name:<28}  "
              f"start=({s[0]:.2f},{s[1]:.2f},{s[2]:.2f})  "
              f"end=({e[0]:.2f},{e[1]:.2f},{e[2]:.2f})  "
              f"span={span}m  ({n} components)")

    # Save pipe list JSON (can be loaded directly into the project)
    with open(OUT_JSON, "w") as f:
        json.dump(pipes, f, indent=2)

    # Save human-readable table
    with open(OUT_READABLE, "w") as f:
        f.write("\n".join(readable_lines) + "\n")

    print(f"\n  Pipe list JSON  → {OUT_JSON}")
    print(f"  Readable table  → {OUT_READABLE}")
    print(f"\n  {len(pipes)} pipe systems extracted.")
    print("\n  To use in the tool:")
    print("  1. Load er_552205_project.json as the project")
    print("  2. Open er_552205_pipes.json and copy the pipes array")
    print("     into the project JSON under the 'pipe_list' key, OR")
    print("     add each pipe manually via the sidebar using the")
    print("     start/end coordinates in er_552205_pipe_endpoints.txt")


if __name__ == "__main__":
    main()
