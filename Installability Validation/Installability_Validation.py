import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os


# Open and attain data from csvs:
dfs_by_name = {}
dir = os.getcwd()

for file in os.listdir(dir):
    if file.endswith(".csv"):
        df_name = os.path.splitext(file)[0]
        df = pd.read_csv(file)
        df["source_file"] = df_name
        df["Installability weight"] = df_name.split("_")[-1] # Extract weight from filename
        df["Installability weight"] = df["Installability weight"].astype(float)
        if df["Installability weight"][0] > 0:
            df["Installability weight"] = df["Installability weight"]/100
        dfs_by_name[df_name] = df
        print(f"\n=== DATA SUMMARY for {df_name} ===")

# II plotting
x_data = []
y_data = []

plt.figure()
for df_name, df in dfs_by_name.items():
    avg_II = df["Install score"].mean()
    plt.scatter(df["Installability weight"][0], avg_II, label=df_name)
    x_data.append(df["Installability weight"][0])
    y_data.append(avg_II)
# Fit polynomial :
x_data = np.array(x_data)
y_data = np.array(y_data)
sort_idx = np.argsort(x_data)
x_data = x_data[sort_idx]
y_data = y_data[sort_idx]
coefficients = np.polyfit(x_data, y_data, 4)
polynomial_II = np.poly1d(coefficients)
x_smooth = np.linspace(x_data.min(), x_data.max(), 100)
plt.plot(x_smooth, polynomial_II(x_smooth), 'r--',label='Polynomial fit')

plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Installability Score")
plt.title("Average Installability Score by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
plt.tight_layout()
plt.show()


# TM plotting
x_data = []
y_data = []

plt.figure()
for df_name, df in dfs_by_name.items():
    stripped_TM_col = df["Time mult"].str.replace("×", "").astype(float)
    avg_TM = stripped_TM_col.mean()
    plt.scatter(df["Installability weight"][0], avg_TM)
    x_data.append(df["Installability weight"][0])
    y_data.append(avg_TM)

x_data = np.array(x_data)
y_data = np.array(y_data)
sort_idx = np.argsort(x_data)
x_data = x_data[sort_idx]
y_data = y_data[sort_idx]
coefficients = np.polyfit(x_data, y_data, 4)
polynomial_TM = np.poly1d(coefficients)
x_smooth = np.linspace(x_data.min(), x_data.max(), 100)
plt.plot(x_smooth, polynomial_TM(x_smooth), 'r--',label='Polynomial fit')
plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Time Multipliler Score")
plt.title("Average Time Multiplier by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
plt.tight_layout()
plt.show()


plt.figure()
for df_name, df in dfs_by_name.items():
    avg_length = df["Length (m)"].mean()
    plt.scatter(df["Installability weight"][0], avg_length)
plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Length (m)")
plt.title("Average Length by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
plt.tight_layout()
plt.show()


print("=== 2D plots have been created ===")


# --- 3D Visualization ---
fig = plt.figure(figsize=(12, 8))
ax = fig.add_subplot(111, projection='3d')

# Prepare data for 3D plot
plot_data = []
for df_name, df in dfs_by_name.items():
    weight = df["Installability weight"].iloc[0]
    avg_II = df["Install score"].mean()
    avg_TM = df["Time mult"].str.replace("×", "").astype(float).mean()
    plot_data.append((weight, avg_II, avg_TM))

# Sort by weight to make the trend line logical
plot_data.sort(key=lambda x: x[0])
weights, scores, multipliers = zip(*plot_data)

# Scatter points and trend line
ax.scatter(weights, scores, multipliers, c='blue', marker='o', s=60, label='Data points')
ax.plot(weights, scores, multipliers, color='red', linestyle='--', alpha=0.6, label='Trend line')

# Labeling
ax.set_xlabel('Installability Weight', labelpad=10)
ax.set_ylabel('Avg Installability Score', labelpad=10)
ax.set_zlabel('Avg Time Multiplier', labelpad=10)
ax.set_title('3D Trade-off Analysis: Weight vs. Score vs. Time Multiplier')
ax.legend()

# Improve view angle
ax.view_init(elev=20, azim=45)

plt.tight_layout()
plt.show()

print("=== 3D plots have been created ===")