# Probe-Count Sweep Results

- Input dataset: `datasets\raw\run04_outdoor_los_100cm_device.csv`
- Available pair rows: `998`
- Online calibration pairs per subset: `100`
- MWA window: `21`
- Alpha: `1.0`
- Quantization block size: `50`
- Target security bits: `128`

| Total probe pairs | Keygen pairs | Usable bits | BDR before | BDR after | Post-leakage min-entropy | K_auth match | Tag match | Wrong K_auth rejected | Tampered transcript rejected | Functional success | 128-bit target met? | Total ToA incl. probes |
|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---:|
| 200 | 98 | 37 | 0.00% | 0.00% | 23.58 | True | True | True | True | True | False | 32793.34 ms |
| 300 | 196 | 64 | 0.00% | 0.00% | 45.16 | True | True | True | True | True | False | 48899.84 ms |
| 500 | 394 | 122 | 0.00% | 0.00% | 68.31 | True | True | True | True | True | False | 81441.54 ms |
| 700 | 591 | 164 | 0.61% | 0.00% | 77.83 | True | True | True | True | True | False | 113818.88 ms |
| 900 | 790 | 188 | 0.00% | 0.00% | 78.33 | True | True | True | True | True | False | 146524.93 ms |
| 987 | 876 | 206 | 1.46% | 0.00% | 111.09 | True | True | True | True | True | False | 160659.20 ms |

## How to interpret this table

- `Functional success = True` means the RSSI-bound EDHOC pipeline worked.
- `128-bit target met = True` is required before claiming full 128-bit security.
- If functional success is true but the 128-bit target is false, the result supports feasibility but not the full security target yet.
- The best practical point is the smallest probe count that gives functional success and meets the entropy target.
