"""
score_existing_routes.py
------------------------
Scores the EXISTING pipe routing plan from the real Cadmatic engine room model
using the same BFS clearance map and fuzzy installability logic as the A* router.

Produces a baseline CSV of Install score + Time Multiplier per pipe system,
ready to compare against the A* algorithm's output on the same start/end points.

Steps:
  1. Load machinery from er_552205_project.json  (filter out nested assembly blocks)
  2. Build BFS clearance map via AStar.build_precomputed_grid()
  3. Load existing pipe component positions from er_object_export.json
  4. For every pipe component centre, look up clearance in the map → fuzzy score
  5. Average per system → baseline scores

Run from: Pipe_route_software_beta/
    python score_existing_routes.py
"""

import json, os, sys
import numpy as np
import pandas as pd

SCRIPT_DIR        = os.path.dirname(os.path.abspath(__file__))
ER_DIR            = os.path.join(SCRIPT_DIR, "..", "..", "Data", "Engine room model")
OBJECT_JSON       = os.path.join(ER_DIR, "er_object_export.json")
PROJECT_JSON      = os.path.join(ER_DIR, "er_552205_project.json")
QUESTIONNAIRE_CSV = os.path.join(SCRIPT_DIR, "data", "questionnaire_data.csv")
OUT_DETAIL        = os.path.join(ER_DIR, "existing_routes_detail.csv")
OUT_SUMMARY       = os.path.join(ER_DIR, "existing_routes_summary.csv")

sys.path.insert(0, SCRIPT_DIR)
from classes              import Room, Machinery, Position, NoGoZone, WalkingSpace, RoutingTray
from fuzzy_installability import FuzzyInstallability
from algorithms           import AStar

# ── Cadmatic coordinate origin (mm) used during 3dm→JSON conversion ──────────
ORIGIN_MM = (27248.0, -9867.0, -15.0)   # x0, y0, z0

GRID_RES  = 0.2   # metres — coarser than default 0.1 to keep BFS fast on large room

# ── Pipe system labels ────────────────────────────────────────────────────────
PIPE_NAMES = {
    "132": "Fuel Oil HFO",        "133": "Fuel Oil MDO",
    "141": "Fuel Oil Service",    "154": "Fuel Oil Transfer",
    "163": "Lube Oil",            "311": "Bilge",
    "312": "Bilge Oily Water",    "321": "Ballast",
    "322": "Sounding/Air Vent",   "331": "Fire Fighting Main",
    "333": "Fire Fighting Local", "371": "Sea Water Cooling",
    "372": "Sea Water Cooling (alt)", "373": "Sea Water Cooling (branch)",
    "380": "Overboard/Discharge", "540": "Exhaust Gas",
}

STRUCT_SID    = {"6002", "6005"}
STRUCT_LAYERS = {"NUPAS-SHELL-FRAMES", "NUPAS-SHELL-PLATES"}

# ─────────────────────────────────────────────────────────────────────────────

def load_clean_machinery(project: dict, max_single_dim_m: float = 6.0) -> list:
    """
    Load Machinery objects, dropping nested Cadmatic assembly blocks.
    A block is kept only if EVERY dimension ≤ max_single_dim_m.
    This removes the 12-14 m bounding boxes that span entire sub-assemblies.
    """
    kept, dropped = [], 0
    for m in project["machinery_list"]:
        if (m["length"] <= max_single_dim_m and
                m["width"]  <= max_single_dim_m and
                m["height"] <= max_single_dim_m):
            pos = Position(x=m["position"]["x"],
                           y=m["position"]["y"],
                           z=m["position"]["z"])
            kept.append(Machinery(
                id=m["id"], name=m["name"],
                length=m["length"], width=m["width"], height=m["height"],
                machine_type=m.get("machine_type","General"),
                constraint=m.get("constraint","floor"),
                position=pos, is_locked=True,
            ))
        else:
            dropped += 1
    print(f"  Machinery kept  : {len(kept)}")
    print(f"  Dropped (nested): {dropped}")
    return kept


def cadmatic_mm_to_room_m(x_mm, y_mm, z_mm):
    """Convert Cadmatic absolute mm coordinates to room-local metres."""
    return (
        (x_mm - ORIGIN_MM[0]) / 1000.0,
        (y_mm - ORIGIN_MM[1]) / 1000.0,
        (z_mm - ORIGIN_MM[2]) / 1000.0,
    )


def lookup_clearance(pg, x_m, y_m, z_m) -> float:
    """
    Read clearance (mm) from the precomputed BFS grid at position (x,y,z) metres.
    Returns max float if out of bounds.
    """
    gx = int(x_m / GRID_RES)
    gy = int(y_m / GRID_RES)
    gz = int(z_m / GRID_RES)
    shape = pg.clearance_map.shape
    if 0 <= gx < shape[0] and 0 <= gy < shape[1] and 0 <= gz < shape[2]:
        return float(pg.clearance_map[gx, gy, gz])
    return 9999.0   # outside room → treat as clear


def main():
    print("=" * 65)
    print("  Existing Route Scoring  —  Cadmatic ER 552205")
    print("=" * 65)

    # 1. Load data
    with open(OBJECT_JSON)  as f: all_objects = json.load(f)
    with open(PROJECT_JSON) as f: project     = json.load(f)

    room = Room(
        length=project["room"]["length"],
        width =project["room"]["width"],
        height=project["room"]["height"],
    )
    print(f"\nRoom : {room.length} × {room.width} × {room.height} m")

    machinery = load_clean_machinery(project)

    # 2. Initialise fuzzy system
    print("\nInitialising fuzzy logic ...")
    fuzzy = FuzzyInstallability(csv_path=QUESTIONNAIRE_CSV)
    fuzzy.summary()

    # 3. Build BFS clearance map
    print(f"\nBuilding BFS clearance map (grid resolution = {GRID_RES} m) ...")
    print("  This may take 30-90 seconds for a room this size ...")
    pg = AStar.build_precomputed_grid(
        room=room,
        machinery_list=machinery,
        no_go_zones=[],
        walking_spaces=[],
        routing_trays=[],
        fuzzy=fuzzy,
        grid_resolution=GRID_RES,
        layout_hash="er_552205",
    )
    valid = pg.clearance_map[pg.clearance_map < 1e8]
    print(f"  Grid shape      : {pg.clearance_map.shape}")
    print(f"  Clearance range : {valid.min():.0f} – {valid.max():.0f} mm")

    # 4. Collect pipe system objects
    pipe_objects = {}
    for obj in all_objects:
        sid   = obj["user_text"].get("sid", "")
        layer = obj["layer"]
        if sid in STRUCT_SID or layer in STRUCT_LAYERS:
            continue
        if sid and not sid.startswith("6"):
            pipe_objects.setdefault(sid, []).append(obj)

    print(f"\nPipe systems  : {sorted(pipe_objects.keys())}")
    PIPE_RADIUS_MM = 50.0   # conservative 100 mm OD

    # 5. Score each pipe component
    detail_rows = []
    for sid in sorted(pipe_objects.keys()):
        name = PIPE_NAMES.get(sid, f"System {sid}")
        objs = pipe_objects[sid]
        print(f"  Scoring sid={sid} ({name}) — {len(objs)} components")

        for obj in objs:
            bb = obj["bbox"]
            cx_mm = (bb["x_min"] + bb["x_max"]) / 2
            cy_mm = (bb["y_min"] + bb["y_max"]) / 2
            cz_mm = (bb["z_min"] + bb["z_max"]) / 2

            # Convert to room-local metres
            cx_m, cy_m, cz_m = cadmatic_mm_to_room_m(cx_mm, cy_mm, cz_mm)

            # Clamp to room (component centres outside room get room-boundary clearance)
            cx_m = max(0.0, min(cx_m, room.length))
            cy_m = max(0.0, min(cy_m, room.width))
            cz_m = max(0.0, min(cz_m, room.height))

            raw_cl = lookup_clearance(pg, cx_m, cy_m, cz_m)
            eff_cl = max(50.0, raw_cl - PIPE_RADIUS_MM)

            label, time_mult, inst_score = fuzzy.get_score(eff_cl)

            detail_rows.append({
                "sid":              sid,
                "system_name":      name,
                "obj_id":           obj["id"],
                "geometry_type":    obj["geometry_type"],
                "cx_m":             round(cx_m, 3),
                "cy_m":             round(cy_m, 3),
                "cz_m":             round(cz_m, 3),
                "clearance_raw_mm": round(raw_cl, 1),
                "clearance_eff_mm": round(eff_cl, 1),
                "fuzzy_label":      label,
                "install_score":    inst_score,
                "time_mult":        time_mult,
            })

    # 6. Save + print
    df = pd.DataFrame(detail_rows)
    df.to_csv(OUT_DETAIL, index=False)

    summary_rows = []
    for sid, grp in df.groupby("sid"):
        summary_rows.append({
            "sid":                  sid,
            "system_name":          PIPE_NAMES.get(sid, f"System {sid}"),
            "n_components":         len(grp),
            "avg_install_score":    round(grp["install_score"].mean(), 4),
            "min_install_score":    round(grp["install_score"].min(), 4),
            "avg_time_mult":        round(grp["time_mult"].mean(), 4),
            "max_time_mult":        round(grp["time_mult"].max(), 4),
            "avg_clearance_eff_mm": round(grp["clearance_eff_mm"].mean(), 1),
            "min_clearance_eff_mm": round(grp["clearance_eff_mm"].min(), 1),
            "pct_tight_or_worse":   round(
                100 * grp["fuzzy_label"].isin(
                    ["tight","too_tight","impossible"]).mean(), 1),
        })

    df_sum = pd.DataFrame(summary_rows).sort_values("avg_install_score")
    df_sum.to_csv(OUT_SUMMARY, index=False)

    # Pretty print
    print("\n" + "=" * 85)
    print("  EXISTING ROUTING — BASELINE INSTALLABILITY SCORES")
    print("=" * 85)
    hdr = (f"  {'SID':<5} {'System':<28} {'n':>4}  {'Avg II':>6}  "
           f"{'Avg TM':>7}  {'Max TM':>7}  {'Avg Clr':>8}  {'%Tight+':>8}")
    print(hdr)
    print("  " + "-"*81)
    for _, r in df_sum.iterrows():
        print(f"  {r['sid']:<5} {r['system_name']:<28} {r['n_components']:>4}  "
              f"{r['avg_install_score']:>6.4f}  {r['avg_time_mult']:>7.3f}×  "
              f"{r['max_time_mult']:>7.3f}×  {r['avg_clearance_eff_mm']:>7.1f}mm  "
              f"{r['pct_tight_or_worse']:>7.1f}%")

    print(f"\n  Overall avg Install Index : {df['install_score'].mean():.4f}")
    print(f"  Overall avg Time Mult     : {df['time_mult'].mean():.4f}×")
    print(f"\n  Detail → {OUT_DETAIL}")
    print(f"  Summary → {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
