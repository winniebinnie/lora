# Simple LoRa sender for ESP32 + SX1276 (MicroPython)
from lora_min import SX1276
import time

# Predefined vocabulary used for the Word Handshake session key
WORD_LIST = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
    "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
    "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
    "victor", "whiskey", "xray", "yankee", "zulu"
]

# === CONFIG ===
FREQ_MHZ = 915.0   # Change to 868.0 in EU, 923.0 in some APAC bands, etc.
TX_POWER = 14      # dBm (2..17 with PA_BOOST normal mode)
SPREADING_FACTOR = 7  # 6..12; keep same as receiver

SESSION_KEY = None


def _derive_key_from_rssi(rssi):
    return abs(int(rssi)) % 256


def _xor_cipher(data: bytes, key: int) -> bytes:
    return bytes([b ^ key for b in data])


def _perform_word_handshake(lora):
    global SESSION_KEY
    print("[Sender] Starting Word Handshake.")
    if lora.send(b"HANDSHAKE_INIT", timeout_ms=5000):
        print("[Sender] Step 1: Sent HANDSHAKE_INIT message.")
    else:
        print("[Sender] Step 1: Failed to send HANDSHAKE_INIT (timeout).")
        return

    print("[Sender] Step 2: Waiting for ciphertext response...")
    payload, rssi, snr = lora.recv(timeout_ms=5000)
    if payload is None:
        print("[Sender] Step 2: Did not receive ciphertext (timeout/CRC error).")
        return

    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        print("[Sender] Step 2: Received non-text payload:", payload)
        return

    print("[Sender] Received response: {} | RSSI: {} dBm | SNR: {} dB".format(text, rssi, snr))
    if not text.startswith("HANDSHAKE_CIPHERTEXT:"):
        print("[Sender] Response did not contain expected ciphertext marker.")
        return

    hex_cipher = text.split(":", 1)[1]
    try:
        ciphertext = bytes.fromhex(hex_cipher)
    except ValueError:
        print("[Sender] Invalid ciphertext encoding.")
        return

    print("[Sender] Step 3: Attempting to brute-force RSSI derived key...")
    for guessed_rssi in range(-120, -19):
        key = _derive_key_from_rssi(guessed_rssi)
        plaintext_bytes = _xor_cipher(ciphertext, key)
        try:
            candidate = plaintext_bytes.decode("utf-8")
        except UnicodeError:
            candidate = None
        print("[Sender] Trying RSSI {} (key {}): {}".format(guessed_rssi, key, candidate))
        if candidate in WORD_LIST:
            SESSION_KEY = candidate
            print("[Sender] Step 4: Handshake successful. Session key established:", SESSION_KEY)
            return

    print("[Sender] Step 4: Failed to determine session key from ciphertext.")


def main():
    print("LoRa sender starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_tx_power(TX_POWER)
    lora.set_spreading_factor(SPREADING_FACTOR)

    _perform_word_handshake(lora)

    counter = 0
    while True:
        if SESSION_KEY:
            msg = "hello {}, t={}, key={}".format(counter, time.ticks_ms(), SESSION_KEY)
        else:
            msg = "hello {}, t={}".format(counter, time.ticks_ms())
        ok = lora.send(msg.encode("utf-8"), timeout_ms=5000)
        if ok:
            print("TX ok:", msg)
        else:
            print("TX timeout!")
        counter += 1
        time.sleep(2)  # send every 2 seconds


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
