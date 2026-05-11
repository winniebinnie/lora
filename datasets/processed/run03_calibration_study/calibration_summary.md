# Calibration Study Summary

Input file: `datasets\raw\run03_indoor_dynamic_100cm_device.csv`

Online calibration pairs: `100`

Minimum usable bits for practical ranking: `128`


## Best candidate by calibration mode

| calibration_mode   |   n_total_pairs |   n_calibration_pairs |   n_keygen_pairs |   window |   alpha |   offset_device_minus_network_db |   usable_bits |   discard_rate |   mismatches |      bdr |   entropy_bits_per_bit |   min_entropy_bits_per_bit |   estimated_min_entropy_bits_total |   kgr_bps_before_reconciliation |
|:-------------------|----------------:|----------------------:|-----------------:|---------:|--------:|---------------------------------:|--------------:|---------------:|-------------:|---------:|-----------------------:|---------------------------:|-----------------------------------:|--------------------------------:|
| full               |             991 |                     0 |              991 |       15 |       1 |                          6.66398 |           157 |       0.841574 |           35 | 0.22293  |               0.997628 |                   0.919581 |                            144.374 |                        0.284317 |
| none               |             991 |                     0 |              991 |       15 |       1 |                          0       |           157 |       0.841574 |           35 | 0.22293  |               0.997628 |                   0.919581 |                            144.374 |                        0.284317 |
| online_100         |             991 |                   100 |              891 |       15 |       1 |                          5.74    |           152 |       0.829405 |           31 | 0.203947 |               0.996876 |                   0.908078 |                            138.028 |                        0.306138 |


## Notes

- `none` is the no-calibration baseline.

- `full` is an optimistic offline upper bound because it estimates offset from the whole dataset.

- `online_N` is the deployable-style mode: first N pairs calibrate offset; remaining pairs generate bits.
