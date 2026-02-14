"""
Mobility Experiment 1 — BEACON Logger (Bob or Eve)
MicroPython (ESP32 + SX1276)

Logs RSSI/SNR for beacon packets, writing CSV rows to a file on the board.

Key idea:
- The beacon includes pkt_id.
- Bob and Eve will log the SAME pkt_id → same transmitted packet → "simultaneous" evidence.

Files needed on the board:
- lora_min.py   (your SX1276 driver)

How to use:
1) Copy this file + lora_min.py to the receiver board.
2) Edit CONFIG section:
   - RX_NAME = "bob" or "eve"
   - DISTANCE_CM = 0, 5, 10, ...
3) Run: import mobility_receiver

CSV output path (on the board):
- mobility.csv (append mode)

Tip:
- To avoid duplicate headers, delete mobility.csv between experiment runs if you want.
"""

import time
from lora_min import SX1276

# ---------------- CONFIG ----------------
RX_NAME = "bob"           # "bob" or "eve"
RUN_ID_FILTER = None      # set to an int to only log a single run_id, else None
DISTANCE_CM = 0           # set before each 5cm step (0,5,10,...)
LOG_PATH = "mobility.csv"

BEACON_FREQ_MHZ = 923.2   # must match sender
RX_TIMEOUT_MS = 2000

TX_POWER_DBM = 14         # not used for RX, kept for printing consistency
SPREADING_FACTOR = 7

# SX1276 wiring (edit to match your board)
SPI_ID = 1
SCK = 18
MOSI = 23
MISO = 19
CS = 5
RST = 17
# ----------------------------------------


def parse_kvs(s: str):
    """Parse 'k=v,k2=v2' into dict."""
    out = {}
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def ensure_header():
    hdr = "run_id,distance_cm,rx_name,pkt_id,t_ms_local,rssi_dbm,snr_db,freq_mhz\n"
    try:
        # Only write header if file doesn't exist / empty
        import os
        st = os.stat(LOG_PATH)
        if st[6] == 0:
            with open(LOG_PATH, "a") as f:
                f.write(hdr)
    except:
        # If stat fails, try creating + writing header
        try:
            with open(LOG_PATH, "a") as f:
                f.write(hdr)
        except:
            pass


def main():
    lora = SX1276(spi_id=SPI_ID, sck=SCK, mosi=MOSI, miso=MISO, cs=CS, rst=RST)
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_frequency(int(BEACON_FREQ_MHZ * 1_000_000))

    # Enter continuous RX once; then poll with recv_keep_rx for faster loop
    lora.rx_continuous()

    ensure_header()

    print("BEACON LOGGER start | rx_name={} distance_cm={} | freq={} MHz | SF={}".format(
        RX_NAME, DISTANCE_CM, BEACON_FREQ_MHZ, SPREADING_FACTOR
    ))

    while True:
        payload, rssi, snr = lora.recv_keep_rx(timeout_ms=RX_TIMEOUT_MS)
        if payload is None:
            continue

        try:
            text = payload.decode()
        except:
            continue

        kv = parse_kvs(text)
        if kv.get("kind") != "beacon":
            continue

        run_id = kv.get("run", "?")
        if RUN_ID_FILTER is not None and str(RUN_ID_FILTER) != str(run_id):
            continue

        pkt_id = kv.get("pkt", "?")
        t_local = time.ticks_ms()

        line = "{},{},{},{},{},{},{},{}\n".format(
            run_id, DISTANCE_CM, RX_NAME, pkt_id, t_local, rssi, snr, BEACON_FREQ_MHZ
        )

        print(line.strip())
        try:
            with open(LOG_PATH, "a") as f:
                f.write(line)
        except Exception as e:
            print("log write err:", e)


# Auto-run when imported (MicroPython style)
main()
