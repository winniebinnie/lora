from lora import SX1276
import time

FREQ_MHZ = 922.0
TX_POWER_DBM = 2
SF = 7
BW = 125000
CR = 5

lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)

print("TX DEBUG")
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

seq = 0

while True:
    msg = "ping=%d" % seq
    ok = lora.send(msg.encode(), timeout_ms=3000)
    print("TX:", msg, "ok=", ok)
    seq += 1
    time.sleep(1)