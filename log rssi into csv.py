# lora_receiver.py — RSSI-based dynamic key exchange responder + FHSS + per-message key (MicroPython)
from lora_min import SX1276
import time, ucryptolib, ubinascii, uhashlib, struct

# --- secure random bytes ---
try:
    from os import urandom
except ImportError:
    try:
        from uos import urandom
    except ImportError:
        import machine
        def urandom(n): return bytes(machine.rng() & 0xFF for _ in range(n))


# === RADIO CONFIG (non-FHSS params) ===
TX_POWER = 14
SPREADING_FACTOR = 7

# === FHSS CONFIG (MUST MATCH SENDER) ===
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
HOP_INTERVAL_MS = 10000
SECRET_SEED     = 0x1234ABCD


def _prn_from_slot(slot):
    x = (SECRET_SEED ^ slot) & 0xFFFFFFFF
    x = (1103515245 * x + 12345) & 0x7FFFFFFF
    return x


def get_hop_frequency():
    slot = time.ticks_ms() // HOP_INTERVAL_MS
    prn  = _prn_from_slot(slot)
    idx  = prn % len(FREQ_TABLE_MHZ)
    return FREQ_TABLE_MHZ[idx], slot


def set_hop_frequency(lora):
    freq_mhz, slot = get_hop_frequency()
    lora.set_frequency(int(freq_mhz * 1_000_000))
    return freq_mhz, slot


TAG_BLOCK = b"HSK-OK-ICEWIN!!#"  # must match sender


# ---------- Helpers ----------
def q_rssi(rssi_dbm, step=1):
    # Quantize RSSI (e.g., -73.4 -> -73 for step=1)
    return int(round(rssi_dbm / step) * step)


def kdf_from_rssi_and_nonce(q, nonce_bytes):
    # K = SHA256("RSSI-KDFv1|" + str(q) + "|" + nonce), take 16 bytes
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]


def aes_ecb_encrypt(key16, block16_mul):
    c = ucryptolib.aes(key16, 1)  # ECB
    return c.encrypt(block16_mul)


def pkcs7_pad(b):
    pad = 16 - (len(b) % 16)
    return b + bytes([pad]) * pad


def pkcs7_unpad(b):
    pad = b[-1]
    if pad < 1 or pad > 16 or b[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad PKCS#7 padding")
    return b[:-pad]


def dec_msg_cbc(key16, iv_hex, ct_hex):
    iv = ubinascii.unhexlify(iv_hex)
    ct = ubinascii.unhexlify(ct_hex)
    c = ucryptolib.aes(key16, 2, iv)  # CBC
    return pkcs7_unpad(c.decrypt(ct)).decode()


def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def derive_msg_key(master_key, counter):
    """
    Derive per-message AES key from master session_key + counter.
    """
    b_ctr = struct.pack(">I", counter & 0xFFFFFFFF)
    h = uhashlib.sha256(b"MSG-KDF-v1|" + master_key + b"|" + b_ctr)
    return h.digest()[:16]


# ---------- Main ----------
def main():
    print("Receiver: starting (RSSI-based handshake + FHSS + per-message key)")
    print("FHSS freq table:", FREQ_TABLE_MHZ)
    print("TX_POWER={} dBm | SF={}".format(TX_POWER, SPREADING_FACTOR))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    freq_mhz, slot = set_hop_frequency(lora)
    print("Initial hop freq = %.3f MHz (slot=%d)" % (freq_mhz, slot))

    session_key = None

    while True:
        # hop ก่อนรับทุกครั้ง
        freq_mhz, slot = set_hop_frequency(lora)
        payload, rssi, snr = lora.recv(timeout_ms=HOP_INTERVAL_MS + 500)
        if payload is None:
            print("Bob: RX timeout/CRC on freq=%.3f MHz slot=%d" %
                  (freq_mhz, slot))
            continue

        try:
            utf8 = payload.decode()
        except UnicodeError:
            print("Bob: RX non-utf8 frame on freq=%.3f slot=%d: %s" %
                  (freq_mhz, slot, ubinascii.hexlify(payload)))
            continue

        kv = parse_kvs(utf8)

        # ---- Handshake HELLO ----
        if kv.get("hello") == "1" and "nonce" in kv:
            # STEP 2 – Bob receives HELLO and measures RSSI
            print("[STEP 2] Bob: HELLO received on freq=%.3f slot=%d" %
                  (freq_mhz, slot))
            print("          raw_frame='{}'".format(utf8))
            print("          RSSI_hello={} dBm | SNR={}".format(rssi, snr))

            nonce_hex = kv["nonce"]
            try:
                nonce = ubinascii.unhexlify(nonce_hex)
            except Exception:
                print("Bob: Bad nonce hex in HELLO")
                continue

            # Derive wrapping key from measured HELLO RSSI
            q = q_rssi(int(rssi))
            K = kdf_from_rssi_and_nonce(q, nonce)
            print("[STEP 3] Bob: derived wrapping key K from RSSI")
            print("          q={} (quantized RSSI) | nonce={}".format(q, nonce_hex))

            # Fresh session key (16B)
            session_key = urandom(16)
            print("[STEP 3] Bob: generated SESSION_KEY = {}".format(
                ubinascii.hexlify(session_key)
            ))

            # Encrypt two blocks: SESSION_KEY || TAG_BLOCK with AES-ECB(K)
            pt = session_key + TAG_BLOCK
            ek = aes_ecb_encrypt(K, pt)
            ek_hex = ubinascii.hexlify(ek).decode()

            reply = "ek={},nonce={}".format(ek_hex, nonce_hex)

            # hop ก่อนส่ง reply (ใช้ช่องตาม slot ปัจจุบัน)
            freq_mhz, slot = set_hop_frequency(lora)
            ok = lora.send(reply.encode(), timeout_ms=5000)
            if ok:
                print("[STEP 3] Bob: sent encrypted SESSION_KEY reply "
                      "on freq=%.3f slot=%d" % (freq_mhz, slot))
                print("          ek_len={} hex chars".format(len(ek_hex)))
            else:
                print("Bob: TX key reply timeout on freq=%.3f slot=%d" %
                      (freq_mhz, slot))

            continue

        # ---- Data frames (after handshake) ----
        if session_key and kv.get("kind") == "data" and "iv" in kv and "msg" in kv:
            try:
                ctr_str = kv.get("counter", None)
                if ctr_str is None:
                    print("Bob: missing counter in data frame")
                    continue

                try:
                    ctr = int(ctr_str)
                except ValueError:
                    print("Bob: bad counter format:", ctr_str)
                    continue

                # derive per-message key จาก master session_key + counter
                msg_key = derive_msg_key(session_key, ctr)
                msg_key_hex = ubinascii.hexlify(msg_key).decode()
                print("[STEP 7] Bob: per-message key derived "
                      "(ctr={}): K_msg={}".format(ctr, msg_key_hex))

                clear = dec_msg_cbc(msg_key, kv["iv"], kv["msg"])
                # STEP 6 – Bob uses established secure session
                print("[STEP 6] Bob: RX secure data on freq=%.3f slot=%d" %
                      (freq_mhz, slot))
                print("          msg='{}' | ctr={} | t={} | RSSI={} | SNR={}".format(
                    clear, ctr, kv.get("t", "?"), rssi, snr
                ))
            except Exception as e:
                print("Bob: Data decrypt error:", e)
            continue

        # Unrecognized frame
        print("Bob: RX other frame on freq=%.3f slot=%d: %s" %
              (freq_mhz, slot, utf8))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Receiver stopped.")