# rssi_probe_network.py
# MicroPython script for ESP32 + SX1276.
# Role: Network-Side Entity. Receives probe requests, logs uplink RSSI/SNR,
# and sends them back in a response so the End Device can print paired CSV rows.

from lora import SX1276
import time

# ---------------- User experiment config ----------------
RUN_ID = "run04"
ENV_LABEL = "outdoor_los"
DISTANCE_CM = 100

FREQ_MHZ = 922.0
TX_POWER_DBM = 14
SPREADING_FACTOR = 7
BANDWIDTH_HZ = 125000
CODING_RATE = 5                  # 5 means LoRa coding rate 4/5

REPLY_DELAY_MS = 60              # small turnaround delay after receiving request

# ESP32 <-> SX1276 pins, matching your current lora.py defaults
PIN_SCK = 18
PIN_MOSI = 23
PIN_MISO = 19
PIN_CS = 5
PIN_RST = 17

# --------------------------------------------------------

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
    except Exception as e:
        print("WARN: set_bandwidth failed:", e)
    try:
        lora.set_coding_rate(CODING_RATE)
    except Exception as e:
        print("WARN: set_coding_rate failed:", e)
    try:
        lora.set_crc(True)
    except Exception:
        pass
    return lora

def print_netlog(seq, t_ms, rssi, snr, payload_len, ok):
    # NETLOG is optional, mainly for debugging. PAIR rows from the device are the main dataset.
    print("NETLOG,{},{},{},{},{:.3f},{},{},{},{},{},{},{},{},{}".format(
        RUN_ID, ENV_LABEL, seq, DISTANCE_CM, FREQ_MHZ, SPREADING_FACTOR,
        BANDWIDTH_HZ // 1000, "4/{}".format(CODING_RATE), TX_POWER_DBM,
        t_ms, rssi, snr, payload_len, ok
    ))

def main():
    print("NETWORK: paired RSSI probe responder")
    print("CONFIG: run_id={} env={} distance_cm={} freq_mhz={} sf={} bw={} cr=4/{} tx_power={}".format(
        RUN_ID, ENV_LABEL, DISTANCE_CM, FREQ_MHZ, SPREADING_FACTOR,
        BANDWIDTH_HZ, CODING_RATE, TX_POWER_DBM
    ))
    print("NETLOG_HEADER,marker,run_id,env,seq,distance_cm,freq_mhz,sf,bw_khz,cr,tx_power_dbm,t_ms,rssi_network,snr_network,payload_len,ok")

    lora = configure_lora()
    time.sleep_ms(1000)

    while True:
        rx, rssi_net, snr_net = lora.recv(timeout_ms=0)  # wait forever
        t_ms = time.ticks_ms()

        if rx is None:
            continue

        try:
            text = rx.decode()
            kv = parse_kvs(text)
        except Exception:
            print_netlog("", t_ms, rssi_net, snr_net, 0, 0)
            continue

        if kv.get("ptype") != "req":
            print("NETWORK: ignored frame:", text)
            continue

        seq = kv.get("seq", "")
        print_netlog(seq, t_ms, rssi_net, snr_net, len(rx), 1)

        time.sleep_ms(REPLY_DELAY_MS)

        resp = "ptype=resp,seq={},run_id={},net_rssi={},net_snr={},net_t={}".format(
            seq, RUN_ID, rssi_net, snr_net, t_ms
        )
        ok = lora.send(resp.encode(), timeout_ms=1500)
        if not ok:
            print("NETWORK: reply timeout seq={}".format(seq))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("NETWORK: stopped")
