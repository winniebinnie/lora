from lora_min import SX1276
import time
import struct
import uos

# === RADIO CONFIG ===
FREQ_MHZ         = 915.0
TX_POWER = 15       # dBm (2..17 for normal PA_DAC)
SPREADING_FACTOR = 9        # 6..12
ROLE             = "rx"     # "tx" or "rx"

LOG_FILE = "lora_rx_log.csv"

# === RADIO SETUP ===
radio = SX1276()

radio.set_frequency(int(FREQ_MHZ * 1_000_000))
radio.set_tx_power(TX_POWER)
radio.set_spreading_factor(SPREADING_FACTOR)

print("LoRa init done")
print("Freq = %.3f MHz, Power = %d dBm, SF = %d, ROLE = %s" %
      (FREQ_MHZ, TX_POWER, SPREADING_FACTOR, ROLE))


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
        f.write("seq,now_ms,tx_ms,dt_ms,rssi_dbm,snr_db\n")
    return f


# === TX SIDE: send sequence + timestamp ===
def tx_loop(interval_s=1.0):
    seq = 0
    while True:
        seq += 1
        t_ms = time.ticks_ms() & 0xFFFFFFFF

        # payload = [seq (4B)] [tx_timestamp (4B)]
        payload = struct.pack(">II", seq, t_ms)

        ok = radio.send(payload)
        print("[TX] seq=%d len=%d ok=%s" % (seq, len(payload), ok))

        time.sleep(interval_s)


# === RX SIDE: receive and print RSSI/SNR + delay + LOG TO CSV ===
def rx_loop():
    log = open_log()
    print("[RX] Listening...")
    while True:
        payload, rssi_dbm, snr_db = radio.recv(timeout_ms=10_000)

        now_ms = time.ticks_ms() & 0xFFFFFFFF

        if payload is None:
            print("[RX] Timeout / CRC error")
            continue

        if len(payload) >= 8:
            seq, t_ms = struct.unpack(">II", payload[:8])
            dt = time.ticks_diff(now_ms, t_ms)

            print(
                "[RX] seq=%d len=%d RSSI=%.1f dBm SNR=%.2f dB delay=%d ms"
                % (seq, len(payload), rssi_dbm, snr_db, dt)
            )

            # --- เขียนลงไฟล์ CSV ---
            line = "%d,%d,%d,%d,%.1f,%.2f\n" % (
                seq, now_ms, t_ms, dt, rssi_dbm, snr_db
            )
            log.write(line)
            log.flush()  # กันไฟดับ/รีเซ็ตแล้วหาย
        else:
            print(
                "[RX] len=%d RSSI=%.1f dBm SNR=%.2f dB raw=%s"
                % (len(payload), rssi_dbm, snr_db, payload)
            )


# === MAIN ===
if ROLE == "tx":
    tx_loop()
else:
    rx_loop()

