# RSSI-derived K_auth demo

- Input: `datasets\raw\run03_indoor_dynamic_100cm_device.csv`
- Run: `run03` / `indoor_dynamic` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `15`
- Alpha: `1.0`
- Block size: `50`
- Offset from calibration phase: `5.7400 dB`

## Bit extraction
- Usable bits before reconciliation: `152`
- Mismatches before reconciliation: `31`
- BDR before reconciliation: `0.20394736842105263`
- Reconciliation mode: `oracle`
- Final bits after reconciliation: `121`
- Entropy after reconciliation: `0.9916574448985775`
- Min-entropy per bit after reconciliation: `0.852774046816822`
- Estimated total min-entropy after reconciliation: `103.18565966483547`

## K_auth and binding tag demo
- K_auth device: `1a307c43cb83bde56e86a27654052e62`
- K_auth network: `1a307c43cb83bde56e86a27654052e62`
- K_auth match: `True`
- Tag device: `bd6fd9c97cb575d431ac709411996a01`
- Tag network: `bd6fd9c97cb575d431ac709411996a01`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Important limitation
If reconciliation mode is `oracle`, this is only a prototype demonstration.
It proves the pipeline from RSSI bits to K_auth to an EDHOC-style binding tag,
but it must later be replaced by a real information reconciliation method.