# Mobility Experiment 1 (5cm increments) — Ready-to-run files

This experiment produces **committee-proof** data by logging RSSI/SNR from the **same transmitted packet_id** on two receivers (Bob + Eve).

## Files
- `mobility_sender.py` — Sender (Alice): transmits 1 beacon per second on a fixed frequency.
- `mobility_receiver.py` — Receiver logger (Bob or Eve): logs RSSI/SNR to `mobility.csv`.
- `lora_min.py` — Your SX1276 driver (already provided).

## Hardware (3 boards)
- **Alice (sender)**: runs `mobility_sender.py`
- **Bob (receiver)**: runs `mobility_receiver.py` with `RX_NAME="bob"`
- **Eve (reference receiver)**: runs `mobility_receiver.py` with `RX_NAME="eve"`

## Physical setup
- Mark distances: 0cm, 5cm, 10cm, … up to 100–200cm.
- Keep antenna orientation and height consistent.
- **Eve stays fixed** for the whole run.
- Move **Bob only**.

## Run procedure (per distance)
For each distance mark:
1. Set Bob at the mark.
2. Edit `DISTANCE_CM = <value>` in Bob’s `mobility_receiver.py`.
3. Re-run Bob (so rows are labeled with correct distance).
4. Collect **~10 packets** (≈ 10 seconds).
5. Repeat for next mark.

### Notes
- If you want a clean file each run: delete `mobility.csv` on each receiver before starting.
- You can keep appending; just keep `run_id` and distance labeling consistent.

## CSV columns (on each receiver)
`run_id,distance_cm,rx_name,pkt_id,t_ms_local,rssi_dbm,snr_db,freq_mhz`

### Why this is "simultaneous"
Bob and Eve rows share the **same pkt_id**, meaning they are from the **exact same transmitted packet** (stronger than “same second”).

## Afterward (analysis)
For each distance:
- compute median/mean RSSI and std/IQR for Bob and Eve
- compute pairwise deltas: RSSI(distance+5cm) − RSSI(distance)
