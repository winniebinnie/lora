# Simple LoRa receiver for ESP32 + SX1276 (MicroPython)
from lora_min import SX1276
import time

# === CONFIG ===
FREQ_MHZ = 915.0     # Must match sender
SPREADING_FACTOR = 7 # Must match sender

def main():
    print("LoRa receiver starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_spreading_factor(SPREADING_FACTOR)

    while True:
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        if payload is None:
            # CRC error or timeout (timeout=0 means shouldn't happen)
            print("RX error/CRC")
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeError:
            text = str(payload)
        print("RX:", text, "| RSSI:", rssi, "dBm | SNR:", snr, "dB")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
