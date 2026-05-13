# RSSI-derived K_auth with block-parity reconciliation

- Input: `datasets\raw\run04_outdoor_los_100cm_device.csv`
- Run: `run04` / `outdoor_los` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `21`
- Alpha: `1.0`
- Quantization block size: `50`
- Offset from calibration phase: `1.4600 dB`

## Bit extraction and reconciliation
- Usable bits: `206`
- Mismatches before reconciliation: `3`
- BDR before reconciliation: `0.014563106796116505`
- Reconciliation block size: `32`
- Reconciliation passes: `4`
- Parity checks revealed: `28`
- Flips applied: `3`
- Mismatches after each pass: `[2, 0, 0, 0]`
- Mismatches after reconciliation: `0`
- BDR after reconciliation: `0.0`

## Entropy / leakage estimate
- Entropy per bit: `0.9825228671226133`
- Min-entropy per bit: `0.7916827638752749`
- Estimated total min-entropy before parity leakage: `163.08664935830663`
- Estimated total min-entropy after parity leakage: `135.08664935830663`

## K_auth and binding tag demo
- K_auth match: `True`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Interpretation note
This is a simplified block-parity reconciliation prototype.
If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.
If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.