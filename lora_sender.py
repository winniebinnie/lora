# lora_sender.py — RSSI-based dynamic key exchange (MicroPython, ESP32 + SX1276)
from lora_min import SX1276
import time, ucryptolib, ubinascii, uhashlib

# --- secure random bytes for nonces/IVs ---
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

# === RSSI / BRUTEFORCE TUNING ===
RSSI_WINDOW_DB = 8   # +/- dB around measured reply RSSI
RSSI_STEP_DB   = 1   # step in dB
TAG_BLOCK      = b"HSK-OK-ICEWIN!!#"  # 16-byte constant check block

# ---------- Helpers ----------
def q_rssi(rssi_dbm, step=1):
    # Quantize RSSI (e.g., -73.4 -> -73 for step=1)
    return int(round(rssi_dbm / step) * step)

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    # K = SHA256("RSSI-KDFv1|" + str(q) + "|" + nonce), take 16 bytes
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]

def aes_ecb_encrypt(key16, block16_mul):
    c = ucryptolib.aes(key16, 1)  # 1 == ECB
    return c.encrypt(block16_mul)

def aes_ecb_decrypt(key16, ct):
    c = ucryptolib.aes(key16, 1)
    return c.decrypt(ct)

def pkcs7_pad(b):
    pad = 16 - (len(b) % 16)
    return b + bytes([pad]) * pad

def pkcs7_unpad(b):
    pad = b[-1]
    if pad < 1 or pad > 16 or b[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad PKCS#7 padding")
    return b[:-pad]

def enc_msg_cbc(key16, msg_str):
    iv = urandom(16)
    c = ucryptolib.aes(key16, 2, iv)  # CBC
    ct = c.encrypt(pkcs7_pad(msg_str.encode()))
    return ubinascii.hexlify(iv).decode(), ubinascii.hexlify(ct).decode()

def dec_msg_cbc(key16, iv_hex, ct_hex):
    iv = ubinascii.unhexlify(iv_hex)
    ct = ubinascii.unhexlify(ct_hex)
    c = ucryptolib.aes(key16, 2, iv)
    return pkcs7_unpad(c.decrypt(ct)).decode()

def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

# Try unwrap SESSION_KEY by brute forcing q around measured RSSI of reply
def unwrap_session_key_bruteforce(ek_hex, nonce_hex, rssi_reply_dbm):
    ek = ubinascii.unhexlify(ek_hex)
    nonce = ubinascii.unhexlify(nonce_hex)

    print("[STEP 4] Alice: start brute-force unwrap of SESSION_KEY")
    print("          RSSI_reply_dbm={} | window=±{} dB | step={}".format(
        rssi_reply_dbm, RSSI_WINDOW_DB, RSSI_STEP_DB
    ))

    # We encrypted two 16B blocks: SESSION_KEY(16) || TAG(16)
    for dq in range(-RSSI_WINDOW_DB, RSSI_WINDOW_DB + 1, RSSI_STEP_DB):
        q = q_rssi(rssi_reply_dbm + dq)
        K = kdf_from_rssi_and_nonce(q, nonce)
        try:
            pt = aes_ecb_decrypt(K, ek)  # expected length 32
            if len(pt) != 32:
                continue
            sess = pt[:16]
            tag  = pt[16:32]
            if tag == TAG_BLOCK:
                print("[STEP 5] Alice: found matching TAG_BLOCK at q={}".format(q))
                return sess, q  # success
        except Exception:
            # ignore bad keys
            pass

    print("[STEP 5] Alice: FAILED to find correct key in window")
    return None, None  # failed

# ---------- Main ----------
def main():
    print("Sender: starting (RSSI-based handshake)")
    print("Radio config: FREQ={} MHz | TX_POWER={} dBm | SF={}".format(
        FREQ_MHZ, TX_POWER, SPREADING_FACTOR
    ))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    session_key = None
    counter = 0
    message = "IceWin"

    while True:
        # If no session key yet, run handshake
        if session_key is None:
            nonce = urandom(8)
            nonce_hex = ubinascii.hexlify(nonce).decode()
            hello = "hello=1,nonce={}".format(nonce_hex)

            ok = lora.send(hello.encode(), timeout_ms=5000)
            if ok:
                # STEP 1 – Alice sends HELLO
                print("[STEP 1] Alice: sent HELLO")
                print("          nonce={}".format(nonce_hex))
            else:
                print("Alice: TX HELLO timeout")
                time.sleep(1)
                continue

            # Wait for KEY reply
            rx, rssi, snr = lora.recv(timeout_ms=4000)
            if rx is None:
                print("Alice: No key reply; retrying handshake")
                time.sleep(1)
                continue

            print("[STEP 4] Alice: got key reply frame")
            print("          RSSI_reply={} dBm | SNR={}".format(rssi, snr))

            try:
                text = rx.decode()
                kv = parse_kvs(text)
                print("Alice: raw key reply =", text)

                if kv.get("hello") or "ek" not in kv or "nonce" not in kv:
                    print("Alice: Unexpected reply, missing ek/nonce or contains hello")
                    time.sleep(1)
                    continue

                if kv["nonce"] != nonce_hex:
                    print("Alice: Nonce mismatch (possible replay/other convo)")
                    print("        expected={} got={}".format(nonce_hex, kv["nonce"]))
                    continue

                # Brute-force q around measured reply RSSI
                session_key, q_found = unwrap_session_key_bruteforce(
                    kv["ek"], kv["nonce"], rssi_reply_dbm=int(rssi)
                )
                if session_key:
                    print("[STEP 5] Alice: handshake OK")
                    print("          q_found={} | RSSI_reply={} dBm".format(q_found, rssi))
                    print("          SESSION_KEY = {}".format(
                        ubinascii.hexlify(session_key)
                    ))
                else:
                    print("Alice: Handshake FAILED (window={} dB)".format(RSSI_WINDOW_DB))
                    time.sleep(1)
                    continue
            except Exception as e:
                print("Alice: Key reply parse/decrypt error:", e)
                time.sleep(1)
                continue

        # --- We have a session key: send data frames encrypting only 'message' ---
        iv_hex, ct_hex = enc_msg_cbc(session_key, message)
        t_ms = time.ticks_ms()
        payload = "iv={},msg={},counter={},t={},kind=data".format(
            iv_hex, ct_hex, counter, t_ms
        )
        ok = lora.send(payload.encode(), timeout_ms=5000)
        if ok:
            # STEP 6 – Alice uses established secure session
            print("[STEP 6] Alice: TX secure data ok")
            print("          ctr={} | t={} ms".format(counter, t_ms))
        else:
            print("Alice: TX data timeout")

        counter += 1
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Sender stopped.")

