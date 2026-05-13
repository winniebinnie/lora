# RSSI-derived K_auth with block-parity reconciliation

- Input: `datasets\raw\run02_indoor_static_100cm_device.csv`
- Run: `run02` / `indoor_static` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `21`
- Alpha: `0.75`
- Quantization block size: `50`
- Offset from calibration phase: `5.7600 dB`

## Bit extraction and reconciliation
- Usable bits: `296`
- Mismatches before reconciliation: `29`
- BDR before reconciliation: `0.09797297297297297`
- Reconciliation block size: `16`
- Reconciliation passes: `4`
- Parity checks revealed: `76`
- Flips applied: `27`
- Mismatches after each pass: `[22, 14, 6, 2]`
- Mismatches after reconciliation: `2`
- BDR after reconciliation: `0.006756756756756757`

## Entropy / leakage estimate
- Entropy per bit: `0.9991765376178505`
- Min-entropy per bit: `0.952065522936298`
- Estimated total min-entropy before parity leakage: `281.8113947891442`
- Estimated total min-entropy after parity leakage: `205.81139478914417`

## K_auth and binding tag demo
- K_auth match: `False`
- Tag match: `False`
- Tampered transcript tag matches valid tag: `False`

## Interpretation note
This is a simplified block-parity reconciliation prototype.
If mismatches after reconciliation is zero, the two parties can derive the same K_auth without oracle filtering.
If mismatches remain, K_auth/tag verification should fail, showing that stronger reconciliation is needed.