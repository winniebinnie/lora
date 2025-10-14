# lora_receiver.py — RSSI-based dynamic key exchange responder (MicroPython)
from lora_min import SX1276
import time, ucryptolib, ubinascii, uhashlib

# --- secure random bytes ---
try:
    from os import urandom
except ImportError:
    try:
        from uos import urandom
    except ImportError:
        import machine
        def urandom(n): return bytes(machine.rng() & 0xFF for _ in range(n))

# === RADIO CONFIG ===
FREQ_MHZ = 915.0
TX_POWER = 14
SPREADING_FACTOR = 7

TAG_BLOCK = b"HSK-OK-ICEWIN!!#"  # must match sender

# ---------- Helpers ----------
def q_rssi(rssi_dbm, step=1):
    return int(round(rssi_dbm / step) * step)

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]

def aes_ecb_encrypt(key16, block16_mul):
    c = ucryptolib.aes(key16, 1)  # ECB
    return c.encrypt(block16_mul)

def pkcs7_pad(b):
    pad = 16 - (len(b) % 16)
    return b + bytes([pad])*pad

def pkcs7_unpad(b):
    pad = b[-1]
    if pad < 1 or pad > 16 or b[-pad:] != bytes([pad])*pad:
        raise ValueError("bad PKCS#7 padding")
    return b[:-pad]

def dec_msg_cbc(key16, iv_hex, ct_hex):
    iv = ubinascii.unhexlify(iv_hex); ct = ubinascii.unhexlify(ct_hex)
    c = ucryptolib.aes(key16, 2, iv)
    return pkcs7_unpad(c.decrypt(ct)).decode()

def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

# ---------- Main ----------
def main():
    print("Receiver: starting (RSSI-based handshake)")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    session_key = None

    while True:
        # Always listen
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        if payload is None:
            print("RX error/CRC")
            continue

        utf8 = None
        try:
            utf8 = payload.decode()
        except UnicodeError:
            print("RX non-utf8:", ubinascii.hexlify(payload))
            continue

        kv = parse_kvs(utf8)

        # ---- Handshake HELLO ----
        if kv.get("hello") == "1" and "nonce" in kv:
            nonce_hex = kv["nonce"]
            try:
                nonce = ubinascii.unhexlify(nonce_hex)
            except Exception:
                print("Bad nonce hex")
                continue

            # Derive wrapping key from MEASURED HELLO RSSI
            q = q_rssi(int(rssi))
            K = kdf_from_rssi_and_nonce(q, nonce)

            # Fresh session key (16B)
            session_key = urandom(16)

            # Encrypt two blocks: SESSION_KEY || TAG_BLOCK with AES-ECB(K)
            pt = session_key + TAG_BLOCK
            ek = aes_ecb_encrypt(K, pt)
            ek_hex = ubinascii.hexlify(ek).decode()

            reply = "ek={},nonce={}".format(ek_hex, nonce_hex)
            ok = lora.send(reply.encode(), timeout_ms=5000)
            if ok:
                print("TX key reply ok | q={} | RSSI_hello={} dBm".format(q, rssi))
            else:
                print("TX key reply timeout")
            # Continue listening for data frames
            continue

        # ---- Data frames (after handshake) ----
        if session_key and kv.get("kind") == "data" and "iv" in kv and "msg" in kv:
            try:
                clear = dec_msg_cbc(session_key, kv["iv"], kv["msg"])
                print("RX data | msg='{}' | ctr={} | t={} | RSSI={} SNR={}".format(
                    clear, kv.get("counter", "?"), kv.get("t", "?"), rssi, snr))
            except Exception as e:
                print("Data decrypt error:", e)
            continue

        # Unrecognized frame
        print("RX other:", utf8)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")


