# Calibration Study Summary

Input file: `datasets\raw\run02_indoor_static_100cm_device.csv`

Online calibration pairs: `100`

Minimum usable bits for practical ranking: `128`


## Best candidate by calibration mode

| calibration_mode   |   n_total_pairs |   n_calibration_pairs |   n_keygen_pairs |   window |   alpha |   offset_device_minus_network_db |   usable_bits |   discard_rate |   mismatches |       bdr |   entropy_bits_per_bit |   min_entropy_bits_per_bit |   estimated_min_entropy_bits_total |   kgr_bps_before_reconciliation |
|:-------------------|----------------:|----------------------:|-----------------:|---------:|--------:|---------------------------------:|--------------:|---------------:|-------------:|----------:|-----------------------:|---------------------------:|-----------------------------------:|--------------------------------:|
| full               |             993 |                     0 |              993 |       21 |    0.75 |                          4.65861 |           340 |       0.657603 |           32 | 0.0941176 |               0.999775 |                   0.974763 |                            331.419 |                        0.608819 |
| none               |             993 |                     0 |              993 |       21 |    0.75 |                          0       |           340 |       0.657603 |           32 | 0.0941176 |               0.999775 |                   0.974763 |                            331.419 |                        0.608819 |
| online_100         |             993 |                   100 |              893 |       21 |    0.75 |                          5.76    |           296 |       0.668533 |           29 | 0.097973  |               0.999177 |                   0.952066 |                            281.811 |                        0.601448 |


## Notes

- `none` is the no-calibration baseline.

- `full` is an optimistic offline upper bound because it estimates offset from the whole dataset.

- `online_N` is the deployable-style mode: first N pairs calibrate offset; remaining pairs generate bits.
