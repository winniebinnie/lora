#!/usr/bin/env python3
"""
analyze_calibration_study.py

Calibration-study analyzer for PAIR rows printed by rssi_probe_device.py.

Compares:
1) none       = no RSSI offset correction
2) full       = offset estimated from the whole dataset, optimistic offline upper bound
3) online_N   = offset estimated from first N successful pairs; those N pairs are excluded from key generation

Example:
  py analyze_calibration_study.py datasets/raw/run01_indoor_static_100cm_device.csv --out datasets/processed/run01_calibration_study
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
                continue
            rows.append(parts)

    if not rows:
        raise SystemExit("No PAIR rows found. Did you capture serial output from rssi_probe_device.py?")

    df = pd.DataFrame(rows, columns=PAIR_COLUMNS)
    numeric_cols = [
        "seq", "distance_cm", "freq_mhz", "sf", "bw_khz", "tx_power_dbm",
        "t_req_ms", "t_resp_ms", "rssi_network", "snr_network",
        "rssi_device", "snr_device", "payload_len", "ok",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[df["ok"] == 1].copy()
    df = df.dropna(subset=["seq", "rssi_network", "rssi_device"])
    df = df.sort_values(["run_id", "env", "distance_cm", "seq"]).reset_index(drop=True)
    return df


def moving_average(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x.astype(float)
    return pd.Series(x.astype(float)).rolling(window=window, min_periods=1).mean().to_numpy()


def adaptive_quantize_blocks(x: np.ndarray, block_size: int, alpha: float) -> np.ndarray:
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
        block_bits = bits[start:end]
        block_bits[block > hi] = 1
        block_bits[block < lo] = 0
        bits[start:end] = block_bits
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


def select_keygen_group(g: pd.DataFrame, calibration_mode: str, online_cal_pairs: int):
    r_net_all = g["rssi_network"].to_numpy(dtype=float)
    r_dev_all = g["rssi_device"].to_numpy(dtype=float)

    if calibration_mode == "none":
        return g.copy(), 0.0, 0, "no offset correction"

    if calibration_mode == "full":
        offset = float(np.mean(r_dev_all - r_net_all))
        return g.copy(), offset, 0, "offline full-dataset offset calibration"

    if calibration_mode == "online":
        if len(g) <= online_cal_pairs:
            return g.iloc[0:0].copy(), np.nan, len(g), "not enough rows for online calibration"
        cal = g.iloc[:online_cal_pairs]
        keygen = g.iloc[online_cal_pairs:].copy()
        offset = float(np.mean(cal["rssi_device"].to_numpy(dtype=float) -
                               cal["rssi_network"].to_numpy(dtype=float)))
        return keygen, offset, online_cal_pairs, f"online offset from first {online_cal_pairs} pairs"

    raise ValueError(f"Unknown calibration mode: {calibration_mode}")


def analyze_group(g, window, block_size, alpha, calibration_mode, online_cal_pairs):
    keygen_g, offset, n_cal, calibration_note = select_keygen_group(g, calibration_mode, online_cal_pairs)
    mode_label = calibration_mode if calibration_mode != "online" else f"online_{online_cal_pairs}"

    base = {
        "run_id": g["run_id"].iloc[0],
        "env": g["env"].iloc[0],
        "distance_cm": g["distance_cm"].iloc[0],
        "freq_mhz": g["freq_mhz"].iloc[0],
        "calibration_mode": mode_label,
        "calibration_note": calibration_note,
        "n_total_pairs": int(len(g)),
        "n_calibration_pairs": int(n_cal),
        "n_keygen_pairs": int(len(keygen_g)),
        "window": window,
        "block_size": block_size,
        "alpha": alpha,
        "offset_device_minus_network_db": offset,
    }

    if len(keygen_g) == 0:
        base.update({
            "usable_bits": 0, "discard_rate": np.nan, "mismatches": 0, "bdr": np.nan,
            "entropy_bits_per_bit": 0.0, "min_entropy_bits_per_bit": 0.0,
            "p0": np.nan, "p1": np.nan, "kgr_bps_before_reconciliation": np.nan,
            "estimated_min_entropy_bits_total": 0.0,
        })
        return base

    r_net = keygen_g["rssi_network"].to_numpy(dtype=float)
    r_dev = keygen_g["rssi_device"].to_numpy(dtype=float)

    if calibration_mode in ("full", "online"):
        r_net = r_net + offset

    r_net_mwa = moving_average(r_net, window)
    r_dev_mwa = moving_average(r_dev, window)

    b_net = adaptive_quantize_blocks(r_net_mwa, block_size, alpha)
    b_dev = adaptive_quantize_blocks(r_dev_mwa, block_size, alpha)

    usable_mask = (~np.isnan(b_net)) & (~np.isnan(b_dev))
    usable = int(np.sum(usable_mask))
    total_keygen = int(len(keygen_g))

    if usable > 0:
        mismatches = int(np.sum(b_net[usable_mask] != b_dev[usable_mask]))
        bdr = mismatches / usable
        h, min_h, p0, p1 = bit_entropy(b_dev[usable_mask])
        estimated_min_entropy_total = usable * min_h
    else:
        mismatches = 0
        bdr = np.nan
        h, min_h, p0, p1 = 0.0, 0.0, np.nan, np.nan
        estimated_min_entropy_total = 0.0

    duration_s = (float(keygen_g["t_resp_ms"].max()) - float(keygen_g["t_req_ms"].min())) / 1000.0
    kgr_bps = usable / duration_s if duration_s > 0 else np.nan

    base.update({
        "usable_bits": usable,
        "discard_rate": 1.0 - (usable / total_keygen if total_keygen else 0.0),
        "mismatches": mismatches,
        "bdr": bdr,
        "entropy_bits_per_bit": h,
        "min_entropy_bits_per_bit": min_h,
        "p0": p0,
        "p1": p1,
        "kgr_bps_before_reconciliation": kgr_bps,
        "estimated_min_entropy_bits_total": estimated_min_entropy_total,
    })
    return base


def choose_best(summary: pd.DataFrame, min_usable_bits: int) -> pd.DataFrame:
    ranked = summary.dropna(subset=["bdr"]).copy()
    if ranked.empty:
        return ranked

    practical = ranked[ranked["usable_bits"] >= min_usable_bits].copy()
    if practical.empty:
        practical = ranked.copy()

    practical = practical.sort_values(
        by=["bdr", "usable_bits", "estimated_min_entropy_bits_total", "discard_rate"],
        ascending=[True, False, False, True],
    )
    return practical


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Raw serial log or text file containing PAIR rows")
    ap.add_argument("--out", type=Path, default=Path("results"), help="Output folder")
    ap.add_argument("--windows", default="1,3,5,9,15,21", help="Comma-separated MWA windows")
    ap.add_argument("--alphas", default="0.25,0.5,0.75,1.0", help="Comma-separated threshold multipliers")
    ap.add_argument("--block-size", type=int, default=50, help="Block size for adaptive quantization")
    ap.add_argument("--online-cal-pairs", type=int, default=100, help="Initial pairs used only for online calibration")
    ap.add_argument("--min-usable-bits", type=int, default=128, help="Minimum useful bits for practical ranking")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    df = load_pair_log(args.input)
    paired_csv = args.out / "paired_clean.csv"
    df.to_csv(paired_csv, index=False)

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    alphas = [float(x.strip()) for x in args.alphas.split(",") if x.strip()]

    rows = []
    group_cols = ["run_id", "env", "distance_cm", "freq_mhz"]
    modes = ["none", "full", "online"]

    for _, g in df.groupby(group_cols, dropna=False):
        for mode in modes:
            for w in windows:
                for a in alphas:
                    rows.append(analyze_group(
                        g=g,
                        window=w,
                        block_size=args.block_size,
                        alpha=a,
                        calibration_mode=mode,
                        online_cal_pairs=args.online_cal_pairs,
                    ))

    summary = pd.DataFrame(rows)
    all_csv = args.out / "calibration_sweep_all.csv"
    summary.to_csv(all_csv, index=False)

    best_rows = []
    for mode, s in summary.groupby("calibration_mode"):
        best = choose_best(s, args.min_usable_bits)
        if not best.empty:
            best_rows.append(best.iloc[0])

    best_by_mode = pd.DataFrame(best_rows)
    best_by_mode_csv = args.out / "best_by_mode.csv"
    best_by_mode.to_csv(best_by_mode_csv, index=False)

    overall = choose_best(best_by_mode, args.min_usable_bits)
    overall_txt = args.out / "best_overall_practical.txt"
    if not overall.empty:
        overall_txt.write_text(overall.iloc[0].to_string(), encoding="utf-8")

    md = []
    md.append("# Calibration Study Summary\n")
    md.append(f"Input file: `{args.input}`\n")
    md.append(f"Online calibration pairs: `{args.online_cal_pairs}`\n")
    md.append(f"Minimum usable bits for practical ranking: `{args.min_usable_bits}`\n")
    md.append("\n## Best candidate by calibration mode\n")
    if not best_by_mode.empty:
        cols = [
            "calibration_mode", "n_total_pairs", "n_calibration_pairs", "n_keygen_pairs",
            "window", "alpha", "offset_device_minus_network_db", "usable_bits",
            "discard_rate", "mismatches", "bdr", "entropy_bits_per_bit",
            "min_entropy_bits_per_bit", "estimated_min_entropy_bits_total",
            "kgr_bps_before_reconciliation",
        ]
        md.append(best_by_mode[cols].to_markdown(index=False))
    else:
        md.append("No valid candidates found.")
    md.append("\n\n## Notes\n")
    md.append("- `none` is the no-calibration baseline.\n")
    md.append("- `full` is an optimistic offline upper bound because it estimates offset from the whole dataset.\n")
    md.append("- `online_N` is the deployable-style mode: first N pairs calibrate offset; remaining pairs generate bits.\n")

    summary_md = args.out / "calibration_summary.md"
    summary_md.write_text("\n".join(md), encoding="utf-8")

    print("\nSaved:")
    print(" -", paired_csv)
    print(" -", all_csv)
    print(" -", best_by_mode_csv)
    print(" -", overall_txt)
    print(" -", summary_md)

    if not best_by_mode.empty:
        print("\nBest by calibration mode:")
        print(best_by_mode[[
            "calibration_mode", "window", "alpha", "usable_bits",
            "discard_rate", "bdr", "entropy_bits_per_bit",
            "min_entropy_bits_per_bit", "kgr_bps_before_reconciliation",
        ]].to_string(index=False))


if __name__ == "__main__":
    main()
