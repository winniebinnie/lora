from lora_min import SX1276
import time
import struct

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

HOP_INTERVAL_MS = 10000          # hop every 1 second (must match RX)
SECRET_SEED     = 0x1234ABCD    # same as RX

def _prn_from_slot(slot):
    x = (SECRET_SEED ^ slot) & 0xFFFFFFFF
    x = (1103515245 * x + 12345) & 0x7FFFFFFF
    return x

def get_hop_frequency():
    slot = time.ticks_ms() // HOP_INTERVAL_MS
    prn = _prn_from_slot(slot)
    idx = prn % len(FREQ_TABLE_MHZ)
    return FREQ_TABLE_MHZ[idx], slot

def set_hop_frequency(radio):
    freq_mhz, slot = get_hop_frequency()
    radio.set_frequency(int(freq_mhz * 1_000_000))
    return freq_mhz, slot

# ========= NORMAL RADIO CONFIG =========
TX_POWER         = 15     # dBm (2..17 for normal PA_DAC)
SPREADING_FACTOR = 9      # 6..12
ROLE             = "tx"   # this file is the TX side

# === RADIO SETUP ===
radio = SX1276()
radio.set_tx_power(TX_POWER)
radio.set_spreading_factor(SPREADING_FACTOR)

freq_mhz, slot = set_hop_frequency(radio)

print("LoRa init done")
print("Initial Freq = %.3f MHz, Power = %d dBm, SF = %d, ROLE = %s" %
      (freq_mhz, TX_POWER, SPREADING_FACTOR, ROLE))


# === TX SIDE: send sequence + timestamp, with FHSS ===
def tx_loop(interval_s=1.0):
    seq = 0
    while True:
        seq += 1
        t_ms = time.ticks_ms() & 0xFFFFFFFF

        # move to current hop frequency before sending
        freq_mhz, slot = set_hop_frequency(radio)

        # payload = [seq (4B)] [tx_timestamp (4B)]
        payload = struct.pack(">II", seq, t_ms)

        ok = radio.send(payload)
        print("[TX] seq=%d len=%d ok=%s freq=%.3f MHz slot=%d" %
              (seq, len(payload), ok, freq_mhz, slot))

        time.sleep(interval_s)


# === RX SIDE: (not used here, but kept for symmetry/debug) ===
def rx_loop():
    print("[RX in TX script] Listening... (debug only)")
    while True:
        freq_mhz, slot = set_hop_frequency(radio)
        payload, rssi_dbm, snr_db = radio.recv(timeout_ms=1500)
        now_ms = time.ticks_ms() & 0xFFFFFFFF

        if payload is None:
            print("[RX] Timeout / CRC error on freq=%.3f MHz slot=%d" %
                  (freq_mhz, slot))
            continue

        if len(payload) >= 8:
            seq, t_ms = struct.unpack(">II", payload[:8])
            dt = time.ticks_diff(now_ms, t_ms)
            print(
                "[RX] seq=%d len=%d RSSI=%.1f dBm SNR=%.2f dB "
                "delay=%d ms freq=%.3f MHz slot=%d"
                % (seq, len(payload), rssi_dbm, snr_db, dt, freq_mhz, slot)
            )
        else:
            print(
                "[RX] len=%d RSSI=%.1f dBm SNR=%.2f dB "
                "freq=%.3f MHz slot=%d raw=%s"
                % (len(payload), rssi_dbm, snr_db, freq_mhz, slot, payload)
            )


# === MAIN ===
if ROLE == "tx":
    tx_loop()
else:
    rx_loop()

