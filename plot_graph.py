import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv("rssi_scan.csv")

# Coerce types
for col in ["rssi_dbm", "snr_db", "freq_mhz", "t_ms"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df["sweep"] = pd.to_numeric(df.get("sweep", 0), errors="coerce").fillna(0).astype(int)

# Treat -200 as missing (no packet)
df_valid = df.copy()
df_valid.loc[df_valid["rssi_dbm"] <= -199, "rssi_dbm"] = np.nan

# 1) Each sweep
plt.figure()
for sweep_id, g in df_valid.groupby("sweep"):
    g = g.sort_values("freq_mhz")
    plt.plot(g["freq_mhz"], g["rssi_dbm"], marker="o", label=f"Sweep {sweep_id+1}")
plt.xlabel("Frequency (MHz)")
plt.ylabel("RSSI (dBm)")
plt.title("RSSI vs Frequency (each sweep)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig("rssi_vs_freq_each_sweep.png", dpi=200)

# 2) Mean ± std
agg = df_valid.groupby("freq_mhz").agg(
    mean_rssi=("rssi_dbm", "mean"),
    std_rssi=("rssi_dbm", "std"),
    n=("rssi_dbm", "count")
).reset_index().sort_values("freq_mhz")

plt.figure()
plt.errorbar(agg["freq_mhz"], agg["mean_rssi"], yerr=agg["std_rssi"], fmt="o-", capsize=3)
plt.xlabel("Frequency (MHz)")
plt.ylabel("RSSI (dBm)")
plt.title("RSSI vs Frequency (mean ± std across sweeps)")
plt.grid(True)
plt.tight_layout()
plt.savefig("rssi_vs_freq_mean_std.png", dpi=200)

# 3) Missing rate
miss = df.groupby("freq_mhz").agg(
    total=("rssi_dbm", "size"),
    missing=("rssi_dbm", lambda x: int((pd.to_numeric(x, errors="coerce") <= -199).sum()))
).reset_index().sort_values("freq_mhz")
miss["missing_rate"] = miss["missing"] / miss["total"]

plt.figure()
plt.plot(miss["freq_mhz"], miss["missing_rate"], marker="o")
plt.xlabel("Frequency (MHz)")
plt.ylabel("Missing rate (fraction)")
plt.title("Packet-miss rate vs Frequency (RSSI=-200 treated as missing)")
plt.grid(True)
plt.tight_layout()
plt.savefig("missing_rate_vs_freq.png", dpi=200)

plt.show()
