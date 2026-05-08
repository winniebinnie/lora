# rssi_eve_sniffer.py
# Optional MicroPython script for a third ESP32 + SX1276 node.
# Role: Eve/passive observer. Logs any received probe packets with RSSI/SNR.
# Use this after the paired logging works.

from lora import SX1276
import time

RUN_ID = "run01"
ENV_LABEL = "indoor_static"
EVE_POSITION_LABEL = "near_alice"   # examples: near_alice, midpoint, near_network

FREQ_MHZ = 922.0
TX_POWER_DBM = 14
SPREADING_FACTOR = 7
BANDWIDTH_HZ = 125000
CODING_RATE = 5

PIN_SCK = 18
PIN_MOSI = 23
PIN_MISO = 19
PIN_CS = 5
PIN_RST = 17

def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

def configure_lora():
    lora = SX1276(sck=PIN_SCK, mosi=PIN_MOSI, miso=PIN_MISO, cs=PIN_CS, rst=PIN_RST)
    lora.set_frequency(int(FREQ_MHZ * 1000000))
    lora.set_tx_power(TX_POWER_DBM)
    lora.set_spreading_factor(SPREADING_FACTOR)
    try:
        lora.set_bandwidth(BANDWIDTH_HZ)
        lora.set_coding_rate(CODING_RATE)
        lora.set_crc(True)
    except Exception:
        pass
    return lora

def main():
    print("EVE: passive RSSI/SNR sniffer")
    print("EVELOG_HEADER,marker,run_id,env,eve_pos,seq,ptype,freq_mhz,sf,bw_khz,cr,t_ms,rssi_eve,snr_eve,payload_len,raw")

    lora = configure_lora()
    while True:
        rx, rssi, snr = lora.recv(timeout_ms=0)
        t_ms = time.ticks_ms()
        if rx is None:
            continue
        try:
            text = rx.decode()
        except Exception:
            text = "<non_utf8>"
        kv = parse_kvs(text)
        seq = kv.get("seq", "")
        ptype = kv.get("ptype", "")
        print("EVELOG,{},{},{},{},{},{:.3f},{},{},{},{},{},{},{},{}".format(
            RUN_ID, ENV_LABEL, EVE_POSITION_LABEL, seq, ptype,
            FREQ_MHZ, SPREADING_FACTOR, BANDWIDTH_HZ // 1000,
            "4/{}".format(CODING_RATE), t_ms, rssi, snr, len(rx), text
        ))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("EVE: stopped")
