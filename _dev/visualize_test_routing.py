"""
visualize_test_routing.py
-------------------------
A script to run the routing scenarios from test_routing.py and visualize
the results using Matplotlib in 2D (top-down view).
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os
from test_routing import build_scene, path_length
from algorithms import AStar
from fuzzy_installability import FuzzyInstallability

def visualize_scenario(w_installability, title, filename):
    room, obstacle, pipe = build_scene()
    
    # Setup Fuzzy if needed
    fuzzy = None
    if w_installability > 0:
        # Try to find questionnaire data
        csv_path = "data/questionnaire_data.csv"
        fuzzy = FuzzyInstallability(csv_path=csv_path if os.path.exists(csv_path) else None)

    # Run A*
    astar = AStar(
        room=room,
        machinery_list=[obstacle],
        no_go_zones=[],
        fuzzy=fuzzy,
        grid_resolution=0.25, # Higher resolution for smoother plot
        w_dist=1.0,
        w_bend=2.0,
        w_vertical=1.5,
        w_installability=w_installability,
    )

    [routed_pipe] = astar.route_all([pipe])

    # Plotting
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 1. Draw Room Boundary
    room_rect = patches.Rectangle((0, 0), room.length, room.width, linewidth=2, edgecolor='black', facecolor='none', label='Room')
    ax.add_patch(room_rect)
    
    # 2. Draw Obstacle (Top-down)
    # Obstacle is at (4,3,0) with size 2x2x2. Since pipe is at z=1, we see the obstacle.
    obs_rect = patches.Rectangle((obstacle.position.x, obstacle.position.y), 
                                 obstacle.length, obstacle.width, 
                                 linewidth=1, edgecolor='blue', facecolor='blue', alpha=0.3, label='Obstacle')
    ax.add_patch(obs_rect)
    
    # 3. Draw Path
    if routed_pipe.path:
        px = [p.x for p in routed_pipe.path]
        py = [p.y for p in routed_pipe.path]
        
        # Color path based on installability weight
        color = 'red' if w_installability == 0 else 'green'
        label = f'Routed Path (Len: {path_length(routed_pipe.path):.2f}m)'
        ax.plot(px, py, marker='o', markersize=4, color=color, linewidth=2, label=label)
        
        # Mark Start and End
        ax.plot(px[0], py[0], 'go', markersize=10, label='Start')
        ax.plot(px[-1], py[-1], 'ro', markersize=10, label='End')
    else:
        ax.text(room.length/2, room.width/2, "NO PATH FOUND", fontsize=20, color='red', ha='center')

    ax.set_xlim(-0.5, room.length + 0.5)
    ax.set_ylim(-0.5, room.width + 0.5)
    ax.set_aspect('equal')
    ax.set_title(f"{title}\n(w_installability={w_installability})")
    ax.set_xlabel("X (meters)")
    ax.set_ylabel("Y (meters)")
    ax.legend(loc='upper right', fontsize='small')
    ax.grid(True, linestyle='--', alpha=0.6)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    print(f"Saved {filename}")
    plt.close()

if __name__ == "__main__":
    print("Generating visual tests...")
    # Test 1: Shortest Path
    visualize_scenario(w_installability=0.0, 
                       title="Test 1: Shortest Path (Ignoring Clearance)", 
                       filename="test_routing_shortest.png")
    
    # Test 2: Fuzzy Path (Prefers clearance)
    visualize_scenario(w_installability=5.0, 
                       title="Test 2: Fuzzy Guided Path (Avoiding Tight Spaces)", 
                       filename="test_routing_fuzzy.png")
    
    print("Done! Check test_routing_shortest.png and test_routing_fuzzy.png")
