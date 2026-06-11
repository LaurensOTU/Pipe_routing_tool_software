# Damen OSV — Pipe Routing & Installability Tool

A browser-based routing tool that finds optimal pipe paths in a 3D engine room layout using an A\* pathfinding algorithm, weighted by an ease-of-installation cost function derived from expert questionnaire data (Fuzzy Logic).

Developed as part of an MSc thesis at TU Delft in collaboration with Damen Offshore Specialised Vessels.

---

## Requirements

- Python 3.9 or higher
- The following packages (install via `pip install -r requirements.txt`):

```
streamlit
plotly
numpy
pandas
```

---

## Installation

1. Copy the `Pipe_route_software_beta` folder to your machine.
2. Open a terminal and navigate into the folder:
   ```
   cd path/to/Pipe_route_software_beta
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

---

## Running the tool

```
streamlit run app.py
```

The tool will open in your browser automatically. If it does not, navigate to `http://localhost:8501`.

---

## Folder structure

```
Pipe_route_software_beta/
├── app.py                    ← Main application (entry point)
├── algorithms.py             ← A* routing algorithm and BFS clearance map
├── classes.py                ← Data classes (Room, Machinery, Pipe, etc.)
├── fuzzy_installability.py   ← Fuzzy Logic scoring module
├── persistence_utils.py      ← Save / load project state (JSON)
├── visualization.py          ← 3D Plotly figures
├── export_utils.py           ← OBJ export for CAD
├── requirements.txt
├── data/
│   └── questionnaire_data.csv   ← Expert questionnaire responses (calibration data)
├── images/
│   ├── Damen_logo.png
│   └── TU_Delft_Logo.svg.png
└── JSON files/               ← Example and case study project files
```

---

## Workflow

The tool has three sequential steps, selectable in the left sidebar.

### Step 1 — Define Room

Set the engine room bounding box dimensions in metres.

- **X axis**: aft → fore
- **Y axis**: starboard → port
- **Z axis**: keel upwards

Click **Initialise Room** to confirm. A 3D preview is shown below.

### Step 2 — Place Machinery

Add machinery, walkways, and routing trays that define the obstacle environment.

- Use the **interactive floor plan** to click-select an area and pre-fill the placement forms.
- Adjust the **snap plane Z** slider to place machinery at different heights.
- Walkways are defined as floor-level rectangles and are treated as no-routing zones.
- Routing trays are rectangular corridors where parallel bundling is encouraged.

All items can be edited or removed after placement.

### Step 3 — Route Pipes

Define pipes with start/end points, diameter, content type and priority, then run the router.

**Two-stage process:**

1. **Pre-compute Grid** — builds the BFS clearance map once for the current layout. This is the slow step (typically 30–90 seconds). Only needs to be re-run if machinery is changed.
2. **Route All Pipes** — runs A\* on all defined pipes using the pre-computed grid. Fast after pre-computation; weight sliders can be adjusted and re-run without rebuilding the grid.

**Routing weight sliders:**

| Slider | Effect |
|---|---|
| Installability weight | Higher → prefers more accessible (spacious) paths |
| Bend penalty | Higher → fewer direction changes, straighter routes |
| Parallel preference | Higher → encourages bundling next to existing pipes |
| Suction low-z preference | Higher → forces suction pipes to stay low |
| Wall/Ceiling preference | Higher → routes prefer walls and ceiling |

After routing, a **3D visualisation** shows all pipes colour-coded by Installability Index, and a summary table shows route length, average install score, and average time multiplier per pipe.

Routed results can be **exported as an OBJ file** for import into CAD tools.

---

## Saving and loading projects

Use the **Project Storage** panel in the sidebar.

- **Save** — writes the current project state to a `.json` file at the specified path.
- **Save As (Download)** — downloads the project file via the browser.
- **Load** — upload any previously saved `.json` project file to restore a full project state (room, machinery, pipes, walkways, trays).

Example project files are provided in the `JSON files/` folder.

---

## Fuzzy calibration data

The installability scores are calibrated from expert questionnaire responses stored in `data/questionnaire_data.csv`. The tool loads this file automatically on startup. The sidebar shows how many responses are loaded and which membership function type is active (Triangular for ≤3 responses, Gaussian for >3).

To use a different dataset, place an additional `.csv` file in the `data/` folder and select it from the **Fuzzy Calibration Data** dropdown in the sidebar. The CSV must follow the same column structure as the existing file.

---

## Classification Society constraints

The router automatically enforces the following hard constraints based on IACS rules:

- **Fuel/flammable pipes** are excluded from switchboard vertical volumes.
- **Bilge lines** are routed separately from ballast/seawater lines.
- **Hot surface** adjacency is penalised for fuel and oil pipes.

Compliance flags are shown per pipe in the pipe list after routing.
