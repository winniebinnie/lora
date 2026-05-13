# RSSI-derived K_auth with block-parity reconciliation

- Input: `datasets\processed\probe_sweep_run04\subsets\subset_700pairs.csv`
- Run: `run04` / `outdoor_los` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `21`
- Alpha: `1.0`
- Quantization block size: `50`
- Offset from calibration phase: `1.4600 dB`

## Bit extraction and reconciliation
- Usable bits: `164`
- Mismatches before reconciliation: `1`
- BDR before reconciliation: `0.006097560975609756`
- Reconciliation block size: `16`
- Reconciliation passes: `4`
- Parity checks revealed: `44`
- Flips applied: `1`
- Mismatches after each pass: `[0, 0, 0, 0]`
- Mismatches after reconciliation: `0`
- BDR after reconciliation: `0.0`

## Entropy / leakage estimate
- Entropy per bit: `0.9723594643683988`
- Min-entropy per bit: `0.7428421605028755`
- Estimated total min-entropy before parity leakage: `121.8261143224716`
- Estimated total min-entropy after parity leakage: `77.8261143224716`

## K_auth and binding tag demo
- K_auth match: `True`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Interpretation note
This is a simplified block-parity reconciliation prototype.
If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.
If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.