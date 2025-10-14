# LoRa receiver for ESP32 + SX1276 (MicroPython) that decrypts the 'message' field
from lora_min import SX1276
import time
import ucryptolib
import ubinascii

# === RADIO CONFIG (must match sender) ===
FREQ_MHZ = 915.0
SPREADING_FACTOR = 7

# === CRYPTO CONFIG (same key as sender!) ===
AES_KEY = b"16-byte-secret!!"  # 16/24/32 bytes for AES-128/192/256

# --------- Helpers ---------
def pkcs7_unpad(b):
    if not b:
        raise ValueError("Empty plaintext after decrypt")
    padlen = b[-1]
    if padlen < 1 or padlen > 16:
        raise ValueError("Bad padding length")
    # Check all pad bytes
    if b[-padlen:] != bytes([padlen]) * padlen:
        raise ValueError("Bad PKCS#7 padding")
    return b[:-padlen]

def parse_envelope(text):
    """
    Parse 'iv=...,msg=...,counter=...,t=...' into dict.
    Returns dict with keys: iv (bytes), ct (bytes), counter (int), t (int).
    """
    parts = text.split(",")
    kv = {}
    for p in parts:
        if "=" not in p:
            # tolerate stray spaces/commas
            continue
        k, v = p.split("=", 1)
        kv[k.strip()] = v.strip()

    # Required fields
    if "iv" not in kv or "msg" not in kv:
        raise ValueError("Missing iv/msg in payload")

    # Convert hex -> bytes
    try:
        iv = ubinascii.unhexlify(kv["iv"])
        ct = ubinascii.unhexlify(kv["msg"])
    except Exception as e:
        raise ValueError("Hex decode failed: {}".format(e))

    # Optional diagnostics
    try:
        counter = int(kv.get("counter", "-1"))
    except:
        counter = -1
    try:
        t = int(kv.get("t", "-1"))
    except:
        t = -1

    return {"iv": iv, "ct": ct, "counter": counter, "t": t}

def decrypt_message(iv, ct):
    cipher = ucryptolib.aes(AES_KEY, 2, iv)  # 2 == CBC mode
    pt_padded = cipher.decrypt(ct)
    pt = pkcs7_unpad(pt_padded)
    return pt.decode("utf-8")

# --------- Main ---------
def main():
    print("LoRa receiver starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_spreading_factor(SPREADING_FACTOR)

    while True:
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        if payload is None:
            print("RX error/CRC")
            continue

        # Try to decode and decrypt
        try:
            text = payload.decode("utf-8")
        except UnicodeError:
            # If not utf-8, show raw and continue
            print("RX (non-UTF8):", payload, "| RSSI:", rssi, "dBm | SNR:", snr, "dB")
            continue

        try:
            env = parse_envelope(text)
            msg_clear = decrypt_message(env["iv"], env["ct"])
            print(
                "RX OK | msg='{}' | counter={} | t={} | RSSI={} dBm | SNR={} dB".format(
                    msg_clear, env["counter"], env["t"], rssi, snr
                )
            )
        except Exception as e:
            # If parsing/decryption failed, still show what we got for debugging
            print("RX PARSE/DECRYPT ERROR:", e)
            print("RAW:", text, "| RSSI:", rssi, "dBm | SNR:", snr, "dB")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")


