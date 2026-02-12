# lora_sender.py — RSSI-based dynamic key exchange + FHSS (dynamic seed + epoch sync) + per-message key (MicroPython, ESP32 + SX1276)
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

# === RADIO CONFIG ===
TX_POWER = 14
SPREADING_FACTOR = 7

# === FHSS CONFIG (MUST MATCH RECEIVER) ===
FREQ_TABLE_MHZ = [920.6, 920.8, 921.0, 921.2, 921.4, 921.6, 923.2, 923.4]
HOP_INTERVAL_MS = 4000
HOP_GUARD_MS = 900  # extra guard for slot-edge tolerance
TX_TUNE_SETTLE_MS = 25  # allow SX127x PLL settle after hopping
# Handshake rendezvous channel (both must match)
RENDEZVOUS_FREQ_MHZ = 923.2

# === RSSI / BRUTEFORCE TUNING ===
RSSI_WINDOW_DB = 8
RSSI_STEP_DB   = 1
TAG_BLOCK      = b"HSK-OK-ICEWIN!!#"  # must match RX (16 bytes)

# ---------- FHSS (dynamic seed) ----------
def u32(b4):
    return struct.unpack(">I", b4)[0]

def derive_hop_seed(session_key16, q=None):
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
    d = time.ticks_diff(time.ticks_ms(), epoch_ms)
    if d < 0:
        return 0
    return d % HOP_INTERVAL_MS

def time_left_in_epoch_slot_ms(epoch_ms):
    p = phase_in_epoch_slot_ms(epoch_ms)
    return HOP_INTERVAL_MS - p


# ---------- Crypto helpers ----------
def q_rssi(rssi_dbm, step=1):
    return int(round(rssi_dbm / step) * step)

def kdf_from_rssi_and_nonce(q, nonce_bytes):
    h = uhashlib.sha256(b"RSSI-KDFv1|" + str(q).encode() + b"|" + nonce_bytes)
    return h.digest()[:16]

# --- TX slot-center alignment (improves reliability near slot edges) ---
TX_CENTER_MS = HOP_INTERVAL_MS // 2
TX_CENTER_TOL_MS = 500   # only transmit when within ±500ms of slot center


def wait_until_slot_center(epoch_ms):
    """Block until we're near the center of the current epoch-based slot.

    This avoids transmitting near hop boundaries where RX may already have hopped.
    """
    while True:
        slot = slot_from_epoch(epoch_ms)
        if slot < 0:
            time.sleep_ms(25)
            continue
        phase = phase_in_epoch_slot_ms(epoch_ms)
        # If we're already near center, go now
        if abs(phase - TX_CENTER_MS) <= TX_CENTER_TOL_MS:
            return slot
        # Otherwise sleep until center (this slot if still ahead, else next slot)
        if phase < TX_CENTER_MS:
            time.sleep_ms(TX_CENTER_MS - phase)
        else:
            time.sleep_ms((HOP_INTERVAL_MS - phase) + TX_CENTER_MS)



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
    print("Sender: starting (RSSI-based handshake + FHSS dynamic seed (epoch synced) + per-message key)")
    print("FHSS freq table:", FREQ_TABLE_MHZ)
    print("RENDEZVOUS_FREQ_MHZ:", RENDEZVOUS_FREQ_MHZ)
    print("TX_POWER={} dBm | SF={}".format(TX_POWER, SPREADING_FACTOR))

    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_bandwidth(125000)
    lora.set_coding_rate(5)
    lora.set_crc(True)

    session_key = None
    hop_seed = None
    fhss_epoch_ms = None
    counter = 0
    message = "HELLLLLLLOOOOOOOO"

    # Start on rendezvous freq for handshake
    set_freq_mhz(lora, RENDEZVOUS_FREQ_MHZ)
    print("Rendezvous = %.3f MHz" % RENDEZVOUS_FREQ_MHZ)

    # --- OPTIONAL: fixed-freq RSSI experiment ---
    # from chirp_experiment import fixed_freq_sender_tx
    # fixed_freq_sender_tx(
    #     lora,
    #     freq_mhz=922.0,
    #     duration_ms=300000,
    #     beacon_interval_ms=100,
    #     print_every=200
    # )
    # return
    # ------------------------------------------------

    while True:
        # --- Handshake ---
        if session_key is None:
            nonce = urandom(8)
            nonce_hex = ubinascii.hexlify(nonce).decode()
            hello = "hello=1,nonce={}".format(nonce_hex)

            freq = set_freq_mhz(lora, RENDEZVOUS_FREQ_MHZ)

            ok = lora.send(hello.encode(), timeout_ms=1500)
            if ok:
                print("[STEP 1] Alice: sent HELLO on %.3f MHz" % freq)
                print("          nonce={}".format(nonce_hex))
            else:
                print("Alice: TX HELLO timeout on %.3f MHz" % freq)
                time.sleep_ms(200)
                continue

            rx, rssi, snr = lora.recv(timeout_ms=2000)
            if rx is None:
                print("Alice: No key reply; retrying handshake (freq=%.3f MHz)" % freq)
                time.sleep_ms(200)
                continue

            print("[STEP 4] Alice: got key reply frame")
            print("          RSSI_reply=-{} dBm | SNR={} | freq={:.3f} MHz".format(
                abs(int(rssi)), snr, freq
            ))

            try:
                text = rx.decode()
                kv = parse_kvs(text)
                print("Alice: raw key reply =", text)

                if "ek" not in kv or "nonce" not in kv or "start_in" not in kv:
                    print("Alice: Unexpected reply, missing ek/nonce/start_in")
                    time.sleep_ms(200)
                    continue

                if kv["nonce"] != nonce_hex:
                    print("Alice: Nonce mismatch (possible replay/other convo)")
                    print("        expected={} got={}".format(nonce_hex, kv["nonce"]))
                    continue

                start_in = int(kv["start_in"])
                fhss_epoch_ms = time.ticks_add(time.ticks_ms(), start_in)

                session_key, q_found = unwrap_session_key_bruteforce(
                    kv["ek"], kv["nonce"], rssi_reply_dbm=int(rssi)
                )
                if session_key:
                    hop_seed = derive_hop_seed(session_key, q_found)
                    print("[STEP 5] Alice: handshake OK")
                    print("          q_found={} | RSSI_reply={} dBm".format(q_found, rssi))
                    print("          SESSION_KEY = {}".format(ubinascii.hexlify(session_key)))
                    print("          HOP_SEED = 0x%08X" % hop_seed)
                    print("          FHSS will start in {} ms".format(start_in))
                else:
                    print("Alice: Handshake FAILED (window={} dB)".format(RSSI_WINDOW_DB))
                    time.sleep_ms(200)
                    continue

            except Exception as e:
                print("Alice: Key reply parse/decrypt error:", e)
                time.sleep_ms(200)
                continue

        # Wait until FHSS epoch + align to slot center (edge-safe)
        slot = wait_until_slot_center(fhss_epoch_ms)

        # --- Secure data ---
        msg_key = derive_msg_key(session_key, counter)
        iv_hex, ct_hex = enc_msg_cbc(msg_key, message)
        t_ms = time.ticks_ms()
        payload = "iv={},msg={},counter={},t={},kind=data,slot={}".format(iv_hex, ct_hex, counter, t_ms, slot)

        freq = set_freq_for_slot_seeded(lora, hop_seed, slot)
        time.sleep_ms(TX_TUNE_SETTLE_MS)

        ok = lora.send(payload.encode(), timeout_ms=1500)
        if ok:
            print("[STEP 6] Alice: TX secure data ok (ctr={} t={} freq={:.3f} slot={})".format(
                counter, t_ms, freq, slot
            ))
        else:
            print("Alice: TX data timeout on freq={:.3f} slot={}".format(freq, slot))

        counter += 1

        # Optional repeat in SAME slot (still near center), improves capture probability
        time.sleep_ms(300)
        if slot_from_epoch(fhss_epoch_ms) == slot:
            msg_key = derive_msg_key(session_key, counter)
            iv_hex, ct_hex = enc_msg_cbc(msg_key, message)
            t_ms = time.ticks_ms()
            payload = "iv={},msg={},counter={},t={},kind=data,slot={}".format(iv_hex, ct_hex, counter, t_ms, slot)
            ok = lora.send(payload.encode(), timeout_ms=1500)
            if ok:
                print("[STEP 6] Alice: TX secure data ok (ctr={} t={} freq={:.3f} slot={})".format(
                    counter, t_ms, freq, slot
                ))
            counter += 1

        # sleep a bit; next loop will re-align to the next slot center
        time.sleep_ms(50)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Sender stopped.")
