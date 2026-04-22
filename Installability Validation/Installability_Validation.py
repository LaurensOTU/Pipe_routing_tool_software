import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

from holoviews.plotting.bokeh.styles import font_size

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


#%% Plotting

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
coefficients = np.polyfit(x_data, y_data, 1)
polynomial_II = np.poly1d(coefficients)
x_smooth = np.linspace(x_data.min(), x_data.max(), 100)
plt.plot(x_smooth, polynomial_II(x_smooth), 'r--',label='Polynomial fit')

plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Installability Score")
plt.legend(loc='upper left', fontsize=5)
plt.title("Average Installability Score by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
# plt.tight_layout()
plt.show()


#TM plotting
x_data = []
y_data = []

plt.figure()
for df_name, df in dfs_by_name.items():
    stripped_TM_col = df["Time mult"].str.replace("×", "").astype(float)
    avg_TM = stripped_TM_col.mean()
    plt.scatter(df["Installability weight"][0], avg_TM, label='df_name')
    x_data.append(df["Installability weight"][0])
    y_data.append(avg_TM)

x_data = np.array(x_data)
y_data = np.array(y_data)
sort_idx = np.argsort(x_data)
x_data = x_data[sort_idx]
y_data = y_data[sort_idx]
coefficients = np.polyfit(x_data, y_data, 1)
polynomial_TM = np.poly1d(coefficients)
x_smooth = np.linspace(x_data.min(), x_data.max(), 100)
plt.plot(x_smooth, polynomial_TM(x_smooth), 'r--',label='Polynomial fit')
plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Time Multipliler Score")
plt.legend(loc='upper right', fontsize=5)
plt.title("Average Time Multiplier by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
plt.tight_layout()
plt.show()


y_data = []
plt.figure()
for df_name, df in dfs_by_name.items():
    avg_length = df["Length (m)"].mean()
    y_data.append(avg_length)
    plt.scatter(df["Installability weight"][0], avg_length)

y_data = np.array(y_data)
y_data = y_data[sort_idx]
coefficients = np.polyfit(x_data, y_data, 1)
polynomial_length = np.poly1d(coefficients)
plt.plot(x_smooth, polynomial_length(x_smooth), 'r--',label='Polynomial fit')
plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Length (m)")
plt.title("Average Length by different cost function weights")
plt.xticks(rotation=45)
plt.grid()
plt.tight_layout()
plt.show()


# Visualise the lower priority pipe's decrease in installability
all_dfs = pd.concat(dfs_by_name.values())
priority_grouped = all_dfs.groupby(["Installability weight", "Priority"])["Install score"].mean().unstack()

# Plotting the grouped data as a line plot to ensure the x-axis is numerical
priority_grouped.plot(kind='line', marker='o', figsize=(12, 7))
plt.plot(x_smooth, polynomial_II(x_smooth),'r--', label='Installability index polynomial fit')
plt.xlabel("Installability weight in cost function")
plt.ylabel("Average Installability Score")
plt.title("Average Installability Score by Pipe Priority and Weight")
plt.legend(title="Priority", bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, linestyle='--', alpha=0.7)
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




#%% II and TM correlation analysis

correlations = {}
for df_name, df in dfs_by_name.items():
    weight = df["Installability weight"].iloc[0]
    II_vals = df["Install score"]
    TM_vals = df["Time mult"].str.replace("×", "").astype(float)
    correlation = II_vals.corr(TM_vals)
    correlations[weight] = correlation**2
    print(f"Pearson correlation squared for weight {weight}: {correlation**2:.5f}")

# Sort correlations by weight for plotting
sorted_weights = sorted(correlations.keys())
sorted_corr = [correlations[w] for w in sorted_weights]

plt.figure()
plt.plot(sorted_weights, sorted_corr, marker='o', label='Pearson correlation squared')
plt.grid(True)
plt.xlabel("Installability weight in cost function")
plt.ylabel("Pearson correlation (R^2)")
plt.title("R^2 Correlation: Installability index vs. Time Multiplier")
plt.show()