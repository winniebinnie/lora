# Simple LoRa sender for ESP32 + SX1276 (MicroPython)
from lora_min import SX1276
import time

# === CONFIG ===
FREQ_MHZ = 915.0   # Change to 868.0 in EU, 923.0 in some APAC bands, etc.
TX_POWER = 14      # dBm (2..17 with PA_BOOST normal mode)
SPREADING_FACTOR = 7  # 6..12; keep same as receiver

def main():
    print("LoRa sender starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    counter = 0
    while True:
        msg = "hello {}, t={}".format(counter, time.ticks_ms())
        ok = lora.send(msg.encode("utf-8"), timeout_ms=5000)
        if ok:
            print("TX ok:", msg)
        else:
            print("TX timeout!")
        counter += 1
        time.sleep(2)  # send every 2 seconds

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
