# RSSI-derived K_auth demo

- Input: `datasets\raw\run02_indoor_static_100cm_device.csv`
- Run: `run02` / `indoor_static` / 100 cm / 922.0 MHz
- Online calibration pairs: `100`
- MWA window: `21`
- Alpha: `0.75`
- Block size: `50`
- Offset from calibration phase: `5.7600 dB`

## Bit extraction
- Usable bits before reconciliation: `296`
- Mismatches before reconciliation: `29`
- BDR before reconciliation: `0.09797297297297297`
- Reconciliation mode: `oracle`
- Final bits after reconciliation: `267`
- Entropy after reconciliation: `0.9999089303498085`
- Min-entropy per bit after reconciliation: `0.983880334636723`
- Estimated total min-entropy after reconciliation: `262.69604934800503`

## K_auth and binding tag demo
- K_auth device: `33c1a09cce412b4989893a2d315a0e72`
- K_auth network: `33c1a09cce412b4989893a2d315a0e72`
- K_auth match: `True`
- Tag device: `4f500aa822f2edbf3e13d87c61dcf0f3`
- Tag network: `4f500aa822f2edbf3e13d87c61dcf0f3`
- Tag match: `True`
- Tampered transcript tag matches valid tag: `False`

## Important limitation
If reconciliation mode is `oracle`, this is only a prototype demonstration.
It proves the pipeline from RSSI bits to K_auth to an EDHOC-style binding tag,
but it must later be replaced by a real information reconciliation method.