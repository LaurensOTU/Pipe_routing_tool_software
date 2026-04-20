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



plt.figure()
for df_name, df in dfs_by_name.items():
    avg_II = df["Install score"].mean()
    plt.scatter(df["Installability weight"][0], avg_II)
plt.xlabel("Installability weight")
plt.ylabel("Average Installability Score")
plt.title("Average Installability Score by different cost function weights")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

plt.figure()
for df_name, df in dfs_by_name.items():
    stripped_TM_col = df["Time mult"].str.replace("×", "").astype(float)
    avg_TM = stripped_TM_col.mean()
    plt.scatter(df["Installability weight"][0], avg_TM)
plt.xlabel("Installability weight")
plt.ylabel("Average Time Multipliler Score")
plt.title("Average Time Multiplier by different cost function weights")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()