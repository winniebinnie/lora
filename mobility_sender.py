"""
Mobility Experiment 1 — BEACON Sender (Alice)
MicroPython (ESP32 + SX1276)

Sends 1 beacon packet per second on a fixed frequency so that two receivers (Bob + Eve)
can log RSSI/SNR for the SAME packet_id (stronger than "same second").

Files needed on the board:
- lora_min.py   (your SX1276 driver)

How to use:
1) Copy this file + lora_min.py to the sender board.
2) Edit CONFIG section below if needed (pins/freq/tx power/sf).
3) Run: import mobility_sender

Output:
BEACON TX ok pkt=... t=... freq=...
"""

import time
from lora_min import SX1276

# ---------------- CONFIG ----------------
RUN_ID = 1                # increment each full experiment run
BEACON_FREQ_MHZ = 923.2   # fixed channel for Experiment 1
BEACON_PERIOD_MS = 1000   # 1 Hz

TX_POWER_DBM = 14
SPREADING_FACTOR = 7

# SX1276 wiring (edit to match your board)
SPI_ID = 1
SCK = 18
MOSI = 23
MISO = 19
CS = 5
RST = 17
# ----------------------------------------


def main():
    lora = SX1276(spi_id=SPI_ID, sck=SCK, mosi=MOSI, miso=MISO, cs=CS, rst=RST)
    lora.set_tx_power(TX_POWER_DBM)
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_frequency(int(BEACON_FREQ_MHZ * 1_000_000))

    pkt = 0
    print("BEACON SENDER start | run={} freq={} MHz | P={} dBm SF={}".format(
        RUN_ID, BEACON_FREQ_MHZ, TX_POWER_DBM, SPREADING_FACTOR
    ))

    while True:
        t_ms = time.ticks_ms()
        payload = "kind=beacon,run={},pkt={},t={}".format(RUN_ID, pkt, t_ms).encode()

        ok = lora.send(payload, timeout_ms=1500)
        if ok:
            print("BEACON TX ok pkt={} t={} freq={:.3f}".format(pkt, t_ms, BEACON_FREQ_MHZ))
        else:
            print("BEACON TX timeout pkt={} t={}".format(pkt, t_ms))

        pkt += 1
        time.sleep_ms(BEACON_PERIOD_MS)


# Auto-run when imported (MicroPython style)
main()
