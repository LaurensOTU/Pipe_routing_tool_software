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
from classes import Room, Machinery, Pipe, NoGoZone, Position
from typing import List, Optional


def create_room_figure(
    room: Room,
    machinery_list: List[Machinery] = [],
    pipes: List[Pipe] = [],
    zones: List[NoGoZone] = [],
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

    # Floor
    fig.add_trace(go.Scatter3d(
        x=[0, L, L, 0, 0], y=[0, 0, W, W, 0], z=[0, 0, 0, 0, 0],
        mode='lines', name='Floor',
        line=dict(color='black', width=2), showlegend=False,
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
            x=[vx, vx], y=[vy, vy], z=[0, H],
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
        xn, yn, zn = m.position.x, m.position.y, m.position.z
        xx, yx, zx = xn + m.length, yn + m.width, zn + m.height

        fig.add_trace(go.Mesh3d(
            x=[xn, xn, xx, xx, xn, xn, xx, xx],
            y=[yn, yx, yx, yn, yn, yx, yx, yn],
            z=[zn, zn, zn, zn, zx, zx, zx, zx],
            i=[7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2],
            j=[3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3],
            k=[0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6],
            color=colour, opacity=opacity,
            name=m.name,
            hovertemplate=(
                f"<b>{m.name}</b><br>"
                f"Type: {m.machine_type}<br>"
                f"Size: {m.length}×{m.width}×{m.height} m<br>"
                f"Pos: ({xn}, {yn}, {zn})<extra></extra>"
            ),
        ))

    # ------------------------------------------------------------------
    # 3. Routed pipes
    # ------------------------------------------------------------------
    # Colour by installability score if available (green=clear, red=tight)
    def _score_colour(score: float) -> str:
        r = int(255 * (1.0 - score))
        g = int(255 * score)
        return f"rgb({r},{g},0)"

    for p in pipes:
        if not p.path:
            continue
        px = [pos.x for pos in p.path]
        py = [pos.y for pos in p.path]
        pz = [pos.z for pos in p.path]
        score = getattr(p, 'avg_installability_score', 1.0)
        colour = _score_colour(score) if score < 0.999 else 'rgb(220,50,50)'
        width  = max(4, int(p.diameter * 25))

        label_parts = [f"<b>{p.name}</b>", f"⌀ {p.diameter} m"]
        if score < 0.999:
            label_parts.append(f"Installability: {score:.2f}")
            mult = getattr(p, 'avg_time_multiplier', 1.0)
            label_parts.append(f"Time mult: {mult:.2f}×")
        hover = "<br>".join(label_parts) + "<extra></extra>"

        fig.add_trace(go.Scatter3d(
            x=px, y=py, z=pz,
            mode='lines',
            line=dict(color=colour, width=width),
            name=p.name,
            hovertemplate=hover,
        ))

    # ------------------------------------------------------------------
    # 4. Snap grid plane  (clickable dots for pipe endpoint placement)
    # ------------------------------------------------------------------
    if snap_grid_z is not None:
        xs, ys, zs, cdata = [], [], [], []
        for gx in np.arange(0, L + grid_resolution * 0.5, grid_resolution):
            for gy in np.arange(0, W + grid_resolution * 0.5, grid_resolution):
                rx = round(min(gx, L), 3)
                ry = round(min(gy, W), 3)
                rz = round(snap_grid_z, 3)
                xs.append(rx)
                ys.append(ry)
                zs.append(rz)
                cdata.append([rx, ry, rz])   # stored in customdata for click retrieval

        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode='markers',
            marker=dict(size=5, color='cyan', opacity=0.75, symbol='circle'),
            name='Snap Grid',
            customdata=cdata,
            hovertemplate='<b>Snap point</b><br>X: %{x:.2f} m<br>Y: %{y:.2f} m<br>Z: %{z:.2f} m<extra></extra>',
        ))

    # ------------------------------------------------------------------
    # 5. Start / End point markers
    # ------------------------------------------------------------------
    if snap_start:
        fig.add_trace(go.Scatter3d(
            x=[snap_start.x], y=[snap_start.y], z=[snap_start.z],
            mode='markers+text',
            marker=dict(size=12, color='limegreen', symbol='circle',
                        line=dict(color='darkgreen', width=2)),
            text=['S'], textfont=dict(size=12, color='darkgreen'),
            textposition='top center',
            name='Start Point',
            hovertemplate=(
                f"<b>Start</b><br>"
                f"({snap_start.x}, {snap_start.y}, {snap_start.z})<extra></extra>"
            ),
        ))
    if snap_end:
        fig.add_trace(go.Scatter3d(
            x=[snap_end.x], y=[snap_end.y], z=[snap_end.z],
            mode='markers+text',
            marker=dict(size=12, color='tomato', symbol='circle',
                        line=dict(color='darkred', width=2)),
            text=['E'], textfont=dict(size=12, color='darkred'),
            textposition='top center',
            name='End Point',
            hovertemplate=(
                f"<b>End</b><br>"
                f"({snap_end.x}, {snap_end.y}, {snap_end.z})<extra></extra>"
            ),
        ))

    # ------------------------------------------------------------------
    # 6. Layout
    # ------------------------------------------------------------------
    ax_range = [0, max(L, W, H) + 0.5]
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='X — Length (m)', range=ax_range, nticks=10),
            yaxis=dict(title='Y — Width (m)',  range=ax_range, nticks=10),
            zaxis=dict(title='Z — Height (m)', range=ax_range, nticks=8),
            aspectmode='data',
        ),
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.7)'),
        margin=dict(r=0, l=0, b=0, t=0),
    )
    return fig
