# Preliminary EDHOC Bootstrap Result: Run04

The run04 outdoor LOS result demonstrates functional feasibility of the proposed RSSI-bound EDHOC bootstrap.

Compared with EDHOC-only, the RSSI-bound version adds physical-layer binding through RSSI-derived K_auth and Tag_phy verification.

The result shows:
- K_auth matched on both sides.
- Tag_phy verification succeeded.
- Wrong K_auth was rejected.
- Tampered transcript was rejected.
- Bound session keys matched.
- BDR was reduced to 0% after reconciliation.

However, the estimated post-leakage min-entropy is approximately 111 bits, which is below the 128-bit target. Therefore, this result supports functional feasibility but does not yet justify a full 128-bit security claim.