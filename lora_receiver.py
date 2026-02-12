# lora_receiver.py — RSSI-based dynamic key exchange responder + FHSS (dynamic seed + epoch sync) + per-message key (MicroPython)
from lora_min import SX1276
import time, ucryptolib, ubinascii, uhashlib, struct
import bench_crypto

# run benchmarks once at startup
# bench_crypto.run_all()

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
TX_POWER = 14
SPREADING_FACTOR = 7

# === FHSS CONFIG (MUST MATCH SENDER) ===
FREQ_TABLE_MHZ = [920.6, 920.8, 921.0, 921.2, 921.4, 921.6, 923.2, 923.4]
HOP_INTERVAL_MS = 4000
HOP_GUARD_MS = 250   # tune 100–500ms

# Handshake rendezvous channel (both must match)
RENDEZVOUS_FREQ_MHZ = 923.2

TAG_BLOCK = b"HSK-OK-ICEWIN!!#"  # must match sender (16 bytes)

# ---------- FHSS (dynamic seed) ----------
def u32(b4):
    return struct.unpack(">I", b4)[0]

def derive_hop_seed(session_key16, q=None):
    # Seed changes every handshake (session_key is fresh).
    # q is optional: include it so RSSI influences the seed deterministically.
    if q is None:
        h = uhashlib.sha256(b"FHSS-SEED-v1|" + session_key16).digest()
    else:
        h = uhashlib.sha256(b"FHSS-SEED-v1|" + session_key16 + b"|" + str(q).encode()).digest()
    return u32(h[:4])

def hop_idx_for_slot(hop_seed_u32, slot):
    b = struct.pack(">II", hop_seed_u32 & 0xFFFFFFFF, slot & 0xFFFFFFFF)
    h = uhashlib.sha256(b"FHSS-HOP-v1|" + b).digest()
    return h[0] % len(FREQ_TABLE_MHZ)

def hop_freq_for_slot_seeded(hop_seed_u32, slot):
    return FREQ_TABLE_MHZ[hop_idx_for_slot(hop_seed_u32, slot)]

def set_freq_mhz(lora, f_mhz):
    lora.set_frequency(int(f_mhz * 1_000_000))
    return f_mhz

def set_freq_for_slot_seeded(lora, hop_seed_u32, slot):
    f = hop_freq_for_slot_seeded(hop_seed_u32, slot)
    return set_freq_mhz(lora, f)

# ---------- Epoch-based slot sync ----------
def slot_from_epoch(epoch_ms):
    d = time.ticks_diff(time.ticks_ms(), epoch_ms)
    if d < 0:
        return -1
    return d // HOP_INTERVAL_MS

def phase_in_epoch_slot_ms(epoch_ms):
    # how far we are into the current epoch-based slot [0..HOP_INTERVAL_MS-1]
    d = time.ticks_diff(time.ticks_ms(), epoch_ms)
    if d < 0:
        return 0
    return d % HOP_INTERVAL_MS

def time_left_in_epoch_slot_ms(epoch_ms):
    p = phase_in_epoch_slot_ms(epoch_ms)
    return HOP_INTERVAL_MS - p


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

# ---------- Main ----------
def main():
    print("Receiver: starting (RSSI-based handshake + FHSS dynamic seed (epoch synced) + per-message key)")
    print("FHSS freq table:", FREQ_TABLE_MHZ)
    print("RENDEZVOUS_FREQ_MHZ:", RENDEZVOUS_FREQ_MHZ)
    print("TX_POWER={} dBm | SF={}".format(TX_POWER, SPREADING_FACTOR))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_bandwidth(125000)
    lora.set_coding_rate(5)
    lora.set_crc(True)

    # State
    session_key = None
    hop_seed = None
    fhss_epoch_ms = None

    # Start on rendezvous for handshake
    set_freq_mhz(lora, RENDEZVOUS_FREQ_MHZ)
    print("Listening on rendezvous = %.3f MHz" % RENDEZVOUS_FREQ_MHZ)

    # --- OPTIONAL: fixed-freq RSSI experiment ---
    # from chirp_experiment import fixed_freq_receiver_log
    # fixed_freq_receiver_log(
    #     lora,
    #     freq_mhz=922.0,
    #     duration_ms=300000,
    #     save_path="rssi_922.csv",
    #     print_every=200
    # )
    # return
    # ------------------------------------------------

    while True:
        if session_key is None:
            # Handshake listen (rendezvous)
            freq = set_freq_mhz(lora, RENDEZVOUS_FREQ_MHZ)
            timeout_ms = 2000
        else:
            # FHSS listen (epoch-synced)
            slot = slot_from_epoch(fhss_epoch_ms)
            if slot < 0:
                # not time to start yet -> stay on rendezvous briefly
                freq = set_freq_mhz(lora, RENDEZVOUS_FREQ_MHZ)
                timeout_ms = 200
            else:
                freq = set_freq_for_slot_seeded(lora, hop_seed, slot)
                # Listen through remainder of slot (+ guard)
                timeout_ms = time_left_in_epoch_slot_ms(fhss_epoch_ms) + HOP_GUARD_MS

        payload, rssi, snr = lora.recv(timeout_ms=timeout_ms)
        if payload is None:
            if session_key is None:
                continue
            print("Bob: RX timeout/CRC on freq=%.3f MHz slot=%d" % (freq, max(0, slot_from_epoch(fhss_epoch_ms))))
            continue

        try:
            text = payload.decode()
        except UnicodeError:
            print("Bob: RX non-utf8 frame on freq=%.3f: %s" % (freq, ubinascii.hexlify(payload)))
            continue

        kv = parse_kvs(text)

        # ---- Handshake HELLO ----
        if kv.get("hello") == "1" and "nonce" in kv:
            print("[STEP 2] Bob: HELLO received on freq=%.3f MHz" % freq)
            print("          raw_frame='{}'".format(text))
            print("          RSSI_hello={} dBm | SNR={}".format(rssi, snr))

            nonce_hex = kv["nonce"]
            try:
                nonce = ubinascii.unhexlify(nonce_hex)
            except Exception:
                print("Bob: Bad nonce hex in HELLO")
                continue

            q = q_rssi(int(rssi))
            K = kdf_from_rssi_and_nonce(q, nonce)

            session_key = urandom(16)
            hop_seed = derive_hop_seed(session_key, q)

            # Choose a future start so both devices align
            start_in = 2000  # ms
            fhss_epoch_ms = time.ticks_add(time.ticks_ms(), start_in)

            print("[STEP 3] Bob: derived wrapping key K from RSSI")
            print("          q={} (quantized RSSI) | nonce={}".format(q, nonce_hex))
            print("[STEP 3] Bob: generated SESSION_KEY = {}".format(ubinascii.hexlify(session_key)))
            print("[STEP 3] Bob: derived HOP_SEED = 0x%08X" % hop_seed)
            print("[STEP 3] Bob: FHSS will start in {} ms".format(start_in))

            # Encrypt SESSION_KEY || TAG_BLOCK with AES-ECB(K)
            pt = session_key + TAG_BLOCK
            ek = aes_ecb_encrypt(K, pt)
            ek_hex = ubinascii.hexlify(ek).decode()

            reply = "ek={},nonce={},start_in={}".format(ek_hex, nonce_hex, start_in)

            ok = lora.send(reply.encode(), timeout_ms=1500)
            if ok:
                print("[STEP 3] Bob: sent encrypted SESSION_KEY reply on freq=%.3f MHz" % freq)
            else:
                print("Bob: TX key reply timeout on freq=%.3f MHz" % freq)
            continue

        # ---- Data frames ----
        if session_key and kv.get("kind") == "data" and "iv" in kv and "msg" in kv and "counter" in kv:
            try:
                ctr = int(kv["counter"])
                msg_key = derive_msg_key(session_key, ctr)
                clear = dec_msg_cbc(msg_key, kv["iv"], kv["msg"])

                slot = slot_from_epoch(fhss_epoch_ms)
                tx_slot = kv.get('slot', None)
                if tx_slot is not None:
                    print("[STEP 6] Bob: RX secure data on freq=%.3f MHz slot=%d (tx_slot=%s)" % (freq, slot, tx_slot))
                else:
                    print("[STEP 6] Bob: RX secure data on freq=%.3f MHz slot=%d" % (freq, slot))
                print("          msg='{}' | ctr={} | t={} | RSSI={} | SNR={}".format(
                    clear, ctr, kv.get("t", "?"), rssi, snr
                ))
            except Exception as e:
                print("Bob: Data decrypt error:", e)
            continue

        print("Bob: RX other frame on freq=%.3f MHz: %s" % (freq, text))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Receiver stopped.")
