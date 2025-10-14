# Simple LoRa sender for ESP32 + SX1276 (MicroPython) with encrypted message field
from lora_min import SX1276
import time
import ucryptolib
import ubinascii
from os import urandom   # MicroPython random bytes

# === RADIO CONFIG ===
FREQ_MHZ = 915.0            # Change to 868.0 in EU, 923.0 in some APAC bands, etc.
TX_POWER = 14               # dBm (2..17 with PA_BOOST normal mode)
SPREADING_FACTOR = 7        # 6..12; keep same as receiver

# === CRYPTO CONFIG (DEMO KEY; CHANGE THIS!) ===
# 16, 24, or 32 bytes for AES-128/192/256. Keep this secret and the same on receiver.
AES_KEY = b"16-byte-secret!!"  # exactly 16 bytes here

def _pkcs7_pad(b):
    padlen = 16 - (len(b) % 16)
    return b + bytes([padlen]) * padlen

def encrypt_message(plaintext: str) -> tuple:
    """
    Encrypts only the 'message' string with AES-CBC.
    Returns (iv_hex_str, ct_hex_str).
    """
    iv = urandom(16)
    cipher = ucryptolib.aes(AES_KEY, 2, iv)  # 2 == MODE_CBC
    padded = _pkcs7_pad(plaintext.encode("utf-8"))
    ct = cipher.encrypt(padded)
    iv_hex = ubinascii.hexlify(iv).decode()
    ct_hex = ubinascii.hexlify(ct).decode()
    return iv_hex, ct_hex

def main():
    print("LoRa sender starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    counter = 0
    message = "IceWin"

    while True:
        t_ms = time.ticks_ms()

        # --- Encrypt ONLY the message field ---
        iv_hex, ct_hex = encrypt_message(message)

        # Build a clear-text envelope: message is encrypted; counter & t are plaintext
        # Format is easy to parse on receiver: key=value, comma-separated
        # Example: iv=...,msg=...,counter=123,t=456789
        payload = "iv={},msg={},counter={},t={}".format(iv_hex, ct_hex, counter, t_ms)

        ok = lora.send(payload.encode("utf-8"), timeout_ms=5000)
        if ok:
            print("TX ok:", payload)
        else:
            print("TX timeout!")

        counter += 1
        time.sleep(2)  # send every 2 seconds

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")

