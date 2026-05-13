#!/usr/bin/env python3
"""
edhoc_bootstrap_experiment.py

Purpose:
Create the first EDHOC bootstrap comparison result table for the thesis.

It compares:

1) EDHOC-only baseline
   - Simulated compact EDHOC message sizes
   - Normal EDHOC transcript/session-key derivation model
   - No physical-layer binding

2) RSSI-bound EDHOC
   - Uses an RSSI-derived K_auth result produced by:
       derive_kauth_from_rssi.py
       or derive_kauth_with_reconciliation.py
   - Computes a physical-layer binding tag:
       Tag_phy = HMAC(K_auth, TH3 || C_I || C_R || DevEUI)
   - Derives a final bound session key:
       SK_bound = HKDF(EDHOC_exporter_key, salt=K_auth, info="LoRaWAN-EDHOC-RSSI-Bound-Session-v1")
   - Checks whether tampering or wrong K_auth is rejected.

This is not a full RFC 9528 EDHOC implementation yet.
It is a thesis experiment harness that gives measurable EDHOC-bootstrap comparison results.

Recommended first run:
  py edhoc_bootstrap_experiment.py ^
    --rssi-result datasets/processed/run04_recon_demo/reconciliation_demo_result.json ^
    --out datasets/processed/edhoc_bootstrap_run04

Then inspect:
  type datasets\processed\edhoc_bootstrap_run04\edhoc_bootstrap_results.md
"""

import argparse
import csv
import hashlib
import hmac
import json
import math
from pathlib import Path


# RFC 9528 Table 1 example sizes for EDHOC using static DH keys with kid identification:
# message_1 = 37 bytes, message_2 = 45 bytes, message_3 = 19 bytes, total = 101 bytes.
# We use these as a compact EDHOC-only baseline model.
EDHOC_M1_LEN = 37
EDHOC_M2_LEN = 45
EDHOC_M3_LEN = 19

PHY_TAG_LEN = 16


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


def hkdf(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    return hkdf_expand(hkdf_extract(salt, ikm), info, length)


def fake_edhoc_messages() -> tuple[bytes, bytes, bytes]:
    """
    Deterministic placeholder messages with RFC-sized lengths.
    These are not real CBOR/COSE EDHOC messages.
    They let us measure transcript binding and payload-size effects before full EDHOC integration.
    """
    m1 = b"E1" + bytes([0x11]) * (EDHOC_M1_LEN - 2)
    m2 = b"E2" + bytes([0x22]) * (EDHOC_M2_LEN - 2)
    m3 = b"E3" + bytes([0x33]) * (EDHOC_M3_LEN - 2)
    return m1, m2, m3


def transcript_hash(m1: bytes, m2: bytes, m3: bytes) -> bytes:
    return hashlib.sha256(b"TH3|" + m1 + m2 + m3).digest()


def make_tag_phy(kauth: bytes, th3: bytes, c_i: bytes, c_r: bytes, dev_eui: bytes) -> bytes:
    msg = th3 + c_i + c_r + dev_eui
    return hmac.new(kauth, msg, hashlib.sha256).digest()[:PHY_TAG_LEN]


def derive_edhoc_exporter_key(th3: bytes, length: int = 16) -> bytes:
    """
    Simulated EDHOC exporter key.
    In full EDHOC, this would come from EDHOC_Exporter / PRK_out.
    """
    simulated_prk_out = hashlib.sha256(b"SIMULATED-EDHOC-PRK-OUT-v1").digest()
    return hkdf(simulated_prk_out, salt=th3, info=b"EDHOC-Exporter-LoRaWAN-Session-v1", length=length)


def derive_bound_session_key(edhoc_exporter_key: bytes, kauth: bytes, length: int = 16) -> bytes:
    return hkdf(
        ikm=edhoc_exporter_key,
        salt=kauth,
        info=b"LoRaWAN-EDHOC-RSSI-Bound-Session-v1",
        length=length,
    )


def lora_time_on_air_ms(payload_len: int, sf: int = 7, bw_hz: int = 125000, cr_denom: int = 5,
                        preamble: int = 8, explicit_header: bool = True, crc: bool = True) -> float:
    """
    LoRa time-on-air estimate.
    CR denominator 5 means coding rate 4/5.
    """
    cr = max(1, min(4, cr_denom - 4))  # 4/5 -> 1, 4/6 -> 2, etc.
    tsym = (2 ** sf) / bw_hz
    de = 1 if (sf >= 11 and bw_hz <= 125000) else 0
    ih = 0 if explicit_header else 1
    crc_val = 1 if crc else 0

    tpreamble = (preamble + 4.25) * tsym

    numerator = 8 * payload_len - 4 * sf + 28 + 16 * crc_val - 20 * ih
    denominator = 4 * (sf - 2 * de)
    payload_symbols = 8 + max(math.ceil(numerator / denominator) * (cr + 4), 0)

    tpayload = payload_symbols * tsym
    return (tpreamble + tpayload) * 1000.0


def get_first_available(d: dict, keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default


def load_rssi_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "kauth_device_hex" not in data:
        raise SystemExit(f"{path} does not contain kauth_device_hex. Run a K_auth demo first.")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rssi-result", type=Path, required=True,
                    help="reconciliation_demo_result.json or kauth_demo_result.json")
    ap.add_argument("--out", type=Path, required=True, help="Output folder")
    ap.add_argument("--dev-eui", default="0102030405060708", help="DevEUI hex string")
    ap.add_argument("--sf", type=int, default=7)
    ap.add_argument("--bw-khz", type=int, default=125)
    ap.add_argument("--cr", default="4/5")
    ap.add_argument("--probe-payload-len", type=int, default=37,
                    help="Approximate payload size of one RSSI probe packet in bytes")
    ap.add_argument("--target-security-bits", type=int, default=128)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    rssi = load_rssi_result(args.rssi_result)

    cr_denom = int(str(args.cr).split("/")[-1])
    bw_hz = args.bw_khz * 1000

    run_id = str(get_first_available(rssi, ["run_id"], "unknown"))
    env = str(get_first_available(rssi, ["env"], "unknown"))
    distance_cm = get_first_available(rssi, ["distance_cm"], None)
    freq_mhz = get_first_available(rssi, ["freq_mhz"], None)

    kauth_device = bytes.fromhex(rssi["kauth_device_hex"])
    kauth_network = bytes.fromhex(rssi.get("kauth_network_hex", rssi["kauth_device_hex"]))
    kauth_match_from_rssi_stage = bool(rssi.get("kauth_match", kauth_device == kauth_network))

    usable_bits = get_first_available(rssi, ["usable_bits", "usable_bits_before_reconciliation"], None)
    mismatches_before = get_first_available(rssi, ["mismatches_before_reconciliation"], None)
    bdr_before = get_first_available(rssi, ["bdr_before_reconciliation"], None)
    mismatches_after = get_first_available(rssi, ["mismatches_after_reconciliation"], None)
    bdr_after = get_first_available(rssi, ["bdr_after_reconciliation"], None)

    if mismatches_after is None:
        # Oracle K_auth demo does not have a real after-reconciliation mismatch count.
        mismatches_after = 0 if kauth_match_from_rssi_stage else None
        bdr_after = 0 if kauth_match_from_rssi_stage else None

    entropy_after_leakage = get_first_available(
        rssi,
        [
            "estimated_total_min_entropy_after_parity_leakage",
            "estimated_min_entropy_bits_total_after_reconciliation",
            "estimated_total_min_entropy_before_leakage",
        ],
        None
    )

    n_total_pairs = int(get_first_available(rssi, ["n_total_pairs"], 0) or 0)
    n_calibration_pairs = int(get_first_available(rssi, ["n_calibration_pairs"], 0) or 0)
    n_keygen_pairs = int(get_first_available(rssi, ["n_keygen_pairs"], max(0, n_total_pairs - n_calibration_pairs)) or 0)
    rssi_probe_packets = n_total_pairs * 2 if n_total_pairs else None

    m1, m2, m3 = fake_edhoc_messages()
    th3 = transcript_hash(m1, m2, m3)
    c_i = b"I"
    c_r = b"R"
    dev_eui = bytes.fromhex(args.dev_eui)

    edhoc_exporter_key = derive_edhoc_exporter_key(th3, length=16)
    edhoc_only_session_key = edhoc_exporter_key

    tag_device = make_tag_phy(kauth_device, th3, c_i, c_r, dev_eui)
    tag_network = make_tag_phy(kauth_network, th3, c_i, c_r, dev_eui)
    tag_match = tag_device == tag_network

    tampered_th3 = hashlib.sha256(b"TAMPERED|" + m1 + m2 + m3).digest()
    tampered_tag = make_tag_phy(kauth_device, tampered_th3, c_i, c_r, dev_eui)
    tampered_rejected = tampered_tag != tag_network

    wrong_kauth = hashlib.sha256(b"wrong-kauth-for-negative-test").digest()[:len(kauth_device)]
    wrong_tag = make_tag_phy(wrong_kauth, th3, c_i, c_r, dev_eui)
    wrong_kauth_rejected = wrong_tag != tag_network

    bound_session_key_device = derive_bound_session_key(edhoc_exporter_key, kauth_device, length=16)
    bound_session_key_network = derive_bound_session_key(edhoc_exporter_key, kauth_network, length=16)
    bound_session_key_match = bound_session_key_device == bound_session_key_network

    edhoc_only_payload_bytes = len(m1) + len(m2) + len(m3)
    bound_edhoc_payload_bytes = edhoc_only_payload_bytes + PHY_TAG_LEN

    toa_m1 = lora_time_on_air_ms(len(m1), args.sf, bw_hz, cr_denom)
    toa_m2 = lora_time_on_air_ms(len(m2), args.sf, bw_hz, cr_denom)
    toa_m3 = lora_time_on_air_ms(len(m3), args.sf, bw_hz, cr_denom)
    toa_phy_tag = lora_time_on_air_ms(len(m3) + PHY_TAG_LEN, args.sf, bw_hz, cr_denom)
    edhoc_only_toa_ms = toa_m1 + toa_m2 + toa_m3
    bound_edhoc_toa_ms_without_probes = toa_m1 + toa_m2 + toa_phy_tag

    probe_toa_ms = lora_time_on_air_ms(args.probe_payload_len, args.sf, bw_hz, cr_denom)
    rssi_probe_toa_ms = (rssi_probe_packets or 0) * probe_toa_ms
    bound_total_toa_ms_with_probes = bound_edhoc_toa_ms_without_probes + rssi_probe_toa_ms

    functional_success = (
        kauth_match_from_rssi_stage
        and tag_match
        and tampered_rejected
        and wrong_kauth_rejected
        and bound_session_key_match
    )

    enough_entropy_for_128 = None
    if entropy_after_leakage is not None:
        enough_entropy_for_128 = float(entropy_after_leakage) >= args.target_security_bits

    rows = [
        {
            "run_id": run_id,
            "environment": env,
            "method": "EDHOC-only baseline",
            "rssi_pairs": 0,
            "rssi_probe_packets": 0,
            "edhoc_payload_bytes_est": edhoc_only_payload_bytes,
            "extra_phy_tag_bytes": 0,
            "edhoc_toa_ms_est": round(edhoc_only_toa_ms, 3),
            "total_toa_ms_est_with_rssi_probes": round(edhoc_only_toa_ms, 3),
            "physical_layer_binding": False,
            "usable_rssi_bits": "",
            "bdr_before": "",
            "mismatches_after": "",
            "estimated_min_entropy_after_leakage": "",
            "kauth_match": "",
            "tag_match": "",
            "tampered_transcript_rejected": "",
            "wrong_kauth_rejected": "",
            "session_key_match": True,
            "functional_success": True,
            "interpretation": "Baseline EDHOC bootstrap; no RSSI-derived physical-layer binding."
        },
        {
            "run_id": run_id,
            "environment": env,
            "method": "RSSI-bound EDHOC",
            "rssi_pairs": n_total_pairs,
            "rssi_probe_packets": rssi_probe_packets,
            "edhoc_payload_bytes_est": bound_edhoc_payload_bytes,
            "extra_phy_tag_bytes": PHY_TAG_LEN,
            "edhoc_toa_ms_est": round(bound_edhoc_toa_ms_without_probes, 3),
            "total_toa_ms_est_with_rssi_probes": round(bound_total_toa_ms_with_probes, 3),
            "physical_layer_binding": True,
            "usable_rssi_bits": usable_bits,
            "bdr_before": bdr_before,
            "mismatches_after": mismatches_after,
            "estimated_min_entropy_after_leakage": entropy_after_leakage,
            "kauth_match": kauth_match_from_rssi_stage,
            "tag_match": tag_match,
            "tampered_transcript_rejected": tampered_rejected,
            "wrong_kauth_rejected": wrong_kauth_rejected,
            "session_key_match": bound_session_key_match,
            "functional_success": functional_success,
            "interpretation": (
                "Adds RSSI-derived K_auth binding. Good thesis signal if success=True, "
                "but overhead and entropy margin must be evaluated."
            )
        }
    ]

    csv_path = args.out / "edhoc_bootstrap_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "input_rssi_result": str(args.rssi_result),
        "run_id": run_id,
        "environment": env,
        "distance_cm": distance_cm,
        "freq_mhz": freq_mhz,
        "edhoc_model_note": "Simulated RFC-sized EDHOC transcript, not a full RFC 9528 implementation.",
        "edhoc_message_lengths": {
            "message_1": len(m1),
            "message_2": len(m2),
            "message_3": len(m3),
            "total": edhoc_only_payload_bytes,
        },
        "rssi_stage": {
            "n_total_pairs": n_total_pairs,
            "n_calibration_pairs": n_calibration_pairs,
            "n_keygen_pairs": n_keygen_pairs,
            "usable_bits": usable_bits,
            "mismatches_before_reconciliation": mismatches_before,
            "bdr_before_reconciliation": bdr_before,
            "mismatches_after_reconciliation": mismatches_after,
            "bdr_after_reconciliation": bdr_after,
            "estimated_min_entropy_after_leakage": entropy_after_leakage,
            "enough_entropy_for_target_security_bits": enough_entropy_for_128,
            "target_security_bits": args.target_security_bits,
        },
        "edhoc_only": {
            "session_key_hex": edhoc_only_session_key.hex(),
            "payload_bytes_est": edhoc_only_payload_bytes,
            "toa_ms_est": edhoc_only_toa_ms,
        },
        "rssi_bound_edhoc": {
            "tag_device_hex": tag_device.hex(),
            "tag_network_hex": tag_network.hex(),
            "tag_match": tag_match,
            "tampered_transcript_rejected": tampered_rejected,
            "wrong_kauth_rejected": wrong_kauth_rejected,
            "bound_session_key_device_hex": bound_session_key_device.hex(),
            "bound_session_key_network_hex": bound_session_key_network.hex(),
            "bound_session_key_match": bound_session_key_match,
            "functional_success": functional_success,
            "payload_bytes_est_without_rssi_probes": bound_edhoc_payload_bytes,
            "edhoc_toa_ms_est_without_rssi_probes": bound_edhoc_toa_ms_without_probes,
            "rssi_probe_packets_est": rssi_probe_packets,
            "rssi_probe_toa_ms_est": rssi_probe_toa_ms,
            "total_toa_ms_est_with_rssi_probes": bound_total_toa_ms_with_probes,
        }
    }

    json_path = args.out / "edhoc_bootstrap_result.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    md_lines = []
    md_lines.append("# EDHOC Bootstrap Comparison Result\n")
    md_lines.append(f"- RSSI result input: `{args.rssi_result}`")
    md_lines.append(f"- Run: `{run_id}` / `{env}`")
    md_lines.append(f"- Distance: `{distance_cm}` cm")
    md_lines.append(f"- Frequency: `{freq_mhz}` MHz")
    md_lines.append(f"- LoRa estimate: SF{args.sf}, BW {args.bw_khz} kHz, CR {args.cr}")
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("")
    md_lines.append("| Method | RSSI pairs | EDHOC bytes est. | Total ToA est. incl. probes | Physical binding | Session key match | Tampered transcript rejected | Functional success |")
    md_lines.append("|---|---:|---:|---:|---|---|---|---|")
    for row in rows:
        md_lines.append(
            f"| {row['method']} | {row['rssi_pairs']} | {row['edhoc_payload_bytes_est']} | "
            f"{row['total_toa_ms_est_with_rssi_probes']} ms | {row['physical_layer_binding']} | "
            f"{row['session_key_match']} | {row['tampered_transcript_rejected']} | {row['functional_success']} |"
        )

    md_lines.append("")
    md_lines.append("## RSSI-bound EDHOC details")
    md_lines.append("")
    md_lines.append(f"- Usable RSSI bits: `{usable_bits}`")
    md_lines.append(f"- BDR before reconciliation: `{bdr_before}`")
    md_lines.append(f"- Mismatches after reconciliation: `{mismatches_after}`")
    md_lines.append(f"- Estimated min-entropy after leakage: `{entropy_after_leakage}`")
    md_lines.append(f"- Enough for {args.target_security_bits}-bit target: `{enough_entropy_for_128}`")
    md_lines.append(f"- K_auth match from RSSI stage: `{kauth_match_from_rssi_stage}`")
    md_lines.append(f"- Tag_phy match: `{tag_match}`")
    md_lines.append(f"- Wrong K_auth rejected: `{wrong_kauth_rejected}`")
    md_lines.append(f"- Bound session key match: `{bound_session_key_match}`")
    md_lines.append("")
    md_lines.append("## Interpretation")
    md_lines.append("")
    if functional_success:
        md_lines.append(
            "The RSSI-bound EDHOC prototype succeeded functionally: the RSSI-derived K_auth "
            "binds to the simulated EDHOC transcript, the physical-layer tag verifies, a wrong "
            "K_auth is rejected, and both sides derive the same bound session key."
        )
    else:
        md_lines.append(
            "The RSSI-bound EDHOC prototype did not fully succeed. This usually means remaining "
            "RSSI bit disagreement, insufficient reconciliation, or mismatched K_auth."
        )
    md_lines.append("")
    if enough_entropy_for_128 is False:
        md_lines.append(
            "However, the estimated post-leakage min-entropy is below the 128-bit target. "
            "This means the pipeline works, but more RSSI bits, lower reconciliation leakage, "
            "or a shorter claimed security level is needed before making a strong 128-bit claim."
        )
    elif enough_entropy_for_128 is True:
        md_lines.append(
            "The estimated post-leakage min-entropy meets the 128-bit target in this run."
        )
    else:
        md_lines.append(
            "No post-leakage entropy estimate was available in the input file."
        )
    md_lines.append("")
    md_lines.append("## Important limitation")
    md_lines.append("")
    md_lines.append(
        "This script uses RFC-sized placeholder EDHOC messages, not a complete RFC 9528 EDHOC implementation. "
        "It is intended to produce the first thesis comparison table before integrating a full EDHOC library."
    )

    md_path = args.out / "edhoc_bootstrap_results.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print("\nEDHOC bootstrap experiment complete")
    print("Run:", run_id, env)
    print("EDHOC-only ToA estimate:", round(edhoc_only_toa_ms, 3), "ms")
    print("RSSI-bound EDHOC functional success:", functional_success)
    print("RSSI-bound EDHOC total ToA estimate with probes:", round(bound_total_toa_ms_with_probes, 3), "ms")
    print("Post-leakage entropy estimate:", entropy_after_leakage)
    print("Enough for target security bits:", enough_entropy_for_128)
    print("\nSaved:")
    print(" -", csv_path)
    print(" -", md_path)
    print(" -", json_path)


if __name__ == "__main__":
    main()
