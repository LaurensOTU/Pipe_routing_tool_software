import json
from dataclasses import asdict
from classes import Room, Machinery, Pipe, NoGoZone, Position, WalkingSpace, RoutingTray

def serialize_state(room, machinery_list, pipe_list, no_go_zones, walking_spaces, routing_trays):
    """Converts the current project state into a JSON-serializable dictionary."""
    data = {
        "room": asdict(room) if room else None,
        "machinery_list": [asdict(m) for m in machinery_list],
        "pipe_list": [asdict(p) for p in pipe_list],
        "no_go_zones": [asdict(z) for z in no_go_zones],
        "walking_space_list": [asdict(w) for w in walking_spaces],
        "routing_tray_list": [asdict(t) for t in routing_trays],
    }
    return json.dumps(data, indent=2)

def deserialize_state(json_str):
    """Converts a JSON string back into project objects."""
    data = json.loads(json_str)
    
    room_data = data.get("room")
    room = Room(**room_data) if room_data else None
    
    machinery_list = []
    for m in data.get("machinery_list", []):
        pos_data = m.pop("position")
        pos = Position(**pos_data) if pos_data else None
        machinery_list.append(Machinery(**m, position=pos))
        
    pipe_list = []
    for p in data.get("pipe_list", []):
        start_data = p.pop("start")
        end_data = p.pop("end")
        path_data = p.pop("path")
        
        start = Position(**start_data)
        end = Position(**end_data)
        path = [Position(**pt) for pt in path_data] if path_data else None
        
        pipe_list.append(Pipe(**p, start=start, end=end, path=path))
        
    no_go_zones = [NoGoZone(**z) for z in data.get("no_go_zones", [])]
    walking_spaces = [WalkingSpace(**w) for w in data.get("walking_space_list", [])]
    routing_trays = [RoutingTray(**t) for t in data.get("routing_tray_list", [])]
    
    return room, machinery_list, pipe_list, no_go_zones, walking_spaces, routing_trays
