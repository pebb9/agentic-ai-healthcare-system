# scripts/02_prepare_probes.py
"""
02_prepare_probes.py - Prepare probes

"""

import json
import pandas as pd

INPUT = "data/Healthcare_clean.csv"
PROBE_IN_OUT_TOTAL = 200
RANDOM_STATE = 42

df = pd.read_csv(INPUT)

disease_freq = df["Disease"].value_counts()
median_freq = disease_freq.median()
rare_diseases = set(disease_freq[disease_freq < median_freq].index)

probe_df = df.sample(n=PROBE_IN_OUT_TOTAL, random_state=RANDOM_STATE).copy()

probe_in = probe_df[probe_df["Disease"].isin(rare_diseases)].copy().head(100)
probe_out = probe_df[~probe_df["Disease"].isin(rare_diseases)].copy().head(100)

probe_in.to_csv("data/probe_in.csv", index=False)
probe_out.to_csv("data/probe_out.csv", index=False)

labels = {
    "median_frequency_threshold": float(median_freq),
    "rare_diseases": sorted(list(rare_diseases)),
    "probe_in_size": int(len(probe_in)),
    "probe_out_size": int(len(probe_out)),
    "random_state": RANDOM_STATE,
    "disease_frequencies": disease_freq.to_dict(),
}

with open("data/probe_labels.json", "w") as f:
    json.dump(labels, f, indent=2)

print("Saved → data/probe_in.csv")
print("Saved → data/probe_out.csv")
print("Saved → data/probe_labels.json")
print(f"Probe-in: {len(probe_in)} | Probe-out: {len(probe_out)} | Median freq: {median_freq}")