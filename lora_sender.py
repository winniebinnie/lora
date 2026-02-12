# lora_sender.py — RSSI-based dynamic key exchange + FHSS + per-message key (MicroPython, ESP32 + SX1276)
from lora_min import SX1276
import time, ucryptolib, ubinascii, uhashlib, struct

# --- secure random bytes for nonces/IVs ---
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

# === FHSS CONFIG (MUST MATCH RECEIVER) ===
FREQ_TABLE_MHZ = [920.6, 920.8, 921.0, 921.2, 921.4, 921.6, 923.2, 923.4]
HOP_INTERVAL_MS = 10000          # hop every 10 seconds
SECRET_SEED     = 0x1234ABCD     # must match RX

# Guard so we don't miss frames around slot edges
HOP_GUARD_MS = 250               # tune 100–500ms depending on your timing

# === RSSI / BRUTEFORCE TUNING ===
RSSI_WINDOW_DB = 8
RSSI_STEP_DB   = 1
TAG_BLOCK      = b"HSK-OK-ICEWIN!!#"  # must match RX (16 bytes)

def _prn_from_slot(slot):
    x = (SECRET_SEED ^ slot) & 0xFFFFFFFF
    x = (1103515245 * x + 12345) & 0x7FFFFFFF
    return x

def hop_freq_for_slot(slot):
    prn = _prn_from_slot(slot)
    idx = prn % len(FREQ_TABLE_MHZ)
    return FREQ_TABLE_MHZ[idx]

def current_slot():
    return time.ticks_ms() // HOP_INTERVAL_MS

def set_freq_for_slot(lora, slot):
    f = hop_freq_for_slot(slot)
    lora.set_frequency(int(f * 1_000_000))
    return f

def time_left_in_slot_ms():
    now = time.ticks_ms()
    elapsed = now % HOP_INTERVAL_MS
    return HOP_INTERVAL_MS - elapsed

def q_rssi(rssi_dbm, step=1):
    return int(round(rssi_dbm / step) * step)

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]

def aes_ecb_decrypt(key16, ct):
    c = ucryptolib.aes(key16, 1)  # ECB
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

def parse_kvs(text):
    kv = {}
    for part in text.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

def derive_msg_key(master_key, counter):
    b_ctr = struct.pack(">I", counter & 0xFFFFFFFF)
    h = uhashlib.sha256(b"MSG-KDF-v1|" + master_key + b"|" + b_ctr)
    return h.digest()[:16]

def unwrap_session_key_bruteforce(ek_hex, nonce_hex, rssi_reply_dbm):
    ek = ubinascii.unhexlify(ek_hex)
    nonce = ubinascii.unhexlify(nonce_hex)

    print("[STEP 4] Alice: start brute-force unwrap of SESSION_KEY")
    print("          RSSI_reply_dbm={} | window=±{} dB | step={}".format(
        rssi_reply_dbm, RSSI_WINDOW_DB, RSSI_STEP_DB
    ))

    for dq in range(-RSSI_WINDOW_DB, RSSI_WINDOW_DB + 1, RSSI_STEP_DB):
        q = q_rssi(rssi_reply_dbm + dq)
        K = kdf_from_rssi_and_nonce(q, nonce)
        try:
            pt = aes_ecb_decrypt(K, ek)  # expected 32 bytes
            if len(pt) != 32:
                continue
            sess = pt[:16]
            tag  = pt[16:32]
            if tag == TAG_BLOCK:
                print("[STEP 5] Alice: found matching TAG_BLOCK at q={}".format(q))
                return sess, q
        except Exception:
            pass

    print("[STEP 5] Alice: FAILED to find correct key in window")
    return None, None

def main():
    print("Sender: starting (RSSI-based handshake + FHSS + per-message key)")
    print("FHSS freq table:", FREQ_TABLE_MHZ)
    print("TX_POWER={} dBm | SF={}".format(TX_POWER, SPREADING_FACTOR))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    slot0 = current_slot()
    f0 = set_freq_for_slot(lora, slot0)
    print("Initial hop freq = %.3f MHz (slot=%d)" % (f0, slot0))

    session_key = None
    counter = 0
    message = "HELLLLLLLOOOOOOOO"

    while True:
        # --- Handshake ---
        if session_key is None:
            nonce = urandom(8)
            nonce_hex = ubinascii.hexlify(nonce).decode()
            hello = "hello=1,nonce={}".format(nonce_hex)

            # Pin to ONE slot for HELLO + waiting reply
            slot = current_slot()
            freq = set_freq_for_slot(lora, slot)

            ok = lora.send(hello.encode(), timeout_ms=1500)
            if ok:
                print("[STEP 1] Alice: sent HELLO on %.3f MHz slot=%d" % (freq, slot))
                print("          nonce={}".format(nonce_hex))
            else:
                print("Alice: TX HELLO timeout on %.3f MHz slot=%d" % (freq, slot))
                time.sleep_ms(200)
                continue

            # Wait only until slot ends (plus guard), still on same freq/slot
            timeout_ms = time_left_in_slot_ms() + HOP_GUARD_MS
            rx, rssi, snr = lora.recv(timeout_ms=timeout_ms)

            if rx is None:
                print("Alice: No key reply; retrying handshake (freq=%.3f slot=%d)" % (freq, slot))
                time.sleep_ms(200)
                continue

            print("[STEP 4] Alice: got key reply frame")
            print("          RSSI_reply={} dBm | SNR={} | freq={:.3f} MHz slot={}".format(
                rssi, snr, freq, slot
            ))

            try:
                text = rx.decode()
                kv = parse_kvs(text)
                print("Alice: raw key reply =", text)

                if "ek" not in kv or "nonce" not in kv:
                    print("Alice: Unexpected reply, missing ek/nonce")
                    time.sleep_ms(200)
                    continue

                if kv["nonce"] != nonce_hex:
                    print("Alice: Nonce mismatch (possible replay/other convo)")
                    print("        expected={} got={}".format(nonce_hex, kv["nonce"]))
                    continue

                session_key, q_found = unwrap_session_key_bruteforce(
                    kv["ek"], kv["nonce"], rssi_reply_dbm=int(rssi)
                )
                if session_key:
                    print("[STEP 5] Alice: handshake OK")
                    print("          q_found={} | RSSI_reply={} dBm".format(q_found, rssi))
                    print("          SESSION_KEY = {}".format(ubinascii.hexlify(session_key)))
                else:
                    print("Alice: Handshake FAILED (window={} dB)".format(RSSI_WINDOW_DB))
                    time.sleep_ms(200)
                    continue

            except Exception as e:
                print("Alice: Key reply parse/decrypt error:", e)
                time.sleep_ms(200)
                continue

        # --- Secure data ---
        msg_key = derive_msg_key(session_key, counter)
        print("[STEP 7] Alice: per-message key derived (ctr={}): K_msg={}".format(
            counter, ubinascii.hexlify(msg_key).decode()
        ))

        iv_hex, ct_hex = enc_msg_cbc(msg_key, message)
        t_ms = time.ticks_ms()
        payload = "iv={},msg={},counter={},t={},kind=data".format(
            iv_hex, ct_hex, counter, t_ms
        )

        slot = current_slot()
        freq = set_freq_for_slot(lora, slot)
        ok = lora.send(payload.encode(), timeout_ms=1500)
        if ok:
            print("[STEP 6] Alice: TX secure data ok (ctr={} t={} freq={:.3f} slot={})".format(
                counter, t_ms, freq, slot
            ))
        else:
            print("Alice: TX data timeout on freq={:.3f} slot={}".format(freq, slot))

        counter += 1
        time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Sender stopped.")

