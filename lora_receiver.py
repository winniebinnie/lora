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
FREQ_TABLE_MHZ = [920.6, 920.8, 921.0, 921.2, 921.4, 921.6, 923.2, 923.4]
HOP_INTERVAL_MS = 10000
SECRET_SEED     = 0x1234ABCD

# Guard so we don't miss frames around slot edges
HOP_GUARD_MS = 250   # tune 100–500ms

TAG_BLOCK = b"HSK-OK-ICEWIN!!#"  # must match sender (16 bytes)

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

# ---------- Helpers ----------
def q_rssi(rssi_dbm, step=1):
    return int(round(rssi_dbm / step) * step)

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]

def aes_ecb_encrypt(key16, block16_mul):
    c = ucryptolib.aes(key16, 1)  # ECB
    return c.encrypt(block16_mul)

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
    b_ctr = struct.pack(">I", counter & 0xFFFFFFFF)
    h = uhashlib.sha256(b"MSG-KDF-v1|" + master_key + b"|" + b_ctr)
    return h.digest()[:16]



# === Synthesized rolling key (LCG + SHA-256) ===
# RSSI is only used to seed this generator (via q from Bob + nonce).
# Then each message derives a fresh key using the rolling LCG state.
LCG_A = 1103515245
LCG_C = 12345

def _lcg_advance(seed32, steps):
    s = seed32 & 0xFFFFFFFF
    for _ in range(steps):
        s = (LCG_A * s + LCG_C) & 0xFFFFFFFF
    return s

def synth_msg_key(session_key, lcg_seed32, counter):
    # counter=0 -> 1 step; counter=1 -> 2 steps; etc.
    state = _lcg_advance(lcg_seed32, counter + 1)
    h = uhashlib.sha256(b"SYNTHK-v1|" + session_key + struct.pack(">I", state))
    return h.digest()[:16]

def synth_seed32_from_q_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"LCG-SEEDv1|" + str(q).encode() + b"|" + nonce_bytes).digest()
    return struct.unpack(">I", h[:4])[0]
# ---------- Main ----------
def main():
    print("Receiver: starting (RSSI-based handshake + FHSS + per-message key)")
    print("FHSS freq table:", FREQ_TABLE_MHZ)
    print("TX_POWER={} dBm | SF={}".format(TX_POWER, SPREADING_FACTOR))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    slot0 = current_slot()
    f0 = set_freq_for_slot(lora, slot0)
    print("Initial hop freq = %.3f MHz (slot=%d)" % (f0, slot0))

    session_key = None
    lcg_seed32  = None

    while True:
        # Pin RX to current slot, and only listen until slot ends (+ guard)
        slot = current_slot()
        freq = set_freq_for_slot(lora, slot)
        timeout_ms = time_left_in_slot_ms() + HOP_GUARD_MS

        payload, rssi, snr = lora.recv(timeout_ms=timeout_ms)
        if payload is None:
            print("Bob: RX timeout/CRC on freq=%.3f MHz slot=%d" % (freq, slot))
            continue

        try:
            utf8 = payload.decode()
        except UnicodeError:
            print("Bob: RX non-utf8 frame on freq=%.3f slot=%d: %s" % (
                freq, slot, ubinascii.hexlify(payload)
            ))
            continue

        kv = parse_kvs(utf8)

        # ---- Handshake HELLO ----
        if kv.get("hello") == "1" and "nonce" in kv:
            print("[STEP 2] Bob: HELLO received on freq=%.3f slot=%d" % (freq, slot))
            print("          raw_frame='{}'".format(utf8))
            print("          RSSI_hello={} dBm | SNR={}".format(rssi, snr))

            nonce_hex = kv["nonce"]
            try:
                nonce = ubinascii.unhexlify(nonce_hex)
            except Exception:
                print("Bob: Bad nonce hex in HELLO")
                continue

            q = q_rssi(int(rssi))
            K = kdf_from_rssi_and_nonce(q, nonce)
            print("[STEP 3] Bob: derived wrapping key K from RSSI")
            print("          q={} (quantized RSSI) | nonce={}".format(q, nonce_hex))

            session_key = urandom(16)
            lcg_seed32 = synth_seed32_from_q_nonce(q, nonce)
            print("[STEP 3] Bob: generated SESSION_KEY = {}".format(
                ubinascii.hexlify(session_key)
            ))
            print("[STEP 3] Bob: synthesized rolling seed32 = 0x%08X" % (lcg_seed32,))

            # Encrypt SESSION_KEY || TAG_BLOCK with AES-ECB(K)
            pt = session_key + TAG_BLOCK
            ek = aes_ecb_encrypt(K, pt)
            ek_hex = ubinascii.hexlify(ek).decode()
            reply = "ek={},nonce={},q={}".format(ek_hex, nonce_hex, q)

            # IMPORTANT: send reply on SAME slot/freq we received HELLO on
            ok = lora.send(reply.encode(), timeout_ms=1500)
            if ok:
                print("[STEP 3] Bob: sent encrypted SESSION_KEY reply on freq=%.3f slot=%d" % (freq, slot))
                print("          ek_len={} hex chars".format(len(ek_hex)))
            else:
                print("Bob: TX key reply timeout on freq=%.3f slot=%d" % (freq, slot))

            continue

        # ---- Data frames ----
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

                if lcg_seed32 is None:
                    msg_key = derive_msg_key(session_key, ctr)  # fallback
                else:
                    msg_key = synth_msg_key(session_key, lcg_seed32, ctr)
                print("[STEP 7] Bob: per-message key derived (ctr={}): K_msg={}".format(
                    ctr, ubinascii.hexlify(msg_key).decode()
                ))

                clear = dec_msg_cbc(msg_key, kv["iv"], kv["msg"])
                print("[STEP 6] Bob: RX secure data on freq=%.3f slot=%d" % (freq, slot))
                print("          msg='{}' | ctr={} | t={} | RSSI={} | SNR={}".format(
                    clear, ctr, kv.get("t", "?"), rssi, snr
                ))
            except Exception as e:
                print("Bob: Data decrypt error:", e)
            continue

        print("Bob: RX other frame on freq=%.3f slot=%d: %s" % (freq, slot, utf8))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Receiver stopped.")
