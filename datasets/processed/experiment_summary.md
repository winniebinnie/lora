| Run | Environment | Pairs | Window | Alpha | Usable Bits | Discard Rate | BDR | Entropy | KGR |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| run01 | indoor static tuning | 486 | 21 | 0.75 | 177 | 63.6% | 2.26% | 0.9989 | 0.6227 |
| run02 | indoor static repeat | 993 | 21 | 0.75 | 340 | 65.8% | 9.41% | 0.9998 | 0.6088 |
| run03 | indoor dynamic | 991 | 1 | 1.0 | 72 | 92.7% | 19.44% | 0.9978 | 0.1304 |
| run04 | outdoor LOS | 987 | 21 | 1.0 | 248 | 74.9% | 1.21% | 0.9921 | 0.4403 |

Phase 1 shows that RSSI-assisted bootstrapping is feasible under controlled indoor static and outdoor LOS conditions, but uncontrolled indoor movement reduces bit agreement. The results suggest that RSSI offset calibration, MWA window size, and adaptive quantization are key design factors.