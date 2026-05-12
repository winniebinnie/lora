# RSSI-derived K_auth demo

- Input: `datasets\raw\run04_outdoor_los_100cm_device.csv`
- Run: `run04` / `outdoor_los` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `21`
- Alpha: `1.0`
- Block size: `50`
- Offset from calibration phase: `1.4600 dB`

## Bit extraction
- Usable bits before reconciliation: `206`
- Mismatches before reconciliation: `3`
- BDR before reconciliation: `0.014563106796116505`
- Reconciliation mode: `oracle`
- Final bits after reconciliation: `203`
- Entropy after reconciliation: `0.9784493292686189`
- Min-entropy per bit after reconciliation: `0.7705181538772325`
- Estimated total min-entropy after reconciliation: `156.41518523707822`

## K_auth and binding tag demo
- K_auth device: `e4484b229bbc806204413d508774fcb8`
- K_auth network: `e4484b229bbc806204413d508774fcb8`
- K_auth match: `True`
- Tag device: `35c2bcf7a276f4f329f7bb9c04b7fea8`
- Tag network: `35c2bcf7a276f4f329f7bb9c04b7fea8`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Important limitation
If reconciliation mode is `oracle`, this is only a prototype demonstration.
It proves the pipeline from RSSI bits to K_auth to an EDHOC-style binding tag,
but it must later be replaced by a real information reconciliation method.