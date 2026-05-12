#!/usr/bin/env python3
"""
derive_kauth_from_rssi.py

Prototype pipeline:
PAIR log / paired_clean.csv
 -> optional online calibration
 -> MWA
 -> adaptive quantization
 -> preliminary device/network bitstrings
 -> placeholder reconciliation
 -> HKDF K_auth
 -> simulated EDHOC physical-layer binding tag

IMPORTANT:
- The default reconciliation mode is "oracle" for PROTOTYPE DEMO ONLY.
- "oracle" means the offline script keeps only positions where both sides' bits match.
- This is NOT a deployable reconciliation protocol.
- Use it only to prove the RSSI_bits -> K_auth -> binding-tag pipeline.
- Later, replace it with a real reconciliation method such as parity/Cascade-like reconciliation.

Examples:
  py derive_kauth_from_rssi.py datasets/raw/run04_outdoor_los_100cm_device.csv --out datasets/processed/run04_kauth_demo --window 21 --alpha 1.0

  py derive_kauth_from_rssi.py datasets/raw/run02_indoor_static_100cm_device.csv --out datasets/processed/run02_kauth_demo --window 21 --alpha 0.75
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
    """
    Accepts either:
    - raw serial log containing PAIR,... rows
    - cleaned CSV containing normal column headers
    """
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


def bits_to_bytes(bits) -> bytes:
    """
    Pack list/array of 0/1 bits into bytes.
    Pads with zeros to complete the final byte.
    """
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
    ap.add_argument("--out", type=Path, default=Path("kauth_demo"), help="Output folder")
    ap.add_argument("--window", type=int, default=21, help="MWA window")
    ap.add_argument("--alpha", type=float, default=1.0, help="Adaptive quantization alpha")
    ap.add_argument("--block-size", type=int, default=50, help="Adaptive quantization block size")
    ap.add_argument("--online-cal-pairs", type=int, default=100, help="Initial pairs reserved for online calibration")
    ap.add_argument("--kauth-len", type=int, default=16, choices=[16, 32], help="K_auth length in bytes")
    ap.add_argument("--reconcile", choices=["none", "oracle"], default="oracle",
                    help="none = derive separate keys; oracle = prototype-only keep matching bit positions")
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
    net_bits_all = b_net[usable_mask].astype(int)
    dev_bits_all = b_dev[usable_mask].astype(int)

    usable_bits_before_reconciliation = int(len(dev_bits_all))
    mismatches = int(np.sum(net_bits_all != dev_bits_all))
    bdr = mismatches / usable_bits_before_reconciliation if usable_bits_before_reconciliation else None

    if args.reconcile == "none":
        dev_bits_final = dev_bits_all
        net_bits_final = net_bits_all
        reconciliation_note = "none: device and network derive K_auth independently; keys may differ if BDR > 0"
    else:
        match_mask = (net_bits_all == dev_bits_all)
        dev_bits_final = dev_bits_all[match_mask]
        net_bits_final = net_bits_all[match_mask]
        reconciliation_note = (
            "oracle prototype: kept only matching bit positions. "
            "This is NOT deployable; replace with real reconciliation later."
        )

    h, min_h, p0, p1 = bit_entropy(dev_bits_final)
    estimated_min_entropy_total = len(dev_bits_final) * min_h

    run_id = str(df["run_id"].iloc[0])
    env = str(df["env"].iloc[0])
    distance = str(df["distance_cm"].iloc[0])
    freq = str(df["freq_mhz"].iloc[0])

    salt = hashlib.sha256(
        f"LoRaWAN-EDHOC-RSSI-SALT-v1|{run_id}|{env}|{distance}|{freq}".encode()
    ).digest()

    info = b"LoRaWAN-EDHOC-RSSI-Binding-v1"

    kauth_device = derive_kauth(dev_bits_final, salt=salt, info=info, length=args.kauth_len)
    kauth_network = derive_kauth(net_bits_final, salt=salt, info=info, length=args.kauth_len)

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
        "usable_bits_before_reconciliation": usable_bits_before_reconciliation,
        "mismatches_before_reconciliation": mismatches,
        "bdr_before_reconciliation": bdr,
        "reconciliation_mode": args.reconcile,
        "reconciliation_note": reconciliation_note,
        "final_bits_after_reconciliation": int(len(dev_bits_final)),
        "entropy_bits_per_bit_after_reconciliation": h,
        "min_entropy_bits_per_bit_after_reconciliation": min_h,
        "estimated_min_entropy_bits_total_after_reconciliation": estimated_min_entropy_total,
        "p0_after_reconciliation": p0,
        "p1_after_reconciliation": p1,
        "kauth_len_bytes": args.kauth_len,
        "kauth_device_hex": kauth_device.hex(),
        "kauth_network_hex": kauth_network.hex(),
        "kauth_match": kauth_device == kauth_network,
        "demo_th3_hex": th3.hex(),
        "demo_dev_eui_hex": dev_eui.hex(),
        "tag_device_hex": tag_device.hex(),
        "tag_network_hex": tag_network.hex(),
        "tag_match": tag_device == tag_network,
        "tampered_transcript_tag_hex": wrong_tag.hex(),
        "tampered_transcript_tag_matches_valid": wrong_tag == tag_network,
    }

    (args.out / "kauth_demo_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary_lines = []
    summary_lines.append("# RSSI-derived K_auth demo\n")
    summary_lines.append(f"- Input: `{args.input}`")
    summary_lines.append(f"- Run: `{run_id}` / `{env}` / {distance} cm / {freq} MHz")
    summary_lines.append(f"- Online calibration pairs: `{args.online_cal_pairs}`")
    summary_lines.append(f"- MWA window: `{args.window}`")
    summary_lines.append(f"- Alpha: `{args.alpha}`")
    summary_lines.append(f"- Block size: `{args.block_size}`")
    summary_lines.append(f"- Offset from calibration phase: `{offset:.4f} dB`")
    summary_lines.append("")
    summary_lines.append("## Bit extraction")
    summary_lines.append(f"- Usable bits before reconciliation: `{usable_bits_before_reconciliation}`")
    summary_lines.append(f"- Mismatches before reconciliation: `{mismatches}`")
    summary_lines.append(f"- BDR before reconciliation: `{bdr}`")
    summary_lines.append(f"- Reconciliation mode: `{args.reconcile}`")
    summary_lines.append(f"- Final bits after reconciliation: `{len(dev_bits_final)}`")
    summary_lines.append(f"- Entropy after reconciliation: `{h}`")
    summary_lines.append(f"- Min-entropy per bit after reconciliation: `{min_h}`")
    summary_lines.append(f"- Estimated total min-entropy after reconciliation: `{estimated_min_entropy_total}`")
    summary_lines.append("")
    summary_lines.append("## K_auth and binding tag demo")
    summary_lines.append(f"- K_auth device: `{kauth_device.hex()}`")
    summary_lines.append(f"- K_auth network: `{kauth_network.hex()}`")
    summary_lines.append(f"- K_auth match: `{kauth_device == kauth_network}`")
    summary_lines.append(f"- Tag device: `{tag_device.hex()}`")
    summary_lines.append(f"- Tag network: `{tag_network.hex()}`")
    summary_lines.append(f"- Tag match: `{tag_device == tag_network}`")
    summary_lines.append(f"- Tampered transcript tag matches valid tag: `{wrong_tag == tag_network}`")
    summary_lines.append("")
    summary_lines.append("## Important limitation")
    summary_lines.append("If reconciliation mode is `oracle`, this is only a prototype demonstration.")
    summary_lines.append("It proves the pipeline from RSSI bits to K_auth to an EDHOC-style binding tag,")
    summary_lines.append("but it must later be replaced by a real information reconciliation method.")
    (args.out / "kauth_demo_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    bits_df = pd.DataFrame({
        "dev_bit_before_reconciliation": dev_bits_all,
        "net_bit_before_reconciliation": net_bits_all,
        "match": dev_bits_all == net_bits_all,
    })
    bits_df.to_csv(args.out / "bit_comparison.csv", index=False)

    print("\nRSSI-derived K_auth demo complete")
    print("Run:", run_id, env)
    print("Usable bits before reconciliation:", usable_bits_before_reconciliation)
    print("Mismatches before reconciliation:", mismatches)
    print("BDR before reconciliation:", bdr)
    print("Final bits after reconciliation:", len(dev_bits_final))
    print("K_auth match:", kauth_device == kauth_network)
    print("Tag match:", tag_device == tag_network)
    print("Tampered transcript tag matches valid tag:", wrong_tag == tag_network)
    print("\nSaved:")
    print(" -", args.out / "kauth_demo_result.json")
    print(" -", args.out / "kauth_demo_summary.md")
    print(" -", args.out / "bit_comparison.csv")


if __name__ == "__main__":
    main()
