# Calibration Study Summary

Input file: `datasets\raw\run04_outdoor_los_100cm_device.csv`

Online calibration pairs: `100`

Minimum usable bits for practical ranking: `128`


## Best candidate by calibration mode

| calibration_mode   |   n_total_pairs |   n_calibration_pairs |   n_keygen_pairs |   window |   alpha |   offset_device_minus_network_db |   usable_bits |   discard_rate |   mismatches |       bdr |   entropy_bits_per_bit |   min_entropy_bits_per_bit |   estimated_min_entropy_bits_total |   kgr_bps_before_reconciliation |
|:-------------------|----------------:|----------------------:|-----------------:|---------:|--------:|---------------------------------:|--------------:|---------------:|-------------:|----------:|-----------------------:|---------------------------:|-----------------------------------:|--------------------------------:|
| full               |             987 |                     0 |              987 |       21 |       1 |                          1.80041 |           248 |       0.748734 |            3 | 0.0120968 |               0.992057 |                   0.856164 |                            212.329 |                        0.440308 |
| none               |             987 |                     0 |              987 |       21 |       1 |                          0       |           248 |       0.748734 |            3 | 0.0120968 |               0.992057 |                   0.856164 |                            212.329 |                        0.440308 |
| online_100         |             987 |                   100 |              887 |       21 |       1 |                          1.46    |           206 |       0.767756 |            3 | 0.0145631 |               0.982523 |                   0.791683 |                            163.087 |                        0.406818 |


## Notes

- `none` is the no-calibration baseline.

- `full` is an optimistic offline upper bound because it estimates offset from the whole dataset.

- `online_N` is the deployable-style mode: first N pairs calibrate offset; remaining pairs generate bits.
