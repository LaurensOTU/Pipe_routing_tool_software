import numpy as np
import matplotlib.pyplot as plt
from fuzzy_installability import FuzzyInstallability, ORDERED_CATS

def plot_membership_functions(csv_path="data/questionnaire_data.csv"):
    # Initialize the fuzzy system
    fuzzy = FuzzyInstallability(csv_path=csv_path)
    
    # Use a universe up to 1200mm for smooth plotting
    plot_max = 1200.0
    universe = np.linspace(fuzzy.min_val, plot_max, 500)
    
    plt.figure(figsize=(10, 6))
    
    # 1. Plot Membership Functions
    for cat in ORDERED_CATS:
        # Interpolate the pre-computed MF array to our denser universe
        # Use 'extrapolate' or clip to ensure values outside fuzzy.universe are handled
        # The 'clear' function should be 1.0 for high values due to the 'shoulder' logic
        mf = np.interp(universe, fuzzy.universe, fuzzy.mf_arrays[cat], right=(1.0 if cat == 'clear' else 0.0))
        plt.plot(universe, mf, label=cat.replace('_', ' ').title(), linewidth=2)
        
        # Mark the centers
        center = fuzzy.centers[cat]
        if center <= plot_max:
            plt.axvline(x=center, color='grey', linestyle='--', alpha=0.3)
            plt.text(center, 1.02, f"{int(center)}mm", rotation=45, ha='center', fontsize=8)

    plt.title("Fuzzy Membership Functions for Pipe Clearance", fontsize=14)
    plt.xlabel("Clearance Distance (mm)", fontsize=12)
    plt.ylabel("Membership Degree", fontsize=12)
    plt.xlim(0, plot_max)
    plt.legend(loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.ylim(0, 1.1)
    plt.tight_layout()
    plt.savefig("membership_functions.png", dpi=300)
    print("Saved membership_functions.png")

    # 2. Plot Defuzzified Time Multiplier
    plt.figure(figsize=(10, 6))
    
    time_mults = []
    for x in universe:
        _, mult, _ = fuzzy.get_score(x)
        time_mults.append(mult)
        
    plt.plot(universe, time_mults, color='red', linewidth=3, label='Defuzzified Time Multiplier')
    
    # Add horizontal lines for the discrete multiplier levels
    colors = plt.cm.viridis(np.linspace(0, 1, len(ORDERED_CATS)))
    for i, cat in enumerate(ORDERED_CATS):
        mult = fuzzy.multipliers[cat]
        plt.axhline(y=mult, color=colors[i], linestyle='--', alpha=0.5, label=f"{cat.replace('_', ' ').title()} Level ({mult}x)")

    plt.title("Defuzzified Time Multiplier vs. Clearance", fontsize=14)
    plt.xlabel("Clearance Distance (mm)", fontsize=12)
    plt.ylabel("Time Multiplier (x baseline)", fontsize=12)
    plt.xlim(0, plot_max)
    plt.legend(loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig("time_multiplier_defuzzification.png", dpi=300)
    print("Saved time_multiplier_defuzzification.png")

if __name__ == "__main__":
    plot_membership_functions()
