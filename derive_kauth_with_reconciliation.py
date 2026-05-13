#!/usr/bin/env python3
"""
derive_kauth_with_reconciliation.py

Prototype pipeline with a simple deployable-style reconciliation simulation:

PAIR log / paired_clean.csv
 -> online calibration
 -> MWA
 -> adaptive quantization
 -> preliminary device/network bitstrings
 -> simple block-parity reconciliation simulation
 -> HKDF K_auth
 -> EDHOC-style HMAC binding tag

Why this exists:
- The earlier derive_kauth_from_rssi.py used "oracle" reconciliation, which is useful
  for proving the RSSI -> K_auth -> tag pipeline, but not deployable.
- This script replaces the oracle step with a simple block-parity method.
- This is still a simplified prototype, not full Cascade, but it is much closer to a
  real reconciliation method than dropping known mismatches.

Model:
- Device is treated as the reference bitstring.
- Network corrects its bitstring using parity comparisons.
- Public leakage is estimated as the number of parity bits revealed.
- After reconciliation, privacy amplification is modeled by HKDF.

Limitations:
- A block parity mismatch can locate/correct one odd error in a block using binary search.
- Blocks with even numbers of errors are not detected in that pass.
- Multiple passes with deterministic permutations are used to improve correction.
- This is a prototype for thesis exploration, not a final formal protocol.

Examples:
  py derive_kauth_with_reconciliation.py datasets/raw/run04_outdoor_los_100cm_device.csv --out datasets/processed/run04_recon_demo --window 21 --alpha 1.0

  py derive_kauth_with_reconciliation.py datasets/raw/run02_indoor_static_100cm_device.csv --out datasets/processed/run02_recon_demo --window 21 --alpha 0.75
"""

import argparse
import csv
import hashlib
import hmac
import json
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
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    has_pair_lines = any(line.startswith("PAIR,") for line in text)

    if has_pair_lines:
        rows = []
        for line in text:
            line = line.strip()
            if not line.startswith("PAIR,"):
                continue
            parts = next(csv.reader([line]))
            if len(parts) == len(PAIR_COLUMNS):
                rows.append(parts)
        if not rows:
            raise SystemExit("No valid PAIR rows found.")
        df = pd.DataFrame(rows, columns=PAIR_COLUMNS)
    else:
        df = pd.read_csv(path)

    for col in [
        "seq", "distance_cm", "freq_mhz", "sf", "bw_khz", "tx_power_dbm",
        "t_req_ms", "t_resp_ms", "rssi_network", "snr_network",
        "rssi_device", "snr_device", "payload_len", "ok",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "ok" in df.columns:
        df = df[df["ok"] == 1].copy()

    df = df.dropna(subset=["seq", "rssi_network", "rssi_device"])
    df = df.sort_values(["run_id", "env", "distance_cm", "seq"]).reset_index(drop=True)
    if df.empty:
        raise SystemExit("No usable paired rows after filtering ok=1 and RSSI fields.")
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

        th = mu + alpha * sigma
        tl = mu - alpha * sigma

        block_bits = bits[start:end]
        block_bits[block > th] = 1
        block_bits[block < tl] = 0
        bits[start:end] = block_bits

    return bits


def parity(bits: np.ndarray) -> int:
    return int(np.sum(bits) % 2)


def make_permutation(n: int, pass_index: int) -> np.ndarray:
    """
    Deterministic permutation shared by both parties.
    For a deployable protocol, this would be generated from public transcript/session info.
    """
    rng = np.random.default_rng(seed=0xA5A50000 + pass_index)
    return rng.permutation(n)


def locate_one_error_by_parity(ref: np.ndarray, other: np.ndarray, indices: np.ndarray) -> int | None:
    """
    Simulates binary-search parity reconciliation.
    Returns an index in the ORIGINAL bit array to flip in other, or None.

    This assumes parity(ref[indices]) != parity(other[indices]).
    If there are odd errors, it will locate one parity-detectable error.
    If there are multiple odd errors, it locates one, not all.
    """
    current = indices.copy()

    while len(current) > 1:
        mid = len(current) // 2
        left = current[:mid]
        right = current[mid:]

        if parity(ref[left]) != parity(other[left]):
            current = left
        elif parity(ref[right]) != parity(other[right]):
            current = right
        else:
            return None

    return int(current[0]) if len(current) == 1 else None


def block_parity_reconcile(ref_bits: np.ndarray, other_bits: np.ndarray, block_size: int, passes: int):
    """
    Device/ref bits are treated as correct.
    Network/other bits are corrected.

    Returns:
      corrected_other_bits, stats dict
    """
    ref = ref_bits.astype(int).copy()
    other = other_bits.astype(int).copy()
    n = len(ref)

    stats = {
        "passes": passes,
        "recon_block_size": block_size,
        "parity_checks_revealed": 0,
        "blocks_checked": 0,
        "blocks_with_parity_mismatch": 0,
        "flips_applied": 0,
        "mismatches_after_each_pass": [],
    }

    for p in range(passes):
        perm = make_permutation(n, p)
        for start in range(0, n, block_size):
            block_perm_indices = perm[start:start + block_size]
            if len(block_perm_indices) < 2:
                continue

            stats["blocks_checked"] += 1
            stats["parity_checks_revealed"] += 1

            if parity(ref[block_perm_indices]) != parity(other[block_perm_indices]):
                stats["blocks_with_parity_mismatch"] += 1
                flip_idx = locate_one_error_by_parity(ref, other, block_perm_indices)
                if flip_idx is not None:
                    other[flip_idx] ^= 1
                    stats["flips_applied"] += 1

        stats["mismatches_after_each_pass"].append(int(np.sum(ref != other)))

    return other, stats


def bits_to_bytes(bits) -> bytes:
    bits = [int(b) for b in bits]
    if not bits:
        return b""

    pad_len = (-len(bits)) % 8
    bits = bits + [0] * pad_len

    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i+8]:
            byte = (byte << 1) | b
        out.append(byte)
    return bytes(out)


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * hashlib.sha256().digest_size
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    digest_len = hashlib.sha256().digest_size
    n = math.ceil(length / digest_len)
    if n > 255:
        raise ValueError("HKDF length too large")

    okm = b""
    t = b""
    for i in range(1, n + 1):
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


def derive_kauth(bits, salt: bytes, info: bytes, length: int) -> bytes:
    ikm = bits_to_bytes(bits)
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)


def bit_entropy(bits):
    if len(bits) == 0:
        return 0.0, 0.0, None, None
    p1 = float(np.mean(bits))
    p0 = 1.0 - p1
    h = 0.0
    for p in (p0, p1):
        if p > 0:
            h -= p * math.log2(p)
    min_h = -math.log2(max(p0, p1)) if max(p0, p1) > 0 else 0.0
    return h, min_h, p0, p1


def make_binding_tag(kauth: bytes, th3: bytes, ci: bytes, cr: bytes, dev_eui: bytes, tag_len: int = 16) -> bytes:
    msg = th3 + ci + cr + dev_eui
    return hmac.new(kauth, msg, hashlib.sha256).digest()[:tag_len]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Raw PAIR log or paired_clean.csv")
    ap.add_argument("--out", type=Path, default=Path("recon_demo"), help="Output folder")
    ap.add_argument("--window", type=int, default=21, help="MWA window")
    ap.add_argument("--alpha", type=float, default=1.0, help="Adaptive quantization alpha")
    ap.add_argument("--block-size", type=int, default=50, help="Adaptive quantization block size")
    ap.add_argument("--online-cal-pairs", type=int, default=100, help="Initial pairs reserved for online calibration")
    ap.add_argument("--kauth-len", type=int, default=16, choices=[16, 32], help="K_auth length in bytes")
    ap.add_argument("--recon-block-size", type=int, default=16, help="Block size for block-parity reconciliation")
    ap.add_argument("--recon-passes", type=int, default=4, help="Number of deterministic reconciliation passes")
    ap.add_argument("--dev-eui", default="0102030405060708", help="DevEUI hex string for binding tag demo")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    df = load_pair_log(args.input)
    if len(df) <= args.online_cal_pairs:
        raise SystemExit("Not enough rows for online calibration + key generation.")

    cal = df.iloc[:args.online_cal_pairs].copy()
    keygen = df.iloc[args.online_cal_pairs:].copy()

    offset = float(np.mean(cal["rssi_device"].to_numpy(dtype=float) - cal["rssi_network"].to_numpy(dtype=float)))

    r_net = keygen["rssi_network"].to_numpy(dtype=float) + offset
    r_dev = keygen["rssi_device"].to_numpy(dtype=float)

    r_net_mwa = moving_average(r_net, args.window)
    r_dev_mwa = moving_average(r_dev, args.window)

    b_net = adaptive_quantize_blocks(r_net_mwa, args.block_size, args.alpha)
    b_dev = adaptive_quantize_blocks(r_dev_mwa, args.block_size, args.alpha)

    usable_mask = (~np.isnan(b_net)) & (~np.isnan(b_dev))
    net_bits = b_net[usable_mask].astype(int)
    dev_bits = b_dev[usable_mask].astype(int)

    usable_bits = int(len(dev_bits))
    mismatches_before = int(np.sum(dev_bits != net_bits))
    bdr_before = mismatches_before / usable_bits if usable_bits else None

    # Simulate deployable-style reconciliation: device is reference, network corrects.
    corrected_net_bits, recon_stats = block_parity_reconcile(
        ref_bits=dev_bits,
        other_bits=net_bits,
        block_size=args.recon_block_size,
        passes=args.recon_passes,
    )

    mismatches_after = int(np.sum(dev_bits != corrected_net_bits))
    bdr_after = mismatches_after / usable_bits if usable_bits else None

    h, min_h, p0, p1 = bit_entropy(dev_bits)
    estimated_total_min_entropy_before_leakage = usable_bits * min_h
    estimated_total_min_entropy_after_leakage = max(
        0.0,
        estimated_total_min_entropy_before_leakage - recon_stats["parity_checks_revealed"]
    )

    run_id = str(df["run_id"].iloc[0])
    env = str(df["env"].iloc[0])
    distance = str(df["distance_cm"].iloc[0])
    freq = str(df["freq_mhz"].iloc[0])

    salt = hashlib.sha256(
        f"LoRaWAN-EDHOC-RSSI-SALT-v1|{run_id}|{env}|{distance}|{freq}".encode()
    ).digest()
    info = b"LoRaWAN-EDHOC-RSSI-Binding-v1"

    kauth_device = derive_kauth(dev_bits, salt=salt, info=info, length=args.kauth_len)
    kauth_network = derive_kauth(corrected_net_bits, salt=salt, info=info, length=args.kauth_len)

    th3 = hashlib.sha256(b"DEMO-EDHOC-TH3|message_1|message_2|message_3").digest()
    ci = b"I"
    cr = b"R"
    dev_eui = bytes.fromhex(args.dev_eui)

    tag_device = make_binding_tag(kauth_device, th3, ci, cr, dev_eui)
    tag_network = make_binding_tag(kauth_network, th3, ci, cr, dev_eui)

    wrong_th3 = hashlib.sha256(b"DEMO-EDHOC-TH3|tampered").digest()
    wrong_tag = make_binding_tag(kauth_device, wrong_th3, ci, cr, dev_eui)

    result = {
        "input": str(args.input),
        "run_id": run_id,
        "env": env,
        "distance_cm": float(df["distance_cm"].iloc[0]),
        "freq_mhz": float(df["freq_mhz"].iloc[0]),
        "n_total_pairs": int(len(df)),
        "n_calibration_pairs": int(args.online_cal_pairs),
        "n_keygen_pairs": int(len(keygen)),
        "online_offset_device_minus_network_db": offset,
        "window": args.window,
        "alpha": args.alpha,
        "block_size": args.block_size,
        "usable_bits": usable_bits,
        "mismatches_before_reconciliation": mismatches_before,
        "bdr_before_reconciliation": bdr_before,
        "recon_block_size": args.recon_block_size,
        "recon_passes": args.recon_passes,
        "reconciliation_stats": recon_stats,
        "mismatches_after_reconciliation": mismatches_after,
        "bdr_after_reconciliation": bdr_after,
        "entropy_bits_per_bit": h,
        "min_entropy_bits_per_bit": min_h,
        "estimated_total_min_entropy_before_leakage": estimated_total_min_entropy_before_leakage,
        "estimated_total_min_entropy_after_parity_leakage": estimated_total_min_entropy_after_leakage,
        "kauth_len_bytes": args.kauth_len,
        "kauth_device_hex": kauth_device.hex(),
        "kauth_network_hex": kauth_network.hex(),
        "kauth_match": kauth_device == kauth_network,
        "tag_device_hex": tag_device.hex(),
        "tag_network_hex": tag_network.hex(),
        "tag_match": tag_device == tag_network,
        "tampered_transcript_tag_matches_valid": wrong_tag == tag_network,
    }

    (args.out / "reconciliation_demo_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = []
    lines.append("# RSSI-derived K_auth with block-parity reconciliation\n")
    lines.append(f"- Input: `{args.input}`")
    lines.append(f"- Run: `{run_id}` / `{env}` / {distance} cm / {freq} MHz")
    lines.append(f"- Online calibration pairs: `{args.online_cal_pairs}`")
    lines.append(f"- MWA window: `{args.window}`")
    lines.append(f"- Alpha: `{args.alpha}`")
    lines.append(f"- Quantization block size: `{args.block_size}`")
    lines.append(f"- Offset from calibration phase: `{offset:.4f} dB`")
    lines.append("")
    lines.append("## Bit extraction and reconciliation")
    lines.append(f"- Usable bits: `{usable_bits}`")
    lines.append(f"- Mismatches before reconciliation: `{mismatches_before}`")
    lines.append(f"- BDR before reconciliation: `{bdr_before}`")
    lines.append(f"- Reconciliation block size: `{args.recon_block_size}`")
    lines.append(f"- Reconciliation passes: `{args.recon_passes}`")
    lines.append(f"- Parity checks revealed: `{recon_stats['parity_checks_revealed']}`")
    lines.append(f"- Flips applied: `{recon_stats['flips_applied']}`")
    lines.append(f"- Mismatches after each pass: `{recon_stats['mismatches_after_each_pass']}`")
    lines.append(f"- Mismatches after reconciliation: `{mismatches_after}`")
    lines.append(f"- BDR after reconciliation: `{bdr_after}`")
    lines.append("")
    lines.append("## Entropy / leakage estimate")
    lines.append(f"- Entropy per bit: `{h}`")
    lines.append(f"- Min-entropy per bit: `{min_h}`")
    lines.append(f"- Estimated total min-entropy before parity leakage: `{estimated_total_min_entropy_before_leakage}`")
    lines.append(f"- Estimated total min-entropy after parity leakage: `{estimated_total_min_entropy_after_leakage}`")
    lines.append("")
    lines.append("## K_auth and binding tag demo")
    lines.append(f"- K_auth match: `{kauth_device == kauth_network}`")
    lines.append(f"- Tag match: `{tag_device == tag_network}`")
    lines.append(f"- Tampered transcript tag matches valid tag: `{wrong_tag == tag_network}`")
    lines.append("")
    lines.append("## Interpretation note")
    lines.append("This is a simplified block-parity reconciliation prototype.")
    lines.append("If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.")
    lines.append("If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.")
    (args.out / "reconciliation_demo_summary.md").write_text("\n".join(lines), encoding="utf-8")

    bit_df = pd.DataFrame({
        "device_bit": dev_bits,
        "network_bit_before_reconciliation": net_bits,
        "network_bit_after_reconciliation": corrected_net_bits,
        "match_before": dev_bits == net_bits,
        "match_after": dev_bits == corrected_net_bits,
    })
    bit_df.to_csv(args.out / "reconciled_bit_comparison.csv", index=False)

    print("\nRSSI-derived K_auth with block-parity reconciliation complete")
    print("Run:", run_id, env)
    print("Usable bits:", usable_bits)
    print("Mismatches before:", mismatches_before)
    print("BDR before:", bdr_before)
    print("Mismatches after:", mismatches_after)
    print("BDR after:", bdr_after)
    print("K_auth match:", kauth_device == kauth_network)
    print("Tag match:", tag_device == tag_network)
    print("Tampered transcript tag matches valid tag:", wrong_tag == tag_network)
    print("\nSaved:")
    print(" -", args.out / "reconciliation_demo_result.json")
    print(" -", args.out / "reconciliation_demo_summary.md")
    print(" -", args.out / "reconciled_bit_comparison.csv")


if __name__ == "__main__":
    main()
