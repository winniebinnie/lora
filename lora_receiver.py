# Simple LoRa receiver for ESP32 + SX1276 (MicroPython)
from lora_min import SX1276
import time
import random

# Predefined vocabulary used for the Word Handshake session key
WORD_LIST = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
    "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
    "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
    "victor", "whiskey", "xray", "yankee", "zulu"
]

# === CONFIG ===
FREQ_MHZ = 915.0     # Must match sender
SPREADING_FACTOR = 7 # Must match sender
TX_POWER = 14        # dBm for handshake responses


def _derive_key_from_rssi(rssi):
    """Map the RSSI reading to a single-byte XOR key."""
    return abs(int(rssi)) % 256


def _xor_cipher(data: bytes, key: int) -> bytes:
    return bytes([b ^ key for b in data])


def main():
    print("LoRa receiver starting...")
    lora = SX1276(sck=18, mosi=23, miso=19, cs=5, rst=17)
    lora.set_frequency(int(FREQ_MHZ * 1_000_000))
    lora.set_spreading_factor(SPREADING_FACTOR)
    lora.set_tx_power(TX_POWER)

    while True:
        payload, rssi, snr = lora.recv(timeout_ms=0)  # wait forever
        if payload is None:
            # CRC error or timeout (timeout=0 means shouldn't happen)
            print("RX error/CRC")
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeError:
            text = str(payload)
        print("RX:", text, "| RSSI:", rssi, "dBm | SNR:", snr, "dB")

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
        print("Stopped.")
