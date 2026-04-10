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
from export_utils import export_to_obj

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
    ("machinery_edit_idx", None),
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
    # Interactive placement (Click on grid)
    # -----------------------------------------------------------------------
    st.subheader("Interactive Placement")
    st.info("💡 Click a cyan dot on the grid to set the X/Y/Z position for the machine below.")
    
    col_z, col_res = st.columns([2, 2])
    # Use existing session state for Z or a local one
    if "mach_snap_z" not in st.session_state:
        st.session_state.mach_snap_z = 0.0
    
    mach_z = col_z.slider("Snap plane Z", -0.5, float(room.height), st.session_state.mach_snap_z, 0.5)
    st.session_state.mach_snap_z = mach_z
    mach_res = col_res.select_slider("Grid resolution", [1.0, 0.5, 0.25], 0.5)

    fig_mach_snap = create_snap_figure(
        room,
        st.session_state.machinery_list,
        snap_grid_z=mach_z,
        grid_resolution=mach_res,
        walking_spaces=st.session_state.walking_space_list,
        routing_trays=st.session_state.routing_tray_list,
    )
    
    snap_event = st.plotly_chart(fig_mach_snap, on_select="rerun", key="mach_snap_chart")
    
    # Pre-fill logic for coordinates if clicked
    clicked_pos = (0.0, 0.0, mach_z)
    if snap_event and "selection" in snap_event and snap_event["selection"]["points"]:
        pt = snap_event["selection"]["points"][0]
        cd = pt.get("customdata")
        if cd:
            clicked_pos = (float(cd[0]), float(cd[1]), float(cd[2]))
        else:
            clicked_pos = (float(pt["x"]), float(pt["y"]), mach_z)
        st.toast(f"Position captured: {clicked_pos}", icon="📍")

    # -----------------------------------------------------------------------
    # Add / Edit machinery form
    # -----------------------------------------------------------------------
    edit_idx = st.session_state.machinery_edit_idx
    is_editing = edit_idx is not None and edit_idx < len(st.session_state.machinery_list)
    
    if is_editing:
        st.subheader(f"Editing: {st.session_state.machinery_list[edit_idx].name}")
        m_curr = st.session_state.machinery_list[edit_idx]
        default_name = m_curr.name
        default_l, default_w, default_h = m_curr.length, m_curr.width, m_curr.height
        default_x, default_y, default_z = m_curr.position.x, m_curr.position.y, m_curr.position.z
        # If we just clicked, override the position
        if snap_event and "selection" in snap_event and snap_event["selection"]["points"]:
            default_x, default_y, default_z = clicked_pos
        default_constraint = m_curr.constraint
        default_type = m_curr.machine_type
        btn_label = "Update Machine"
    else:
        st.subheader("Add a New Machine")
        default_name = "Main Engine"
        default_l, default_w, default_h = 2.0, 2.0, 1.5
        default_x, default_y, default_z = clicked_pos
        default_constraint = "floor"
        default_type = "General"
        btn_label = "Add Machine"

    with st.form("machinery_form", clear_on_submit=False):
        m_name = st.text_input("Machine name", value=default_name)

        c1, c2, c3 = st.columns(3)
        m_l = c1.number_input("Length (m)", min_value=0.1, max_value=room.length,  value=default_l, step=0.1)
        m_w = c2.number_input("Width (m)",  min_value=0.1, max_value=room.width,   value=default_w, step=0.1)
        m_h = c3.number_input("Height (m)", min_value=0.1, max_value=room.height,  value=default_h, step=0.1)

        st.markdown("**Position — bottom-left-front corner (m)**")
        p1, p2, p3 = st.columns(3)
        m_x = p1.number_input("X position", min_value=0.0, max_value=room.length, value=default_x, step=0.1)
        m_y = p2.number_input("Y position", min_value=0.0, max_value=room.width,  value=default_y, step=0.1)
        m_z = p3.number_input("Z position", min_value=-0.5, max_value=room.height, value=default_z, step=0.1)

        c4, c5 = st.columns(2)
        m_constraint = c4.selectbox("Constraint", ["free", "wall", "floor"], index=["free", "wall", "floor"].index(default_constraint))
        m_type       = c5.selectbox("Machine type", ["General", "Switchboard", "Hot Surface"], index=["General", "Switchboard", "Hot Surface"].index(default_type))

        submitted = st.form_submit_button(btn_label)

    if submitted:
        new_machine = Machinery(
            id=m_curr.id if is_editing else f"m_{len(st.session_state.machinery_list)}",
            name=m_name,
            length=m_l, width=m_w, height=m_h,
            constraint=m_constraint, machine_type=m_type,
            position=Position(m_x, m_y, m_z),
        )
        if is_editing:
            st.session_state.machinery_list[edit_idx] = new_machine
            st.session_state.machinery_edit_idx = None
            st.success(f"Updated '{m_name}'")
        else:
            st.session_state.machinery_list.append(new_machine)
            st.success(f"Added '{m_name}'")
        st.rerun()
    
    if is_editing:
        if st.button("Cancel Edit"):
            st.session_state.machinery_edit_idx = None
            st.rerun()

    # -----------------------------------------------------------------------
    # Machine list + edit/remove buttons
    # -----------------------------------------------------------------------
    if st.session_state.machinery_list:
        st.subheader(f"Placed machinery ({len(st.session_state.machinery_list)} items)")
        for idx, m in enumerate(st.session_state.machinery_list):
            col_info, col_edit, col_rm = st.columns([4, 1, 1])
            with col_info:
                pos = m.position
                st.text(
                    f"{m.name}  |  {m.length}×{m.width}×{m.height} m  "
                    f"|  pos ({pos.x}, {pos.y}, {pos.z})  |  {m.machine_type}"
                )
            with col_edit:
                if st.button("Edit", key=f"edit_m_{idx}"):
                    st.session_state.machinery_edit_idx = idx
                    st.rerun()
            with col_rm:
                if st.button("Remove", key=f"rm_m_{idx}"):
                    st.session_state.machinery_list.pop(idx)
                    if st.session_state.machinery_edit_idx == idx:
                        st.session_state.machinery_edit_idx = None
                    st.rerun()
    else:
        st.info("No machinery placed yet. Use the grid and form above to add machines.")

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
            "Snap plane Z (height)",
            min_value=-0.5,
            max_value=float(room.height),
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

        # Stable key so the widget survives reruns and on_select can fire.
        # The figure itself is rebuilt each run with updated markers, so the
        # key does NOT need to change when snap_start / snap_end change.
        _snap_chart_key = "snap_chart"
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

    p_name = st.text_input("Pipe name", value="Main Line")
    c_a, c_b = st.columns(2)
    p_diam = c_a.number_input("Diameter (m)", min_value=0.05, max_value=1.0, value=0.2, step=0.05)
    p_prio = c_b.number_input("Priority (1 = highest)", min_value=1, max_value=20, value=1, step=1)
    
    col_t1, col_t2 = st.columns(2)
    p_type = col_t1.selectbox("Pipe Type", ["Closed", "Open"])
    if p_type == "Closed":
        p_suction = col_t2.selectbox("Pressurised/Suction", ["Pressurised", "Suction"])
    else:
        p_suction = "Pressurised"

    st.markdown("**Start point (m)**  — or snap-select above 🟢")
    s1, s2, s3 = st.columns(3)
    sx = s1.number_input("Start X", min_value=0.0, max_value=room.length,
                          value=float(st.session_state.pipe_sx), step=0.5)
    sy = s2.number_input("Start Y", min_value=0.0, max_value=room.width,
                          value=float(st.session_state.pipe_sy), step=0.5)
    sz = s3.number_input("Start Z", min_value=-0.5, max_value=room.height,
                          value=float(st.session_state.pipe_sz), step=0.5)

    st.markdown("**End point (m)**  — or snap-select above 🔴")
    e1, e2, e3 = st.columns(3)
    ex = e1.number_input("End X", min_value=0.0, max_value=room.length,
                          value=float(st.session_state.pipe_ex), step=0.5)
    ey = e2.number_input("End Y", min_value=0.0, max_value=room.width,
                          value=float(st.session_state.pipe_ey), step=0.5)
    ez = e3.number_input("End Z", min_value=-0.5, max_value=room.height,
                          value=float(st.session_state.pipe_ez), step=0.5)

    if st.button("Add Pipe"):
        new_pipe = Pipe(
            id=f"p_{len(st.session_state.pipe_list)}",
            name=p_name,
            start=Position(sx, sy, sz),
            end=Position(ex, ey, ez),
            diameter=p_diam,
            priority=p_prio,
            pipe_type=p_type,
            suction_type=p_suction,
        )
        st.session_state.pipe_list.append(new_pipe)
        st.success(f"Added pipe '{p_name}'")
        st.rerun()

    # -----------------------------------------------------------------------
    # Pipe list
    # -----------------------------------------------------------------------
    if st.session_state.pipe_list:
        st.subheader(f"Pipes to route ({len(st.session_state.pipe_list)} items)")
        import math as _math
        for idx, p in enumerate(st.session_state.pipe_list):
            c_i, c_b = st.columns([5, 1])
            if p.path:
                total = sum(
                    _math.sqrt(
                        (p.path[i].x - p.path[i - 1].x) ** 2 +
                        (p.path[i].y - p.path[i - 1].y) ** 2 +
                        (p.path[i].z - p.path[i - 1].z) ** 2
                    )
                    for i in range(1, len(p.path))
                )
                route_info = (
                    f"  ✓ {total:.2f} m  |  "
                    f"install {p.avg_installability_score:.2f}  |  "
                    f"time {p.avg_time_multiplier:.2f}×"
                )
            else:
                reason = f" — {p.routing_status}" if p.routing_status else " — not yet routed"
                route_info = reason
            p_info = f"{p.pipe_type}"
            if p.pipe_type == "Closed":
                p_info += f" ({p.suction_type})"
            
            c_i.text(
                f"{p.name}  |  ⌀{p.diameter * 1000:.0f} mm  |  {p_info}  |  priority {p.priority}  |  "
                f"({p.start.x}, {p.start.y}, {p.start.z}) → "
                f"({p.end.x}, {p.end.y}, {p.end.z}){route_info}"
            )
            if c_b.button("Remove", key=f"rmp_{idx}"):
                st.session_state.pipe_list.pop(idx)
                st.rerun()
    else:
        st.info("No pipes added yet. Use the form above.")

    st.divider()

    # -----------------------------------------------------------------------
    # Routing settings + run button
    # -----------------------------------------------------------------------
    st.subheader("Routing Settings")

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    w_installability = col_r1.slider(
        "Installability weight",
        min_value=0.0, max_value=5.0, value=1.0, step=0.5,
        help="0 = shortest path only; higher values prefer more accessible clearance.",
    )
    w_bend = col_r2.slider(
        "Bend penalty",
        min_value=0.0, max_value=5.0, value=2.0, step=0.5,
        help="Cost per direction change — higher values produce straighter routes.",
    )
    w_tray = col_r3.slider(
        "Tray preference",
        min_value=0.0, max_value=2.0, value=0.5, step=0.25,
        help="Cost discount per step next to a routing tray.",
    )
    w_suction = col_r4.slider(
        "Suction low-z preference",
        min_value=0.0, max_value=10.0, value=5.0, step=0.5,
        help="Higher values force suction pipes to stay as low as possible.",
    )

    run_col, clr_col = st.columns([3, 1])

    if run_col.button(
        "🚀  Route All Pipes",
        type="primary",
        disabled=not st.session_state.pipe_list,
    ):
        with st.spinner("Building grid and running A* routing…  (0.1 m resolution)"):
            astar = AStar(
                room=room,
                machinery_list=st.session_state.machinery_list,
                no_go_zones=st.session_state.no_go_zones,
                walking_spaces=st.session_state.walking_space_list,
                routing_trays=st.session_state.routing_tray_list,
                fuzzy=fuzzy,
                grid_resolution=0.1,   # fine pathfinding grid; snap grid is separate
                w_dist=1.0,
                w_bend=w_bend,
                w_vertical=1.5,
                w_installability=w_installability,
                w_tray=w_tray,
                w_suction=w_suction,
            )
            routed = astar.route_all(st.session_state.pipe_list)
            st.session_state.pipe_list = routed
        st.success("Routing complete!")
        st.rerun()

    if clr_col.button("Clear routes", disabled=not st.session_state.pipe_list):
        for p in st.session_state.pipe_list:
            p.path = None
            p.avg_installability_score = 1.0
            p.avg_time_multiplier = 1.0
        st.rerun()

    # -----------------------------------------------------------------------
    # 3D result visualisation + summary table
    # -----------------------------------------------------------------------
    if any(p.path for p in st.session_state.pipe_list):
        st.subheader("3D Route Visualisation")
        fig3d = create_room_figure(
            room,
            st.session_state.machinery_list,
            st.session_state.pipe_list,
            st.session_state.no_go_zones,
            walking_spaces=st.session_state.walking_space_list,
            routing_trays=st.session_state.routing_tray_list,
        )
        st.plotly_chart(fig3d, use_container_width=True)

        # -----------------------------------------------------------------------
        # Export to CAD (OBJ)
        # -----------------------------------------------------------------------
        st.subheader("Export to CAD")
        obj_content = export_to_obj(
            room,
            st.session_state.machinery_list,
            st.session_state.pipe_list,
            st.session_state.no_go_zones,
            st.session_state.walking_space_list,
            st.session_state.routing_tray_list,
        )
        st.download_button(
            label="📥 Download 3D Model (.obj)",
            data=obj_content,
            file_name="damen_pipe_layout.obj",
            mime="text/plain",
            help="Download the full engine room layout, including machinery and routed pipes, as an OBJ file compatible with Rhino, Solidworks, and other CAD tools."
        )

        st.subheader("Route Summary")
        import pandas as _pd
        import math as _math2
        rows = []
        for p in st.session_state.pipe_list:
            if p.path:
                total = sum(
                    _math2.sqrt(
                        (p.path[i].x - p.path[i - 1].x) ** 2 +
                        (p.path[i].y - p.path[i - 1].y) ** 2 +
                        (p.path[i].z - p.path[i - 1].z) ** 2
                    )
                    for i in range(1, len(p.path))
                )
                rows.append({
                    "Pipe":           p.name,
                    "⌀ (mm)":         f"{p.diameter * 1000:.0f}",
                    "Priority":       p.priority,
                    "Length (m)":     f"{total:.2f}",
                    "Install score":  f"{p.avg_installability_score:.3f}",
                    "Time mult":      f"{p.avg_time_multiplier:.2f}×",
                    "Waypoints":      len(p.path),
                })
        if rows:
            st.dataframe(_pd.DataFrame(rows), use_container_width=True)
       