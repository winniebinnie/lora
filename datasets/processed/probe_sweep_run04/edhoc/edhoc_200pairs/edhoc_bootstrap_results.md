# EDHOC Bootstrap Comparison Result

- RSSI result input: `datasets\processed\probe_sweep_run04\reconciliation\recon_200pairs\reconciliation_demo_result.json`
- Run: `run04` / `outdoor_los`
- Distance: `100.0` cm
- Frequency: `922.0` MHz
- LoRa estimate: SF7, BW 125 kHz, CR 4/5

## Summary

| Method | RSSI pairs | EDHOC bytes est. | Total ToA est. incl. probes | Physical binding | Session key match | Tampered transcript rejected | Functional success |
|---|---:|---:|---:|---|---|---|---|
| EDHOC-only baseline | 0 | 101 | 226.048 ms | False | True |  | True |
| RSSI-bound EDHOC | 198 | 117 | 32793.344 ms | True | True | True | True |

## RSSI-bound EDHOC details

- Usable RSSI bits: `37`
- BDR before reconciliation: `0.0`
- Mismatches after reconciliation: `0`
- Estimated min-entropy after leakage: `23.57645653085848`
- Enough for 128-bit target: `False`
- K_auth match from RSSI stage: `True`
- Tag_phy match: `True`
- Wrong K_auth rejected: `True`
- Bound session key match: `True`

## Interpretation

The RSSI-bound EDHOC prototype succeeded functionally: the RSSI-derived K_auth binds to the simulated EDHOC transcript, the physical-layer tag verifies, a wrong K_auth is rejected, and both sides derive the same bound session key.

However, the estimated post-leakage min-entropy is below the 128-bit target. This means the pipeline works, but more RSSI bits, lower reconciliation leakage, or a shorter claimed security level is needed before making a strong 128-bit claim.

## Important limitation

This script uses RFC-sized placeholder EDHOC messages, not a complete RFC 9528 EDHOC implementation. It is intended to produce the first thesis comparison table before integrating a full EDHOC library.