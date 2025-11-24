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

# ---------- Main ----------
def main():
    print("Receiver: starting (RSSI-based handshake)")
    print("Radio config: FREQ={} MHz | TX_POWER={} dBm | SF={}".format(
        FREQ_MHZ, TX_POWER, SPREADING_FACTOR
    ))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_tx_power(TX_POWER)

    session_key = None

    while True:
        # Always listen
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        if payload is None:
            print("RX error/CRC")
            continue

        try:
            utf8 = payload.decode()
        except UnicodeError:
            print("RX non-utf8 frame:", ubinascii.hexlify(payload))
            continue

        kv = parse_kvs(utf8)

        # ---- Handshake HELLO ----
        if kv.get("hello") == "1" and "nonce" in kv:
            # STEP 2 – Bob receives HELLO and measures RSSI
            print("[STEP 2] Bob: HELLO received")
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
            ok = lora.send(reply.encode(), timeout_ms=5000)
            if ok:
                print("[STEP 3] Bob: sent encrypted SESSION_KEY reply")
                print("          ek_len={} hex chars".format(len(ek_hex)))
            else:
                print("Bob: TX key reply timeout")
            # Continue listening for data frames
            continue

        # ---- Data frames (after handshake) ----
        if session_key and kv.get("kind") == "data" and "iv" in kv and "msg" in kv:
            try:
                clear = dec_msg_cbc(session_key, kv["iv"], kv["msg"])
                # STEP 6 – Bob uses established secure session
                print("[STEP 6] Bob: RX secure data")
                print("          msg='{}' | ctr={} | t={} | RSSI={} | SNR={}".format(
                    clear, kv.get("counter", "?"), kv.get("t", "?"), rssi, snr
                ))
            except Exception as e:
                print("Bob: Data decrypt error:", e)
            continue

        # Unrecognized frame
        print("Bob: RX other frame:", utf8)

        if text == "HANDSHAKE_INIT":
            print("[Receiver] Handshake initiated by sender.")
            selected_word = random.choice(WORD_LIST)
            print("[Receiver] Step 1: Generated random word:", selected_word)
            key = _derive_key_from_rssi(rssi)
            print("[Receiver] Step 2: Derived XOR key from RSSI ({} -> {}).".format(rssi, key))
            ciphertext = _xor_cipher(selected_word.encode("utf-8"), key)
            print("[Receiver] Step 3: Encrypted word to ciphertext:", ciphertext.hex())
            response = "HANDSHAKE_CIPHERTEXT:" + ciphertext.hex()
            if lora.send(response.encode("utf-8"), timeout_ms=5000):
                print("[Receiver] Step 4: Sent ciphertext back to sender.")
            else:
                print("[Receiver] Step 4: Failed to send ciphertext (timeout).")
            print("[Receiver] Waiting for next message...")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Receiver stopped.")

