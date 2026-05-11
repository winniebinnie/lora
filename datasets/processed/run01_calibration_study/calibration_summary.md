# Calibration Study Summary

Input file: `datasets\raw\run01_indoor_static_100cm_device.csv`

Online calibration pairs: `100`

Minimum usable bits for practical ranking: `128`


## Best candidate by calibration mode

| calibration_mode   |   n_total_pairs |   n_calibration_pairs |   n_keygen_pairs |   window |   alpha |   offset_device_minus_network_db |   usable_bits |   discard_rate |   mismatches |       bdr |   entropy_bits_per_bit |   min_entropy_bits_per_bit |   estimated_min_entropy_bits_total |   kgr_bps_before_reconciliation |
|:-------------------|----------------:|----------------------:|-----------------:|---------:|--------:|---------------------------------:|--------------:|---------------:|-------------:|----------:|-----------------------:|---------------------------:|-----------------------------------:|--------------------------------:|
| full               |             486 |                     0 |              486 |       21 |    0.75 |                          2.56996 |           177 |       0.635802 |            4 | 0.0225989 |               0.998871 |                   0.944044 |                            167.096 |                        0.622693 |
| none               |             486 |                     0 |              486 |       21 |    0.75 |                          0       |           177 |       0.635802 |            4 | 0.0225989 |               0.998871 |                   0.944044 |                            167.096 |                        0.622693 |
| online_100         |             486 |                   100 |              386 |       21 |    0.75 |                          3.3     |           141 |       0.634715 |            2 | 0.0141844 |               0.999093 |                   0.949727 |                            133.911 |                        0.64468  |


## Notes

- `none` is the no-calibration baseline.

- `full` is an optimistic offline upper bound because it estimates offset from the whole dataset.

- `online_N` is the deployable-style mode: first N pairs calibrate offset; remaining pairs generate bits.
