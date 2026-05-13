# Probe-Count Sweep Results

- Input dataset: `datasets\raw\run04_outdoor_los_100cm_device.csv`
- Available pair rows: `998`
- Online calibration pairs per subset: `100`
- MWA window: `31`
- Alpha: `0.25`
- Quantization block size: `100`
- Target security bits: `128`

| Total probe pairs | Keygen pairs | Usable bits | BDR before | BDR after | Post-leakage min-entropy | K_auth match | Tag match | Wrong K_auth rejected | Tampered transcript rejected | Functional success | 128-bit target met? | Total ToA incl. probes |
|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|---:|
| 300 | 196 | 162 | 0.00% | 0.00% | 109.50 | True | True | True | True | True | False | 48899.84 ms |
| 350 | 245 | 197 | 0.00% | 0.00% | 137.88 | True | True | True | True | True | True | 56953.09 ms |
| 400 | 294 | 254 | 0.00% | 0.00% | 164.91 | True | True | True | True | True | True | 65006.34 ms |
| 450 | 344 | 298 | 0.00% | 0.00% | 202.26 | True | True | True | True | True | True | 73223.94 ms |
| 500 | 394 | 347 | 0.00% | 0.00% | 200.52 | True | True | True | True | True | True | 81441.54 ms |

## How to interpret this table

- `Functional success = True` means the RSSI-bound EDHOC pipeline worked.
- `128-bit target met = True` is required before claiming full 128-bit security.
- If functional success is true but the 128-bit target is false, the result supports feasibility but not the full security target yet.
- The best practical point is the smallest probe count that gives functional success and meets the entropy target.
