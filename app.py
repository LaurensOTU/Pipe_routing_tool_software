"""
app.py  —  Damen OSV Pipe Routing & Installability Tool
--------------------------------------------------------
Streamlit front-end with three workflow stages:

  1. Define Room       — set engine room dimensions
  2. Place Machinery   — manually enter machine positions (no GA)
  3. Route Pipes       — A* routing with optional fuzzy installability penalty
"""

import os
import streamlit as st
from classes import Room, Machinery, Pipe, NoGoZone, Position, WalkingSpace, RoutingTray
from visualization import create_room_figure, create_snap_figure
from algorithms import AStar
from fuzzy_installability import FuzzyInstallability

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Damen Pipe Routing Tool", layout="wide")
st.title("Damen OSV — Pipe Routing & Installability Tool")

# ---------------------------------------------------------------------------
# Locate available questionnaire CSVs
# ---------------------------------------------------------------------------
_here      = os.path.dirname(os.path.abspath(__file__))
_q_folder  = os.path.normpath(
    os.path.join(_here, "..", "Graduation_python_project", "Questionnaire data")
)

def _scan_csvs(folder: str) -> dict:
    """Return {display_label: full_path} for every CSV in the questionnaire folder."""
    found = {}
    if os.path.isdir(folder):
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".csv"):
                full = os.path.join(folder, fname)
                # Quick response count (lines - 1 for header)
                try:
                    with open(full, encoding="utf-8", errors="ignore") as fh:
                        n = sum(1 for _ in fh) - 1
                except Exception:
                    n = "?"
                found[f"{fname}  ({n} responses)"] = full
    return found

_available_csvs = _scan_csvs(_q_folder)

# ---------------------------------------------------------------------------
# Sidebar — Questionnaire dataset selector
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("Fuzzy Calibration Data")

if _available_csvs:
    _default_key = next(
        (k for k in _available_csvs if "firstdraft" in k.lower()),
        list(_available_csvs.keys())[-1],   # fall back to last file
    )
    _selected_label = st.sidebar.selectbox(
        "Questionnaire dataset",
        options=list(_available_csvs.keys()),
        index=list(_available_csvs.keys()).index(_default_key),
        help="Select which questionnaire CSV to use for fuzzy membership calibration.",
    )
    _csv_path = _available_csvs[_selected_label]
else:
    st.sidebar.warning("No questionnaire CSV found. Using built-in defaults.")
    _selected_label = None
    _csv_path = None

# Rebuild fuzzy module whenever the selected CSV changes
if st.session_state.get("_loaded_csv") != _csv_path:
    st.session_state.fuzzy       = FuzzyInstallability(csv_path=_csv_path)
    st.session_state._loaded_csv = _csv_path

fuzzy: FuzzyInstallability = st.session_state.fuzzy

# Show calibration status in sidebar
n = fuzzy.n_responses
mf_type = "Gaussian" if n > 3 else "Triangular"
st.sidebar.metric("Responses loaded", n)
st.sidebar.caption(f"MF type: **{mf_type}**  ({'Gaussian unlocked ✓' if n > 3 else 'Need >3 for Gaussian'})")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
for key, default in [
    ("room",              None),
    ("machinery_list",    []),
    ("no_go_zones",       []),
    ("walking_space_list", []),
    ("routing_tray_list", []),
    ("pipe_list",         []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
step = st.sidebar.radio(
    "Workflow Stage",
    ["1. Define Room", "2. Place Machinery", "3. Route Pipes"],
)

# ===========================================================================
# STEP 1 — Define Room
# ===========================================================================
if step == "1. Define Room":
    st.header("Step 1: Define Engine Room Dimensions")

    col1, col2, col3 = st.columns(3)
    with col1:
        length = st.number_input("Length (m)", min_value=1.0, value=10.0, step=0.5)
    with col2:
        width  = st.number_input("Width (m)",  min_value=1.0, value=8.0,  step=0.5)
    with col3:
        height = st.number_input("Height (m)", min_value=1.0, value=5.0,  step=0.5)

    if st.button("Initialise Room"):
        st.session_state.room = Room(length=length, width=width, height=height)
        st.success(f"Room initialised: {length} × {width} × {height} m")
        st.rerun()

    if st.session_state.room:
        st.subheader("Room Preview")
        fig = create_room_figure(
            st.session_state.room,
            st.session_state.machinery_list,
            st.session_state.pipe_list,
            st.session_state.no_go_zones,
            walking_spaces=st.session_state.walking_space_list,
            routing_trays=st.session_state.routing_tray_list,
        )
        st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# STEP 2 — Place Machinery (manual)
# ===========================================================================
elif step == "2. Place Machinery":
    st.header("Step 2: Place Machinery")

    if st.session_state.room is None:
        st.warning("Please define the room in Step 1 first.")
        st.stop()

    room = st.session_state.room

    # -----------------------------------------------------------------------
    # Add machinery form
    # -----------------------------------------------------------------------
    st.subheader("Add / Place a Machine")

    with st.form("add_machine_form", clear_on_submit=True):
        m_name = st.text_input("Machine name", value="Main Engine")

        c1, c2, c3 = st.columns(3)
        m_l = c1.number_input("Length (m)", min_value=0.1, max_value=room.length,  value=2.0, step=0.1)
        m_w = c2.number_input("Width (m)",  min_value=0.1, max_value=room.width,   value=2.0, step=0.1)
        m_h = c3.number_input("Height (m)", min_value=0.1, max_value=room.height,  value=1.5, step=0.1)

        st.markdown("**Position — bottom-left-front corner (m)**")
        p1, p2, p3 = st.columns(3)
        m_x = p1.number_input("X position", min_value=0.0, max_value=room.length, value=0.0, step=0.5)
        m_y = p2.number_input("Y position", min_value=0.0, max_value=room.width,  value=0.0, step=0.5)
        m_z = p3.number_input("Z position", min_value=0.0, max_value=room.height, value=0.0, step=0.5)

        c4, c5 = st.columns(2)
        m_constraint = c4.selectbox("Constraint",    ["free", "wall", "floor"])
        m_type       = c5.selectbox("Machine type",  ["General", "Switchboard", "Hot Surface"])

        submitted = st.form_submit_button("Add Machine")

    if submitted:
        new_id = f"m_{len(st.session_state.machinery_list)}"
        new_machine = Machinery(
            id=new_id, name=m_name,
            length=m_l, width=m_w, height=m_h,
            constraint=m_constraint, machine_type=m_type,
            position=Position(m_x, m_y, m_z),
        )
        st.session_state.machinery_list.append(new_machine)
        st.success(f"Added '{m_name}' at ({m_x}, {m_y}, {m_z})")
        st.rerun()

    # -----------------------------------------------------------------------
    # Machine list + remove buttons
    # -----------------------------------------------------------------------
    if st.session_state.machinery_list:
        st.subheader(f"Placed machinery ({len(st.session_state.machinery_list)} items)")
        for idx, m in enumerate(st.session_state.machinery_list):
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                pos = m.position
                st.text(
                    f"{m.name}  |  {m.length}×{m.width}×{m.height} m  "
                    f"|  pos ({pos.x}, {pos.y}, {pos.z})  |  {m.machine_type}"
                )
            with col_btn:
                if st.button("Remove", key=f"rm_{idx}"):
                    st.session_state.machinery_list.pop(idx)
                    st.rerun()
    else:
        st.info("No machinery placed yet. Use the form above to add machines.")

    st.divider()

    # -----------------------------------------------------------------------
    # Walking spaces
    # -----------------------------------------------------------------------
    st.subheader("Walking Spaces (crew walkways)")
    st.caption(
        "Mark areas that must stay clear for crew access. "
        "The full volume from z = 0 to z = 2.1 m is blocked for pipe routing."
    )

    with st.form("add_walking_space_form", clear_on_submit=True):
        ws_name = st.text_input("Name", value="Main walkway")
        st.markdown("**XY footprint (m)**")
        wc1, wc2, wc3, wc4 = st.columns(4)
        ws_x0 = wc1.number_input("X min", min_value=0.0, max_value=room.length, value=0.0, step=0.5)
        ws_x1 = wc2.number_input("X max", min_value=0.0, max_value=room.length, value=2.0, step=0.5)
        ws_y0 = wc3.number_input("Y min", min_value=0.0, max_value=room.width,  value=0.0, step=0.5)
        ws_y1 = wc4.number_input("Y max", min_value=0.0, max_value=room.width,  value=room.width, step=0.5)
        st.info("Height is fixed at **2.1 m** (head-clearance requirement).")
        ws_submitted = st.form_submit_button("Add Walking Space")

    if ws_submitted:
        wid = f"ws_{len(st.session_state.walking_space_list)}"
        st.session_state.walking_space_list.append(
            WalkingSpace(id=wid, name=ws_name,
                         x_min=ws_x0, y_min=ws_y0, x_max=ws_x1, y_max=ws_y1)
        )
        st.success(f"Added walking space '{ws_name}'")
        st.rerun()

    if st.session_state.walking_space_list:
        for idx, w in enumerate(st.session_state.walking_space_list):
            c_i, c_b = st.columns([5, 1])
            c_i.text(f"{w.name}  |  X {w.x_min}–{w.x_max}  Y {w.y_min}–{w.y_max}  h=2.1 m")
            if c_b.button("Remove", key=f"rmws_{idx}"):
                st.session_state.walking_space_list.pop(idx)
                st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Routing trays
    # -----------------------------------------------------------------------
    st.subheader("Routing Trays")
    st.caption(
        "Define tray zones where pipes are preferred to run. "
        "The A* router gives a cost discount to cells inside trays."
    )

    with st.form("add_routing_tray_form", clear_on_submit=True):
        rt_name = st.text_input("Tray name", value="Port side tray")
        st.markdown("**3-D bounding box (m)**")
        rc1, rc2 = st.columns(2)
        with rc1:
            st.markdown("*Min corner*")
            rca, rcb, rcc = st.columns(3)
            rt_x0 = rca.number_input("X min", min_value=0.0, max_value=room.length, value=0.0, step=0.5, key="rt_x0")
            rt_y0 = rcb.number_input("Y min", min_value=0.0, max_value=room.width,  value=0.0, step=0.5, key="rt_y0")
            rt_z0 = rcc.number_input("Z min", min_value=0.0, max_value=room.height, value=room.height - 0.5, step=0.5, key="rt_z0")
        with rc2:
            st.markdown("*Max corner*")
            rcd, rce, rcf = st.columns(3)
            rt_x1 = rcd.number_input("X max", min_value=0.0, max_value=room.length, value=room.length, step=0.5, key="rt_x1")
            rt_y1 = rce.number_input("Y max", min_value=0.0, max_value=room.width,  value=0.5,         step=0.5, key="rt_y1")
            rt_z1 = rcf.number_input("Z max", min_value=0.0, max_value=room.height, value=room.height,  step=0.5, key="rt_z1")
        rt_submitted = st.form_submit_button("Add Routing Tray")

    if rt_submitted:
        tid = f"rt_{len(st.session_state.routing_tray_list)}"
        st.session_state.routing_tray_list.append(
            RoutingTray(id=tid, name=rt_name,
                        x_min=rt_x0, y_min=rt_y0, z_min=rt_z0,
                        x_max=rt_x1, y_max=rt_y1, z_max=rt_z1)
        )
        st.success(f"Added routing tray '{rt_name}'")
        st.rerun()

    if st.session_state.routing_tray_list:
        for idx, t in enumerate(st.session_state.routing_tray_list):
            c_i, c_b = st.columns([5, 1])
            c_i.text(
                f"{t.name}  |  "
                f"X {t.x_min}–{t.x_max}  Y {t.y_min}–{t.y_max}  Z {t.z_min}–{t.z_max} m"
            )
            if c_b.button("Remove", key=f"rmrt_{idx}"):
                st.session_state.routing_tray_list.pop(idx)
                st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Visualisation
    # -----------------------------------------------------------------------
    st.subheader("Layout Preview")
    fig = create_room_figure(
        room,
        st.session_state.machinery_list,
        st.session_state.pipe_list,
        st.session_state.no_go_zones,
        walking_spaces=st.session_state.walking_space_list,
        routing_trays=st.session_state.routing_tray_list,
    )
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# STEP 3 — Route Pipes
# ===========================================================================
elif step == "3. Route Pipes":
    st.header("Step 3: Route Pipes")

    if st.session_state.room is None:
        st.warning("Please define the room in Step 1 first.")
        st.stop()

    room = st.session_state.room

    # -----------------------------------------------------------------------
    # Snap-to-grid endpoint selector
    # -----------------------------------------------------------------------
    # Session state keys for selected coordinates (populated by snap clicks)
    for _k, _v in [
        ("snap_start", None), ("snap_end", None),
        ("snap_mode", "Off"),
        ("pipe_sx", 0.5), ("pipe_sy", 0.5), ("pipe_sz", 1.0),
        ("pipe_ex", room.length - 0.5), ("pipe_ey", room.width - 0.5), ("pipe_ez", 1.0),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    with st.expander("🖱️  Click to place pipe endpoints in the 3D view", expanded=True):
        col_mode, col_z, col_res = st.columns([2, 2, 2])

        snap_mode = col_mode.radio(
            "Snap mode",
            ["Off", "Set Start  🟢", "Set End  🔴"],
            horizontal=True,
            key="snap_mode_radio",
        )
        snap_z = col_z.slider(
            "Snap plane height (m)",
            min_value=0.0, max_value=room.height,
            value=st.session_state.pipe_sz,
            step=0.5,
            help="The horizontal plane the click grid sits on. Change this to place endpoints at different heights.",
        )
        snap_res = col_res.select_slider(
            "Grid snap resolution (m)",
            options=[1.0, 0.5, 0.25],
            value=0.5,
        )

        # Build start/end Position objects from session state for markers
        _ss = st.session_state.snap_start
        _se = st.session_state.snap_end
        snap_start_pos = Position(_ss[0], _ss[1], _ss[2]) if _ss else None
        snap_end_pos   = Position(_se[0], _se[1], _se[2]) if _se else None

        # 2-D top-down snap grid (on_select works reliably in 2-D; 3-D clicks
        # only fire plotly_click, not plotly_selected that Streamlit listens to)
        fig_snap = create_snap_figure(
            room,
            st.session_state.machinery_list,
            snap_grid_z=snap_z,
            grid_resolution=snap_res,
            snap_start=snap_start_pos,
            snap_end=snap_end_pos,
            walking_spaces=st.session_state.walking_space_list,
            routing_trays=st.session_state.routing_tray_list,
        )

        st.caption(
            "Top-down floor plan — click a cyan dot to place the selected endpoint."
        )

        # Key encodes snap state so the chart always re-renders with fresh markers.
        _snap_chart_key = (
            f"snap_chart_{st.session_state.snap_start}_{st.session_state.snap_end}"
        )
        try:
            snap_event = st.plotly_chart(
                fig_snap,
                use_container_width=True,
                on_select="rerun",
                key=_snap_chart_key,
            )
            # Process click only when snap mode is active
            if snap_mode != "Off" and snap_event and snap_event.selection.points:
                pt = snap_event.selection.points[0]
                # customdata holds [x, y, z]; handle both Bunch and dict forms
                cd = (
                    getattr(pt, "customdata", None)
                    or (pt.get("customdata") if hasattr(pt, "get") else None)
                )
                if cd and len(cd) >= 3:
                    cx, cy, cz = float(cd[0]), float(cd[1]), float(cd[2])
                else:
                    # Fall back to point x/y + snap plane z
                    raw_x = getattr(pt, "x", None) or (pt.get("x") if hasattr(pt, "get") else None)
                    raw_y = getattr(pt, "y", None) or (pt.get("y") if hasattr(pt, "get") else None)
                    if raw_x is None or raw_y is None:
                        raw_x = raw_y = None
                    cx = round(float(raw_x), 3) if raw_x is not None else None
                    cy = round(float(raw_y), 3) if raw_y is not None else None
                    cz = round(snap_z, 3)
                if cx is not None and cy is not None:
                    if "Start" in snap_mode:
                        st.session_state.snap_start = (cx, cy, cz)
                        st.session_state.pipe_sx    = cx
                        st.session_state.pipe_sy    = cy
                        st.session_state.pipe_sz    = cz
                        st.toast(f"Start set to ({cx}, {cy}, {cz}) m", icon="🟢")
                    else:
                        st.session_state.snap_end = (cx, cy, cz)
                        st.session_state.pipe_ex  = cx
                        st.session_state.pipe_ey  = cy
                        st.session_state.pipe_ez  = cz
                        st.toast(f"End set to ({cx}, {cy}, {cz}) m", icon="🔴")
                    st.rerun()
        except TypeError:
            # Fallback for Streamlit < 1.33
            st.plotly_chart(fig_snap, use_container_width=True)
            st.caption("⚠️  Upgrade Streamlit to ≥ 1.33 to enable click-to-place.")

        # Status line showing currently selected points
        s_txt = f"🟢 Start: {st.session_state.snap_start}" if st.session_state.snap_start else "🟢 Start: not set"
        e_txt = f"🔴 End: {st.session_state.snap_end}"     if st.session_state.snap_end   else "🔴 End: not set"
        st.caption(f"{s_txt}    |    {e_txt}")

        if st.button("Clear selected points"):
            st.session_state.snap_start = None
            st.session_state.snap_end   = None
            st.rerun()

    # -----------------------------------------------------------------------
    # Add pipe form  (coordinates pre-filled from snap selection)
    # -----------------------------------------------------------------------
    st.subheader("Add a Pipe")

    with st.form("add_pipe_form", clear_on_submit=True):
        p_name = st.text_input("Pipe name", value="Fuel Line")
        c_a, c_b = st.columns(2)
        p_diam = c_a.number_input("Diameter (m)", min_value=0.05, max_value=1.0, value=0.2, step=0.05)
        p_prio = c_b.number_input("Priority (1 = highest)", min_value=1, max_value=20, value=1, step=1)
        p_type = st.selectbox("Fluid type", ["General", "Fuel", "Water", "Electric"])

        st.markdown("**Start point (m)**  — or snap-select above 🟢")
        s1, s2, s3 = st.columns(3)
        sx = s1.number_input("Start X", min_value=0.0, max_value=room.length,
                              value=float(st.session_state.pipe_sx), step=0.5)
        sy = s2.number_input("Start Y", min_value=0.0, max_value=room.width,
                              value=float(st.session_state.pipe_sy), step=0.5)
        sz = s3.number_input("Start Z", min_value=0.0, max_value=room.height,
                              value=float(st.session_state.pipe_sz), step=0.5)

        st.markdown("**End point (m)**  — or snap-select above 🔴")
        e1, e2, e3 = st.columns(3)
        ex = e1.number_input("End X", min_value=0.0, max_value=room.length,
                              value=float(st.session_state.pipe_ex), step=0.5)
        ey = e2.number_input("End Y", min_value=0.0, max_value=room.width,
                              value=float(st.session_state.pipe_ey), step=0.5)
        ez = e3.number_input("End Z", min_value=0.0, max_value=room.height,
                              value=float(st.session_state.pipe_ez), step=0.5)

        pipe_submitted = st.form_submit_button("Add Pipe")

    if pipe_submitted:
        new_id   = f"p_{len(st.session_state.pipe_list)}"
        new_pipe = Pipe(
            id=new_id, name=p_name,
            start=Position(sx, sy, sz),
            end=Position(ex, ey, ez),
            diameter=p_diam, priority=p_prio, fluid_type=p_type,
        )
        st.session_state.pipe_list.append(new_pipe)
        st.success(f"Added pipe '{p_name}'")
        st.rerun()

    # -----------------------------------------------------------------------
    # Pipe list
    # -----------------------------------------------------------------------
    if st.session_state.pipe_list:
        st.subheader(f"Pipes ({len(st.session_state.pipe_list)} items)")
        for idx, p in enumerate(st.session_state.pipe_list):
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                routed = "✓ Routed" if p.path else "— Not routed"
                score_txt = (
                    f"  |  Installability: {p.avg_installability_score:.2f}  "
                    f"|  Time mult: {p.avg_time_multiplier:.2f}×"
                    if p.path and p.avg_installability_score < 1.0 else ""
                )
                st.text(
                    f"{p.name}  |  ⌀{p.diam_str() if hasattr(p,'diam_str') else str(p.diameter)} m  "
                    f"|  Priority {p.priority}  |  {p.fluid_type}  |  {routed}{score_txt}"
                )
            with col_btn:
                if st.button("Remove", key=f"rmp_{idx}"):
                    st.session_state.pipe_list.pop(idx)
                    st.rerun()
    else:
        st.info("No pipes added yet.")

    st.divider()

    # -----------------------------------------------------------------------
    # Routing settings
    # -----------------------------------------------------------------------
    st.subheader("Routing Settings")

    col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
    w_dist = col_r1.slider("Distance weight",        0.1, 5.0,  1.0, 0.1)
    w_bend = col_r2.slider("Bend penalty",           0.0, 10.0, 2.0, 0.5)
    w_vert = col_r3.slider("Vertical penalty",       0.0, 10.0, 1.5, 0.5)
    w_inst = col_r4.slider("Installability penalty", 0.0, 5.0,  0.0, 0.5,
                           help="0 = pure shortest path. Increase to prefer more accessible routes.")
    w_tray = col_r5.slider("Tray preference",        0.0, 2.0,  0.5, 0.1,
                           help="Cost discount per step inside a routing tray. 0 = ignore trays.")

    col_g1, col_g2 = st.columns(2)
    grid_res = col_g1.select_slider(
        "Grid resolution (m)", options=[0.5, 0.25, 0.1], value=0.5,
        help="Finer grid = more accurate routing but slower. 0.5 m recommended for interactive use."
    )

    # Fuzzy module info
    if w_inst > 0:
        n = st.session_state.fuzzy.n_responses
        st.info(
            f"**Fuzzy installability penalty active** (weight = {w_inst})  "
            f"— calibrated on **{n} questionnaire response{'s' if n != 1 else ''}**."
        )

    # -----------------------------------------------------------------------
    # Route button
    # -----------------------------------------------------------------------
    if st.button("▶  Route All Pipes (A*)", type="primary"):
        if not st.session_state.pipe_list:
            st.warning("Add at least one pipe first.")
        else:
            with st.spinner("Building clearance map and routing..."):
                astar = AStar(
                    room=room,
                    machinery_list=st.session_state.machinery_list,
                    no_go_zones=st.session_state.no_go_zones,
                    walking_spaces=st.session_state.walking_space_list,
                    routing_trays=st.session_state.routing_tray_list,
                    fuzzy=st.session_state.fuzzy if w_inst > 0 else None,
                    grid_resolution=grid_res,
                    w_dist=w_dist,
                    w_bend=w_bend,
                    w_vertical=w_vert,
                    w_installability=w_inst,
                    w_tray=w_tray,
                )
                st.session_state.pipe_list = astar.route_all(
                    st.session_state.pipe_list
                )
            st.success("Routing complete!")
            st.rerun()

    # -----------------------------------------------------------------------
    # Results table
    # -----------------------------------------------------------------------
    routed_pipes = [p for p in st.session_state.pipe_list if p.path]
    if routed_pipes:
        st.subheader("Routing Results")
        import math
        results = []
        for p in routed_pipes:
            # Path length
            path_len = 0.0
            for i in range(1, len(p.path)):
                dx = p.path[i].x - p.path[i-1].x
                dy = p.path[i].y - p.path[i-1].y
                dz = p.path[i].z - p.path[i-1].z
                path_len += math.sqrt(dx**2 + dy**2 + dz**2)
            results.append({
                "Pipe":              p.name,
                "Length (m)":        round(path_len, 2),
                "Segments":          len(p.path),
                "Installability":    p.avg_installability_score,
                "Time multiplier":   f"{p.avg_time_multiplier:.2f}×",
            })

        import pandas as pd
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)

    # -----------------------------------------------------------------------
    # 3D visualisation
    # -----------------------------------------------------------------------
    st.subheader("3D Routing Visualisation")
    fig = create_room_figure(
        room,
        st.session_state.machinery_list,
        st.session_state.pipe_list,
        st.session_state.no_go_zones,
        walking_spaces=st.session_state.walking_space_list,
        routing_trays=st.session_state.routing_tray_list,
    )
    st.plotly_chart(fig, use_container_width=True)
