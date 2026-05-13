#!/usr/bin/env python3
"""
run_probe_count_sweep.py

Easy probe-count sweep for the RSSI-bound EDHOC thesis experiment.

It does 4 things for each probe-count size:
1. Creates a subset of the raw PAIR log / paired_clean.csv.
2. Runs derive_kauth_with_reconciliation.py on that subset.
3. Runs edhoc_bootstrap_experiment.py on the reconciliation JSON.
4. Aggregates all results into one CSV + Markdown table.

Recommended first run:
  py run_probe_count_sweep.py datasets/raw/run04_outdoor_los_100cm_device.csv --sizes 200,300,500,700,900,987 --out datasets/processed/probe_sweep_run04

Note:
- derive_kauth_with_reconciliation.py defaults to --online-cal-pairs 100.
- Therefore sizes below 200 are usually not useful unless you reduce --online-cal-pairs.
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

PAIR_PREFIX = "PAIR,"


def parse_sizes(text: str) -> list[int]:
    sizes = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        sizes.append(int(part))
    return sizes


def count_pair_rows(path: Path) -> int:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if any(line.startswith(PAIR_PREFIX) for line in lines):
        return sum(1 for line in lines if line.startswith(PAIR_PREFIX))
    # Treat as CSV with header if no raw PAIR lines.
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return 0
    return max(0, len(rows) - 1)


def make_subset(input_path: Path, out_path: Path, n_pairs: int) -> int:
    """Create a subset file with the first n PAIR rows or first n CSV rows."""
    lines = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if any(line.startswith(PAIR_PREFIX) for line in lines):
        pair_lines = [line for line in lines if line.startswith(PAIR_PREFIX)]
        subset = pair_lines[:n_pairs]
        out_path.write_text("\n".join(subset) + "\n", encoding="utf-8")
        return len(subset)

    # CSV mode. Preserve header and first n data rows.
    with input_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = list(csv.reader(f))
    if not reader:
        raise SystemExit(f"Input is empty: {input_path}")
    header = reader[0]
    data = reader[1:1+n_pairs]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    return len(data)


def run_cmd(cmd: list[str]) -> None:
    print("\n$ " + " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def safe_get(d, path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def pct(x):
    if x is None:
        return ""
    return f"{100*x:.2f}%"


def fmt_float(x, digits=2):
    if x is None:
        return ""
    return f"{x:.{digits}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Raw PAIR log or paired_clean.csv, e.g. datasets/raw/run04_outdoor_los_100cm_device.csv")
    ap.add_argument("--sizes", default="200,300,500,700,900,987", help="Comma-separated TOTAL probe pairs to test")
    ap.add_argument("--out", type=Path, default=Path("datasets/processed/probe_sweep_run04"), help="Output folder")
    ap.add_argument("--window", type=int, default=21)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--block-size", type=int, default=50)
    ap.add_argument("--online-cal-pairs", type=int, default=100)
    ap.add_argument("--recon-block-size", type=int, default=16)
    ap.add_argument("--recon-passes", type=int, default=4)
    ap.add_argument("--target-security-bits", type=int, default=128)
    ap.add_argument("--derive-script", type=Path, default=Path("derive_kauth_with_reconciliation.py"))
    ap.add_argument("--edhoc-script", type=Path, default=Path("edhoc_bootstrap_experiment.py"))
    args = ap.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input dataset not found: {args.input}")
    if not args.derive_script.exists():
        raise SystemExit(f"Missing script: {args.derive_script}")
    if not args.edhoc_script.exists():
        raise SystemExit(f"Missing script: {args.edhoc_script}")

    total_available = count_pair_rows(args.input)
    sizes = [s for s in parse_sizes(args.sizes) if s <= total_available]
    skipped = [s for s in parse_sizes(args.sizes) if s > total_available]

    args.out.mkdir(parents=True, exist_ok=True)
    subsets_dir = args.out / "subsets"
    recon_dir = args.out / "reconciliation"
    edhoc_dir = args.out / "edhoc"

    print(f"Input: {args.input}")
    print(f"Available pair rows: {total_available}")
    print(f"Testing sizes: {sizes}")
    if skipped:
        print(f"Skipping sizes larger than available rows: {skipped}")

    rows = []

    for n in sizes:
        label = f"{n}pairs"
        subset_path = subsets_dir / f"subset_{label}.csv"
        actual = make_subset(args.input, subset_path, n)
        print(f"\nCreated subset: {subset_path} ({actual} pairs)")

        recon_out = recon_dir / f"recon_{label}"
        edhoc_out = edhoc_dir / f"edhoc_{label}"

        run_cmd([
            sys.executable, str(args.derive_script), str(subset_path),
            "--out", str(recon_out),
            "--window", str(args.window),
            "--alpha", str(args.alpha),
            "--block-size", str(args.block_size),
            "--online-cal-pairs", str(args.online_cal_pairs),
            "--recon-block-size", str(args.recon_block_size),
            "--recon-passes", str(args.recon_passes),
        ])

        rssi_json = recon_out / "reconciliation_demo_result.json"
        run_cmd([
            sys.executable, str(args.edhoc_script),
            "--rssi-result", str(rssi_json),
            "--out", str(edhoc_out),
            "--target-security-bits", str(args.target_security_bits),
        ])

        recon = json.loads(rssi_json.read_text(encoding="utf-8"))
        edhoc_json = json.loads((edhoc_out / "edhoc_bootstrap_result.json").read_text(encoding="utf-8"))

        rssi_stage = edhoc_json.get("rssi_stage", {})
        bound = edhoc_json.get("rssi_bound_edhoc", {})

        rows.append({
            "probe_pairs_total": n,
            "keygen_pairs": recon.get("n_keygen_pairs"),
            "usable_bits": recon.get("usable_bits"),
            "bdr_before_reconciliation": recon.get("bdr_before_reconciliation"),
            "bdr_after_reconciliation": recon.get("bdr_after_reconciliation"),
            "mismatches_after_reconciliation": recon.get("mismatches_after_reconciliation"),
            "parity_checks_revealed": safe_get(recon, ["reconciliation_stats", "parity_checks_revealed"]),
            "post_leakage_min_entropy_bits": rssi_stage.get("estimated_min_entropy_after_leakage"),
            "enough_for_128bit_target": rssi_stage.get("enough_entropy_for_target_security_bits"),
            "kauth_match": recon.get("kauth_match"),
            "tag_match": bound.get("tag_match"),
            "wrong_kauth_rejected": bound.get("wrong_kauth_rejected"),
            "tampered_transcript_rejected": bound.get("tampered_transcript_rejected"),
            "bound_session_key_match": bound.get("bound_session_key_match"),
            "functional_success": bound.get("functional_success"),
            "total_toa_ms_with_rssi_probes": bound.get("total_toa_ms_est_with_rssi_probes"),
            "edhoc_result_folder": str(edhoc_out),
        })

    # Write CSV.
    csv_path = args.out / "probe_count_sweep_results.csv"
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # Write Markdown.
    md_path = args.out / "probe_count_sweep_results.md"
    md = []
    md.append("# Probe-Count Sweep Results\n")
    md.append(f"- Input dataset: `{args.input}`")
    md.append(f"- Available pair rows: `{total_available}`")
    md.append(f"- Online calibration pairs per subset: `{args.online_cal_pairs}`")
    md.append(f"- MWA window: `{args.window}`")
    md.append(f"- Alpha: `{args.alpha}`")
    md.append(f"- Quantization block size: `{args.block_size}`")
    md.append(f"- Target security bits: `{args.target_security_bits}`")
    md.append("")
    md.append("| Total probe pairs | Keygen pairs | Usable bits | BDR before | BDR after | Post-leakage min-entropy | K_auth match | Tag match | Wrong K_auth rejected | Tampered transcript rejected | Functional success | 128-bit target met? | Total ToA incl. probes |")
    md.append("|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---:|")
    for r in rows:
        md.append(
            f"| {r['probe_pairs_total']} | {r['keygen_pairs']} | {r['usable_bits']} | "
            f"{pct(r['bdr_before_reconciliation'])} | {pct(r['bdr_after_reconciliation'])} | "
            f"{fmt_float(r['post_leakage_min_entropy_bits'])} | "
            f"{r['kauth_match']} | {r['tag_match']} | {r['wrong_kauth_rejected']} | "
            f"{r['tampered_transcript_rejected']} | {r['functional_success']} | "
            f"{r['enough_for_128bit_target']} | {fmt_float(r['total_toa_ms_with_rssi_probes'])} ms |"
        )

    md.append("\n## How to interpret this table\n")
    md.append("- `Functional success = True` means the RSSI-bound EDHOC pipeline worked.")
    md.append("- `128-bit target met = True` is required before claiming full 128-bit security.")
    md.append("- If functional success is true but the 128-bit target is false, the result supports feasibility but not the full security target yet.")
    md.append("- The best practical point is the smallest probe count that gives functional success and meets the entropy target.")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\nDone.")
    print("Saved:")
    print(" -", csv_path)
    print(" -", md_path)


if __name__ == "__main__":
    main()
