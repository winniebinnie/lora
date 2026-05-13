# RSSI-derived K_auth with block-parity reconciliation

- Input: `datasets\raw\run03_indoor_dynamic_100cm_device.csv`
- Run: `run03` / `indoor_dynamic` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `15`
- Alpha: `1.0`
- Quantization block size: `50`
- Offset from calibration phase: `5.7400 dB`

## Bit extraction and reconciliation
- Usable bits: `152`
- Mismatches before reconciliation: `31`
- BDR before reconciliation: `0.20394736842105263`
- Reconciliation block size: `16`
- Reconciliation passes: `4`
- Parity checks revealed: `40`
- Flips applied: `21`
- Mismatches after each pass: `[24, 18, 14, 10]`
- Mismatches after reconciliation: `10`
- BDR after reconciliation: `0.06578947368421052`

## Entropy / leakage estimate
- Entropy per bit: `0.9968755679272235`
- Min-entropy per bit: `0.9080775105589607`
- Estimated total min-entropy before parity leakage: `138.02778160496203`
- Estimated total min-entropy after parity leakage: `98.02778160496203`

## K_auth and binding tag demo
- K_auth match: `False`
- Tag match: `False`
- Tampered transcript tag matches valid tag: `False`

## Interpretation note
This is a simplified block-parity reconciliation prototype.
If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.
If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.