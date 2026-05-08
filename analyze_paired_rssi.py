#!/usr/bin/env python3
"""
analyze_paired_rssi.py

Offline analysis for the PAIR rows printed by rssi_probe_device.py.

What it computes:
- mean offset between network-side RSSI and device-side RSSI
- optional RSSI offset calibration
- Moving Window Averaging (MWA)
- adaptive guard-band quantization
- usable bit count
- discard rate
- Bit Disagreement Rate (BDR)
- binary entropy and min-entropy
- a parameter sweep over MWA window and threshold alpha

Usage:
  python analyze_paired_rssi.py paired_device_log.txt --out results
  python analyze_paired_rssi.py paired_device_log.txt --windows 1,3,5,9,15 --alphas 0.25,0.5,0.75,1.0

The input can be raw serial text. Lines not starting with "PAIR," are ignored.
"""

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd


PAIR_COLUMNS = [
    "marker", "run_id", "env", "seq", "distance_cm", "freq_mhz", "sf",
    "bw_khz", "cr", "tx_power_dbm", "t_req_ms", "t_resp_ms",
    "rssi_network", "snr_network", "rssi_device", "snr_device",
    "payload_len", "ok",
]


def load_pair_log(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("PAIR,"):
                continue
            parts = next(csv.reader([line]))
            if len(parts) != len(PAIR_COLUMNS):
                # Skip malformed/debug-truncated rows
                continue
            rows.append(parts)

    if not rows:
        raise SystemExit("No PAIR rows found. Did you capture serial output from rssi_probe_device.py?")

    df = pd.DataFrame(rows, columns=PAIR_COLUMNS)
    for col in ["seq", "distance_cm", "freq_mhz", "sf", "bw_khz", "tx_power_dbm",
                "t_req_ms", "t_resp_ms", "rssi_network", "snr_network",
                "rssi_device", "snr_device", "payload_len", "ok"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df["ok"] == 1].copy()
    df = df.dropna(subset=["seq", "rssi_network", "rssi_device"])
    df = df.sort_values(["run_id", "env", "distance_cm", "seq"]).reset_index(drop=True)
    return df


def moving_average(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x.astype(float)
    return pd.Series(x.astype(float)).rolling(window=window, min_periods=1).mean().to_numpy()


def adaptive_quantize_blocks(x: np.ndarray, block_size: int, alpha: float):
    """
    Per-block adaptive guard-band quantizer.
    Above mean + alpha*std => 1
    Below mean - alpha*std => 0
    Inside guard band => NaN/discard

    This mirrors the physical-layer key generation idea:
    keep confident high/low RSSI samples, discard uncertain samples.
    """
    bits = np.full(len(x), np.nan)
    for start in range(0, len(x), block_size):
        end = min(start + block_size, len(x))
        block = x[start:end]
        if len(block) < 2:
            continue
        mu = float(np.mean(block))
        sigma = float(np.std(block))
        if sigma == 0:
            continue
        hi = mu + alpha * sigma
        lo = mu - alpha * sigma
        bits[start:end][block > hi] = 1
        bits[start:end][block < lo] = 0
    return bits


def bit_entropy(bits: np.ndarray):
    bits = bits[~np.isnan(bits)]
    if len(bits) == 0:
        return 0.0, 0.0, np.nan, np.nan
    p1 = float(np.mean(bits))
    p0 = 1.0 - p1
    h = 0.0
    for p in (p0, p1):
        if p > 0:
            h -= p * math.log2(p)
    min_h = -math.log2(max(p0, p1)) if max(p0, p1) > 0 else 0.0
    return h, min_h, p0, p1


def analyze_group(g: pd.DataFrame, window: int, block_size: int, alpha: float, calibrate_offset: bool):
    r_net = g["rssi_network"].to_numpy(dtype=float)
    r_dev = g["rssi_device"].to_numpy(dtype=float)

    # Hardware / direction calibration:
    # Uplink RSSI at Network and downlink RSSI at Device often have a constant offset.
    # For key-generation analysis, compare variations by aligning means.
    offset = float(np.mean(r_dev - r_net))
    if calibrate_offset:
        r_net = r_net + offset

    r_net_mwa = moving_average(r_net, window)
    r_dev_mwa = moving_average(r_dev, window)

    b_net = adaptive_quantize_blocks(r_net_mwa, block_size, alpha)
    b_dev = adaptive_quantize_blocks(r_dev_mwa, block_size, alpha)

    usable_mask = (~np.isnan(b_net)) & (~np.isnan(b_dev))
    usable = int(np.sum(usable_mask))
    total = int(len(g))

    if usable > 0:
        mismatches = int(np.sum(b_net[usable_mask] != b_dev[usable_mask]))
        bdr = mismatches / usable
        # Use one side's retained bits for entropy estimate
        h, min_h, p0, p1 = bit_entropy(b_dev[usable_mask])
    else:
        mismatches = 0
        bdr = np.nan
        h, min_h, p0, p1 = 0.0, 0.0, np.nan, np.nan

    duration_s = (float(g["t_resp_ms"].max()) - float(g["t_req_ms"].min())) / 1000.0
    kgr_bps = usable / duration_s if duration_s > 0 else np.nan

    return {
        "run_id": g["run_id"].iloc[0],
        "env": g["env"].iloc[0],
        "distance_cm": g["distance_cm"].iloc[0],
        "freq_mhz": g["freq_mhz"].iloc[0],
        "n_pairs": total,
        "window": window,
        "block_size": block_size,
        "alpha": alpha,
        "calibrate_offset": calibrate_offset,
        "mean_offset_device_minus_network_db": offset,
        "usable_bits": usable,
        "discard_rate": 1.0 - (usable / total if total else 0.0),
        "mismatches": mismatches,
        "bdr": bdr,
        "entropy_bits_per_bit": h,
        "min_entropy_bits_per_bit": min_h,
        "p0": p0,
        "p1": p1,
        "kgr_bps_before_reconciliation": kgr_bps,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Raw serial log or text file containing PAIR rows")
    ap.add_argument("--out", type=Path, default=Path("results"), help="Output folder")
    ap.add_argument("--windows", default="1,3,5,9,15,21", help="Comma-separated MWA windows")
    ap.add_argument("--alphas", default="0.25,0.5,0.75,1.0", help="Comma-separated threshold multipliers")
    ap.add_argument("--block-size", type=int, default=50, help="Block size for adaptive quantization")
    ap.add_argument("--no-calibrate-offset", action="store_true",
                    help="Do not align network/device RSSI means before quantization")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    df = load_pair_log(args.input)
    paired_csv = args.out / "paired_clean.csv"
    df.to_csv(paired_csv, index=False)

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    alphas = [float(x.strip()) for x in args.alphas.split(",") if x.strip()]
    calibrate = not args.no_calibrate_offset

    rows = []
    group_cols = ["run_id", "env", "distance_cm", "freq_mhz"]
    for _, g in df.groupby(group_cols, dropna=False):
        for w in windows:
            for a in alphas:
                rows.append(analyze_group(g, w, args.block_size, a, calibrate))

    summary = pd.DataFrame(rows)
    summary_csv = args.out / "mwa_quantization_sweep.csv"
    summary.to_csv(summary_csv, index=False)

    # Choose a practical "best": low BDR first, then more usable bits, then higher entropy.
    ranked = summary.dropna(subset=["bdr"]).copy()
    if not ranked.empty:
        ranked = ranked.sort_values(
            by=["bdr", "usable_bits", "entropy_bits_per_bit"],
            ascending=[True, False, False]
        )
        best = ranked.iloc[0]
        best_txt = args.out / "best_parameters.txt"
        best_txt.write_text(best.to_string(), encoding="utf-8")
        print("\nBest parameter candidate:")
        print(best.to_string())

    print("\nSaved:")
    print(" -", paired_csv)
    print(" -", summary_csv)
    if not ranked.empty:
        print(" -", args.out / "best_parameters.txt")


if __name__ == "__main__":
    main()
