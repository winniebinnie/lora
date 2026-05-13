# RSSI-derived K_auth with block-parity reconciliation

- Input: `datasets\processed\probe_sweep_run04_tuned_threshold\subsets\subset_450pairs.csv`
- Run: `run04` / `outdoor_los` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `31`
- Alpha: `0.25`
- Quantization block size: `100`
- Offset from calibration phase: `1.4600 dB`

## Bit extraction and reconciliation
- Usable bits: `298`
- Mismatches before reconciliation: `0`
- BDR before reconciliation: `0.0`
- Reconciliation block size: `16`
- Reconciliation passes: `4`
- Parity checks revealed: `76`
- Flips applied: `0`
- Mismatches after each pass: `[0, 0, 0, 0]`
- Mismatches after reconciliation: `0`
- BDR after reconciliation: `0.0`

## Entropy / leakage estimate
- Entropy per bit: `0.9984073220991563`
- Min-entropy per bit: `0.9337663015999131`
- Estimated total min-entropy before parity leakage: `278.2623578767741`
- Estimated total min-entropy after parity leakage: `202.2623578767741`

## K_auth and binding tag demo
- K_auth match: `True`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Interpretation note
This is a simplified block-parity reconciliation prototype.
If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.
If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.