"""
visualization.py
----------------
Builds the 3D Plotly figure for the engine room.

New parameters versus original:
  snap_grid_z     : float  — if set, draws a clickable snap-grid plane at this z height
  grid_resolution : float  — spacing of snap grid dots (metres)
  snap_start      : Position — green marker for selected pipe start point
  snap_end        : Position — red marker for selected pipe end point
"""

import numpy as np
import plotly.graph_objects as go
from classes import Room, Machinery, Pipe, NoGoZone, Position, WalkingSpace, RoutingTray
from typing import List, Optional


def create_snap_figure(
    room: Room,
    machinery_list: List[Machinery] = [],
    snap_grid_z: float = 0.0,
    grid_resolution: float = 0.5,
    snap_start: Optional[Position] = None,
    snap_end: Optional[Position] = None,
    walking_spaces: List[WalkingSpace] = [],
    routing_trays: List[RoutingTray] = [],
):
    """
    2-D top-down (XY) floor-plan for click-to-place pipe endpoints.

    Uses a 2-D Scatter trace with dragmode='select' so that a single click
    on any cyan grid dot fires Streamlit's on_select event.  The z-coordinate
    comes from snap_grid_z (controlled by the height slider in the UI).
    """
    fig = go.Figure()
    L, W = room.length, room.width

    # Machinery footprints (top-down rectangles)
    machine_colours = {
        "General":     ("royalblue",  0.40),
        "Switchboard": ("darkorange", 0.45),
        "Hot Surface": ("firebrick",  0.45),
    }
    for m in machinery_list:
        if not m.position:
            continue
        colour, opacity = machine_colours.get(m.machine_type, ("royalblue", 0.40))
        xn, yn = m.position.x, m.position.y
        xx, yx = xn + m.length, yn + m.width
        fig.add_shape(
            type="rect", x0=xn, y0=yn, x1=xx, y1=yx,
            fillcolor=colour, opacity=opacity,
            line=dict(color=colour, width=1),
        )
        fig.add_annotation(
            x=(xn + xx) / 2, y=(yn + yx) / 2,
            text=m.name, showarrow=False,
            font=dict(size=9, color="white"),
        )

    # Walking space footprints (green hatched rectangles)
    for w in walking_spaces:
        # Only show the footprint if the snap plane is within the walking space
        fill = "mediumseagreen" if snap_grid_z <= w.height else "lightgrey"
        fig.add_shape(
            type="rect", x0=w.x_min, y0=w.y_min, x1=w.x_max, y1=w.y_max,
            fillcolor=fill, opacity=0.30,
            line=dict(color="green", width=1, dash="dot"),
        )
        fig.add_annotation(
            x=(w.x_min + w.x_max) / 2, y=(w.y_min + w.y_max) / 2,
            text=f"🚶 {w.name}", showarrow=False,
            font=dict(size=8, color="darkgreen"),
        )

    # Routing tray footprints (grey outlines at their z range)
    for t in routing_trays:
        if t.z_min <= snap_grid_z <= t.z_max:
            fig.add_shape(
                type="rect", x0=t.x_min, y0=t.y_min, x1=t.x_max, y1=t.y_max,
                fillcolor="silver", opacity=0.40,
                line=dict(color="grey", width=1),
            )
            fig.add_annotation(
                x=(t.x_min + t.x_max) / 2, y=(t.y_min + t.y_max) / 2,
                text=f"▭ {t.name}", showarrow=False,
                font=dict(size=8, color="dimgrey"),
            )

    # Snap grid dots (cyan) — customdata carries (x, y, z) for the handler
    xs, ys, cdata = [], [], []
    for gx in np.arange(0, L + grid_resolution * 0.5, grid_resolution):
        for gy in np.arange(0, W + grid_resolution * 0.5, grid_resolution):
            rx = round(min(gx, L), 3)
            ry = round(min(gy, W), 3)
            rz = round(snap_grid_z, 3)
            xs.append(rx)
            ys.append(ry)
            cdata.append([rx, ry, rz])

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers",
        marker=dict(size=8, color="cyan", opacity=0.85,
                    line=dict(color="steelblue", width=1)),
        customdata=cdata,
        name="Snap grid",
        hovertemplate="X: %{x:.2f} m   Y: %{y:.2f} m   Z: "
                      + f"{snap_grid_z:.2f} m<extra></extra>",
    ))

    # Start / End markers
    if snap_start:
        fig.add_trace(go.Scatter(
            x=[snap_start.x], y=[snap_start.y],
            mode="markers+text",
            marker=dict(size=16, color="limegreen", symbol="circle",
                        line=dict(color="darkgreen", width=2)),
            text=["S"], textfont=dict(size=11, color="darkgreen"),
            textposition="top center",
            name="Start",
            hovertemplate=(
                f"<b>Start</b>  ({snap_start.x}, {snap_start.y}, "
                f"{snap_start.z})<extra></extra>"
            ),
        ))
    if snap_end:
        fig.add_trace(go.Scatter(
            x=[snap_end.x], y=[snap_end.y],
            mode="markers+text",
            marker=dict(size=16, color="tomato", symbol="circle",
                        line=dict(color="darkred", width=2)),
            text=["E"], textfont=dict(size=11, color="darkred"),
            textposition="top center",
            name="End",
            hovertemplate=(
                f"<b>End</b>  ({snap_end.x}, {snap_end.y}, "
                f"{snap_end.z})<extra></extra>"
            ),
        ))

    fig.update_layout(
        xaxis=dict(
            range=[-0.3, L + 0.3], title="X — Length (m)",
            scaleanchor="y", scaleratio=1,
        ),
        yaxis=dict(range=[-0.3, W + 0.3], title="Y — Width (m)"),
        # dragmode='select' + clickmode='event+select' together make a single
        # point click fire Plotly's plotly_selected event, which is what
        # Streamlit's on_select listens to.
        dragmode="select",
        clickmode="event+select",
        height=320,
        margin=dict(r=0, l=0, b=30, t=0),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.7)"),
    )
    return fig


def _add_box_3d(fig: go.Figure, xn, yn, zn, xx, yx, zx, name, colour, opacity):
    """Helper to add a 3D box (Mesh3d faces + Scatter3d edges) to the figure."""
    # Vertices
    # 0:(n,n,n), 1:(x,n,n), 2:(x,x,n), 3:(n,x,n)
    # 4:(n,n,x), 5:(x,n,x), 6:(x,x,x), 7:(n,x,x)
    x = [xn, xx, xx, xn, xn, xx, xx, xn]
    y = [yn, yn, yx, yx, yn, yn, yx, yx]
    z = [zn, zn, zn, zn, zx, zx, zx, zx]

    # Faces (12 triangles)
    i = [0, 0, 4, 4, 0, 0, 1, 1, 0, 0, 3, 3]
    j = [1, 2, 5, 6, 4, 7, 5, 6, 1, 5, 2, 6]
    k = [2, 3, 6, 7, 7, 3, 6, 2, 5, 4, 6, 7]

    fig.add_trace(go.Mesh3d(
        x=x, y=y, z=z, i=i, j=j, k=k,
        color=colour, opacity=opacity,
        name=name, showlegend=True,
    ))

    # Edges
    edge_coords = [
        (0,1), (1,2), (2,3), (3,0), # bottom
        (4,5), (5,6), (6,7), (7,4), # top
        (0,4), (1,5), (2,6), (3,7)  # verticals
    ]
    for start, end in edge_coords:
        fig.add_trace(go.Scatter3d(
            x=[x[start], x[end]], y=[y[start], y[end]], z=[z[start], z[end]],
            mode='lines', line=dict(color=colour, width=2),
            showlegend=False, hoverinfo='skip'
        ))


def create_room_figure(
    room: Room,
    machinery_list: List[Machinery] = [],
    pipes: List[Pipe] = [],
    zones: List[NoGoZone] = [],
    walking_spaces: List[WalkingSpace] = [],
    routing_trays: List[RoutingTray] = [],
    snap_grid_z: Optional[float] = None,
    grid_resolution: float = 0.5,
    snap_start: Optional[Position] = None,
    snap_end: Optional[Position] = None,
):
    """
    Returns a Plotly Figure with:
      - Room wireframe
      - Machinery boxes
      - Routed pipe paths (colour-coded by installability if scored)
      - Optional snap grid plane (clickable dots at z = snap_grid_z)
      - Optional start (green) / end (red) point markers
    """
    fig = go.Figure()

    # ------------------------------------------------------------------
    # 1. Room wireframe
    # ------------------------------------------------------------------
    L, W, H = room.length, room.width, room.height
    Z_MIN = -0.5

    # True Floor (bottom of the 0.5m space)
    fig.add_trace(go.Scatter3d(
        x=[0, L, L, 0, 0], y=[0, 0, W, W, 0], z=[Z_MIN, Z_MIN, Z_MIN, Z_MIN, Z_MIN],
        mode='lines', name='True Bottom (-0.5m)',
        line=dict(color='blue', width=1, dash='dot'), showlegend=True,
    ))
    # Engine Room Floor (z=0)
    fig.add_trace(go.Scatter3d(
        x=[0, L, L, 0, 0], y=[0, 0, W, W, 0], z=[0, 0, 0, 0, 0],
        mode='lines', name='ER Floor (0m)',
        line=dict(color='black', width=2), showlegend=True,
    ))
    # Ceiling
    fig.add_trace(go.Scatter3d(
        x=[0, L, L, 0, 0], y=[0, 0, W, W, 0], z=[H, H, H, H, H],
        mode='lines', name='Ceiling',
        line=dict(color='black', width=2), showlegend=False,
    ))
    # Verticals
    for vx, vy in [(0, 0), (L, 0), (L, W), (0, W)]:
        fig.add_trace(go.Scatter3d(
            x=[vx, vx], y=[vy, vy], z=[Z_MIN, H],
            mode='lines', line=dict(color='black', width=2), showlegend=False,
        ))

    # ------------------------------------------------------------------
    # 2. Machinery boxes
    # ------------------------------------------------------------------
    machine_colours = {
        "General":     ("royalblue",   0.45),
        "Switchboard": ("darkorange",  0.50),
        "Hot Surface": ("firebrick",   0.50),
    }
    for m in machinery_list:
        if not m.position:
            continue
        colour, opacity = machine_colours.get(m.machine_type, ("royalblue", 0.45))
        _add_box_3d(
            fig,
            m.position.x, m.position.y, m.position.z,
            m.position.x + m.length, m.position.y + m.width, m.position.z + m.height,
            m.name, colour, opacity
        )

    # ------------------------------------------------------------------
    # 3. No-Go Zones
    # ------------------------------------------------------------------
    for z in zones:
        _add_box_3d(
            fig,
            z.x_min, z.y_min, z.z_min,
            z.x_max, z.y_max, z.z_max,
            f"No-Go: {z.id}", "grey", 0.20
        )

    # ------------------------------------------------------------------
    # 4. Walking Spaces
    # ------------------------------------------------------------------
    for w in walking_spaces:
        _add_box_3d(
            fig,
            w.x_min, w.y_min, 0.0,
            w.x_max, w.y_max, w.height,
            f"🚶 {w.name}", "green", 0.15
        )

    # ------------------------------------------------------------------
    # 5. Routing Trays
    # ------------------------------------------------------------------
    for t in routing_trays:
        _add_box_3d(
            fig,
            t.x_min, t.y_min, t.z_min,
            t.x_max, t.y_max, t.z_max,
            f"▭ {t.name}", "silver", 0.30
        )

    # ------------------------------------------------------------------
    # 6. Routed Pipes
    # ------------------------------------------------------------------
    for p in pipes:
        if not p.path:
            continue
        
        px = [pos.x for pos in p.path]
        py = [pos.y for pos in p.path]
        pz = [pos.z for pos in p.path]
        
        # Color by installability if scored
        score = getattr(p, 'avg_installability_score', 1.0)
        # 1.0 -> green, 0.5 -> yellow, 0.0 -> red
        if score > 0.8:
            pipe_color = "limegreen"
        elif score > 0.5:
            pipe_color = "gold"
        else:
            pipe_color = "crimson"
            
        fig.add_trace(go.Scatter3d(
            x=px, y=py, z=pz,
            mode='lines+markers',
            name=f"{p.name} (Score: {score:.2f})",
            line=dict(color=pipe_color, width=4),
            marker=dict(size=2, color=pipe_color)
        ))

    # ------------------------------------------------------------------
    # 7. Optional Snap Grid / Markers
    # ------------------------------------------------------------------
    if snap_grid_z is not None:
        xs, ys, zs = [], [], []
        for gx in np.arange(0, L + grid_resolution * 0.5, grid_resolution):
            for gy in np.arange(0, W + grid_resolution * 0.5, grid_resolution):
                xs.append(min(gx, L))
                ys.append(min(gy, W))
                zs.append(snap_grid_z)
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode='markers',
            marker=dict(size=2, color='cyan', opacity=0.3),
            name="Snap grid plane",
            showlegend=False,
            hoverinfo='skip'
        ))

    if snap_start:
        fig.add_trace(go.Scatter3d(
            x=[snap_start.x], y=[snap_start.y], z=[snap_start.z],
            mode='markers',
            marker=dict(size=8, color='limegreen', symbol='circle'),
            name="Selected Start"
        ))
    if snap_end:
        fig.add_trace(go.Scatter3d(
            x=[snap_end.x], y=[snap_end.y], z=[snap_end.z],
            mode='markers',
            marker=dict(size=8, color='tomato', symbol='circle'),
            name="Selected End"
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title="Length (X)",
            yaxis_title="Width (Y)",
            zaxis_title="Height (Z)",
            aspectmode='data'
        ),
        margin=dict(l=0, r=0, b=0, t=30),
        height=600
    )
    return fig
