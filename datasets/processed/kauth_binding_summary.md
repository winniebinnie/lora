# RSSI-derived K_auth Binding Summary

| Run | Environment | Usable Bits Before Reconciliation | BDR | Final Bits | K_auth Match | Tag Match | Tampered Tag Rejected | Interpretation |
|---|---|---:|---:|---:|---|---|---|---|
| run02 | indoor static | 296 | 9.80% | 267 | True | True | True | Works, but needs reconciliation |
| run03 | indoor dynamic | 152 | 20.39% | 121 | True | True | True | Weak; dynamic movement hurts agreement |
| run04 | outdoor LOS | 206 | 1.46% | 203 | True | True | True | Strongest condition |

## Interpretation

The K_auth demo shows that the combined RSSI + EDHOC-binding pipeline is feasible. The method can derive matching RSSI-based authentication material and use it to verify an EDHOC-style HMAC binding tag. Outdoor LOS and indoor static conditions are more suitable than indoor dynamic movement.

The current implementation still uses oracle reconciliation, so the next step is to replace it with a deployable reconciliation method such as block-parity reconciliation.