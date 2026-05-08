from lora import SX1276
import time, ubinascii

FREQ_MHZ = 922.0
TX_POWER_DBM = 2
SF = 7
BW = 125000
CR = 5

lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)

print("RX DEBUG")
print("Chip OK")
print("Setting frequency:", FREQ_MHZ)

lora.set_frequency(int(FREQ_MHZ * 1000000))
lora.set_tx_power(TX_POWER_DBM)
lora.set_spreading_factor(SF)

try:
    lora.set_bandwidth(BW)
    print("BW set OK")
except Exception as e:
    print("BW warn:", e)

try:
    lora.set_coding_rate(CR)
    print("CR set OK")
except Exception as e:
    print("CR warn:", e)

try:
    lora.set_crc(True)
except Exception:
    pass

print("Listening on %.3f MHz, SF=%d, TX power setting=%d" % (FREQ_MHZ, SF, TX_POWER_DBM))

while True:
    payload, rssi, snr = lora.recv(timeout_ms=5000)

    if payload is None:
        print("RX timeout")
        continue

    try:
        text = payload.decode()
    except Exception:
        text = ubinascii.hexlify(payload)

    print("RX payload:", text, "| RSSI:", rssi, "| SNR:", snr)