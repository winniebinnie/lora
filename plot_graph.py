import csv
import math
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FuncFormatter

freq = []
rssi = []
t_s  = []
snr  = []

with open("rssi_scan.csv", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        freq.append(float(row["freq_mhz"]))
        rssi.append(float(row["rssi_dbm"]))
        t_s.append(float(row["t_ms"]) / 1000.0)
        snr.append(float(row.get("snr_db", 0.0)))

def nice_ylim(values, pad=0.5):
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return vmin - 1, vmax + 1
    return (math.floor(vmin - pad), math.ceil(vmax + pad))

mean_rssi = sum(rssi) / len(rssi)
ymin, ymax = nice_ylim(rssi, pad=0.6)

# -------- Plot 1: RSSI vs Frequency --------
plt.figure()
plt.plot(freq, rssi, marker="o")
plt.axhline(mean_rssi, linestyle="--", linewidth=1, label=f"Mean = {mean_rssi:.2f} dBm")

plt.xlabel("Frequency (MHz)")
plt.ylabel("RSSI (dBm)")
plt.title("RSSI vs Frequency (Chirp Sweep)")
plt.grid(True)

# Zoom Y scale (this is the main change)
plt.ylim(ymin, ymax)
plt.gca().yaxis.set_major_locator(MultipleLocator(1))   # 1 dB ticks
# If you want 0.5 dB ticks instead, use:
# plt.gca().yaxis.set_major_locator(MultipleLocator(0.5))

# Make frequency axis cleaner (e.g., show 2 decimals)
plt.gca().xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.2f}"))

plt.legend()
plt.tight_layout()

# Same zoomed Y scale for easy comparison
plt.ylim(ymin, ymax)
plt.gca().yaxis.set_major_locator(MultipleLocator(1))

plt.legend()
plt.tight_layout()

plt.show()
