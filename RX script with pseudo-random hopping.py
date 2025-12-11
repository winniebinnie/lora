from lora_min import SX1276
import time
import struct
import uos

# ========= FHSS SHARED CONFIG (MUST MATCH ON TX & RX) =========
FREQ_TABLE_MHZ = [
    914.0,
    914.3,
    914.6,
    914.9,
    915.2,
    915.5,
    915.8,
    916.1,
]

HOP_INTERVAL_MS = 10000          # hop every 1 second (adjust as needed)
SECRET_SEED     = 0x1234ABCD    # any 32-bit value, but SAME on both sides

def _prn_from_slot(slot):
    """
    Very simple 32-bit LCG-based PRN derived from the time slot.
    Deterministic and stateless: same slot => same PRN on both ends.
    """
    x = (SECRET_SEED ^ slot) & 0xFFFFFFFF
    x = (1103515245 * x + 12345) & 0x7FFFFFFF
    return x

def get_hop_frequency():
    """
    Returns the current hop frequency in MHz based on the current time slot.
    """
    slot = time.ticks_ms() // HOP_INTERVAL_MS
    prn = _prn_from_slot(slot)
    idx = prn % len(FREQ_TABLE_MHZ)
    return FREQ_TABLE_MHZ[idx], slot

def set_hop_frequency(radio):
    """
    Compute current hop frequency and apply it to the radio.
    Returns (freq_mhz, slot).
    """
    freq_mhz, slot = get_hop_frequency()
    radio.set_frequency(int(freq_mhz * 1_000_000))
    return freq_mhz, slot

# ========= NORMAL RADIO CONFIG =========
TX_POWER         = 15       # dBm (2..17 for normal PA_DAC)
SPREADING_FACTOR = 9        # 6..12
ROLE             = "rx"     # this file is the RX side

LOG_FILE = "lora_rx_log.csv"

# === RADIO SETUP ===
radio = SX1276()
radio.set_tx_power(TX_POWER)
radio.set_spreading_factor(SPREADING_FACTOR)

# apply initial hop frequency
freq_mhz, slot = set_hop_frequency(radio)

print("LoRa init done")
print("Initial Freq = %.3f MHz, Power = %d dBm, SF = %d, ROLE = %s" %
      (freq_mhz, TX_POWER, SPREADING_FACTOR, ROLE))


def open_log():
    """เปิดไฟล์ log และเขียน header ถ้ายังไม่มีไฟล์"""
    try:
        uos.stat(LOG_FILE)
        exists = True
    except OSError:
        exists = False

    f = open(LOG_FILE, "a")
    if not exists:
        # เขียน header แถวแรก
        f.write("seq,now_ms,tx_ms,dt_ms,rssi_dbm,snr_db,freq_mhz,slot\n")
    return f


# === RX SIDE: receive and print RSSI/SNR + delay + LOG TO CSV ===
def rx_loop():
    log = open_log()
    print("[RX] Listening with pseudo-random frequency hopping...")

    while True:
        # before each receive attempt, move to the current hop frequency
        freq_mhz, slot = set_hop_frequency(radio)

        # short timeout so we don't get stuck on the wrong channel for too long
        payload, rssi_dbm, snr_db = radio.recv(timeout_ms=1500)

        now_ms = time.ticks_ms() & 0xFFFFFFFF

        if payload is None:
            print("[RX] Timeout / CRC error on freq=%.3f MHz (slot=%d)" %
                  (freq_mhz, slot))
            # next loop iteration will hop automatically by time
            continue

        if len(payload) >= 8:
            seq, t_ms = struct.unpack(">II", payload[:8])
            dt = time.ticks_diff(now_ms, t_ms)

            print(
                "[RX] seq=%d len=%d RSSI=%.1f dBm SNR=%.2f dB "
                "delay=%d ms freq=%.3f MHz slot=%d"
                % (seq, len(payload), rssi_dbm, snr_db, dt, freq_mhz, slot)
            )

            # --- เขียนลงไฟล์ CSV ---
            line = "%d,%d,%d,%d,%.1f,%.2f,%.3f,%d\n" % (
                seq, now_ms, t_ms, dt, rssi_dbm, snr_db, freq_mhz, slot
            )
            log.write(line)
            log.flush()  # กันไฟดับ/รีเซ็ตแล้วหาย
        else:
            print(
                "[RX] len=%d RSSI=%.1f dBm SNR=%.2f dB "
                "freq=%.3f MHz slot=%d raw=%s"
                % (len(payload), rssi_dbm, snr_db, freq_mhz, slot, payload)
            )


# === MAIN ===
if ROLE == "tx":
    raise RuntimeError("This file is configured as RX (ROLE='rx')")
else:
    rx_loop()

