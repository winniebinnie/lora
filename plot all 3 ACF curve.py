import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import math

def acf_fft_unbiased(x, max_lag):
    x = np.asarray(x, dtype=float)
    x = x - np.mean(x)
    n = len(x)
    max_lag = min(max_lag, n - 1)

    f = np.fft.rfft(x, n=2*n)
    p = f * np.conjugate(f)
    ac = np.fft.irfft(p)[:n]

    ac = ac / np.arange(n, 0, -1)   # unbiased (n-k)
    ac = ac / ac[0]                 # normalize so acf[0]=1
    return ac[:max_lag+1]

def estimate_dt_ms(t_ms):
    diffs = np.diff(t_ms.astype(float))
    diffs = diffs[diffs > 0]
    return float(np.median(diffs))

files = [
    ("rssi_920.csv", "920 MHz"),
    ("rssi_922.csv", "922 MHz"),
    ("rssi_924.csv", "924 MHz"),
]

plt.figure()

for path, label in files:
    df = pd.read_csv(path)
    x = df["rssi_dbm"].to_numpy()
    dt_ms = estimate_dt_ms(df["t_ms"].to_numpy())

    max_lag = int(min(len(x) - 1, round(15000 / dt_ms)))  # plot up to ~15s of lag
    ac = acf_fft_unbiased(x, max_lag=max_lag)
    lags_ms = np.arange(len(ac)) * dt_ms

    plt.plot(lags_ms, ac, label=f"{label} (dt≈{dt_ms:.0f} ms)")

# Optional reference lines
plt.axhline(0.5, linestyle="--", linewidth=1)
plt.axhline(1/math.e, linestyle="--", linewidth=1)
plt.axhline(0.0, linestyle="--", linewidth=1)

plt.xlabel("Lag (ms)")
plt.ylabel("Autocorrelation (normalized)")
plt.title("RSSI Autocorrelation (ACF) — 920 vs 922 vs 924 MHz")
plt.ylim(-0.25, 1.05)
plt.xlim(-1000, 10000)
plt.grid(True, alpha=0.3)
plt.legend()
plt.show()
