# rssi_probe_device.py
# MicroPython script for ESP32 + SX1276.
# Role: End Device. Sends bidirectional RSSI probe requests and prints paired CSV rows.
#
# Copy to the end-device ESP32 as main.py, or run with mpremote:
#   mpremote connect COMx run rssi_probe_device.py
#
# Output lines start with "PAIR," so they are easy to filter from serial logs.

from lora import SX1276
import time

# ---------------- User experiment config ----------------
RUN_ID = "run03"
ENV_LABEL = "indoor_dynamic"       # examples: indoor_static, indoor_dynamic, outdoor_los
DISTANCE_CM = 100                 # set current distance for this run
PROBE_COUNT = 1000                 # start with 300-1000 packet pairs
PROBE_INTERVAL_MS = 250           # increase if packets are missed

FREQ_MHZ = 922.0
TX_POWER_DBM = 14
SPREADING_FACTOR = 7
BANDWIDTH_HZ = 125000
CODING_RATE = 5                   # 5 means LoRa coding rate 4/5

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

def csv_pair_line(seq, t_req_ms, t_resp_ms, net_rssi, net_snr,
                  dev_rssi, dev_snr, payload_len, ok):
    # Marker + fixed CSV order:
    # PAIR,run_id,env,seq,distance_cm,freq_mhz,sf,bw_khz,cr,tx_power_dbm,
    # t_req_ms,t_resp_ms,rssi_network,snr_network,rssi_device,snr_device,payload_len,ok
    return "PAIR,{},{},{},{},{:.3f},{},{},{},{},{},{},{},{},{},{},{},{}".format(
        RUN_ID, ENV_LABEL, seq, DISTANCE_CM, FREQ_MHZ, SPREADING_FACTOR,
        BANDWIDTH_HZ // 1000, "4/{}".format(CODING_RATE), TX_POWER_DBM,
        t_req_ms, t_resp_ms,
        net_rssi, net_snr, dev_rssi, dev_snr, payload_len, ok
    )

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

def main():
    print("DEVICE: bidirectional paired RSSI probe logger")
    print("CONFIG: run_id={} env={} distance_cm={} freq_mhz={} sf={} bw={} cr=4/{} tx_power={}".format(
        RUN_ID, ENV_LABEL, DISTANCE_CM, FREQ_MHZ, SPREADING_FACTOR,
        BANDWIDTH_HZ, CODING_RATE, TX_POWER_DBM
    ))
    print("CSV_HEADER,marker,run_id,env,seq,distance_cm,freq_mhz,sf,bw_khz,cr,tx_power_dbm,t_req_ms,t_resp_ms,rssi_network,snr_network,rssi_device,snr_device,payload_len,ok")

    lora = configure_lora()
    time.sleep_ms(1000)

    for seq in range(PROBE_COUNT):
        t_req = time.ticks_ms()
        req = "ptype=req,seq={},run_id={},t={}".format(seq, RUN_ID, t_req)
        ok_tx = lora.send(req.encode(), timeout_ms=1500)

        if not ok_tx:
            print(csv_pair_line(seq, t_req, "", "", "", "", "", len(req), 0))
            time.sleep_ms(PROBE_INTERVAL_MS)
            continue

        rx, rssi_dev, snr_dev = lora.recv(timeout_ms=2000)
        t_resp = time.ticks_ms()

        if rx is None:
            print(csv_pair_line(seq, t_req, t_resp, "", "", "", "", len(req), 0))
            time.sleep_ms(PROBE_INTERVAL_MS)
            continue

        try:
            text = rx.decode()
            kv = parse_kvs(text)
        except Exception:
            print(csv_pair_line(seq, t_req, t_resp, "", "", rssi_dev, snr_dev, len(req), 0))
            time.sleep_ms(PROBE_INTERVAL_MS)
            continue

        if kv.get("ptype") != "resp" or kv.get("seq") != str(seq):
            print("WARN: unexpected response seq={} text={}".format(seq, text))
            print(csv_pair_line(seq, t_req, t_resp, "", "", rssi_dev, snr_dev, len(req), 0))
            time.sleep_ms(PROBE_INTERVAL_MS)
            continue

        net_rssi = kv.get("net_rssi", "")
        net_snr = kv.get("net_snr", "")

        print(csv_pair_line(seq, t_req, t_resp, net_rssi, net_snr,
                            rssi_dev, snr_dev, len(req), 1))

        time.sleep_ms(PROBE_INTERVAL_MS)

    print("DEVICE: done")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("DEVICE: stopped")
