````markdown
# LoRa SX1276 (MicroPython) — FHSS + RSSI Handshake Demo

MicroPython examples for **ESP32 + SX1276** (RFM95 / Ra-02 class modules).

This repo focuses on:
- **Frequency hopping (FHSS-like time-slot hopping)**
- **RSSI-based handshake** to wrap/unwrap a session key (demo/experimental)
- **Per-message keys** derived from a counter (demo/experimental)

> ⚠️ Security note: RSSI-derived secrets have **low entropy** and are **not** strong cryptography by themselves.
> Treat this as a learning prototype, not production security.

---

## 📂 Files (in this repo)
- `lora_min.py` — minimal SX1276 driver/wrapper used by the examples
- `lora_sender.py` — initiator / sender (HELLO → key reply → encrypted data TX)
- `lora_receiver.py` — responder / receiver (RX HELLO → key reply → decrypt data)
- `log rssi into csv.py` — helper script to log RSSI into CSV for analysis

---

## ⚙️ Hardware / Wiring (ESP32 + SX1276)
Typical wiring (adjust to match your scripts):
- MISO → GPIO19  
- MOSI → GPIO23  
- SCK  → GPIO18  
- CS/NSS → GPIO5  
- RST  → GPIO17  
- DIO0 → GPIO26  

✅ Sender and receiver must use **the same** wiring and radio parameters.

---

## 📡 Frequency / Region
Many LoRa tutorials default to **868 MHz (EU)**, but these scripts are commonly configured for **~915 MHz** (e.g., hopping around 914–916 MHz).

**Use a legal ISM band for your country** and update the frequency / hop table in the scripts if needed.

---

## ▶️ Setup (MicroPython)
1. Flash MicroPython firmware to both ESP32 boards.
2. Upload the repo files to both boards (at minimum: `lora_min.py` and the script you will run).

Example with `mpremote`:

### Upload files to Board A (sender)
```bash
mpremote connect COM3 fs cp lora_min.py :lora_min.py
mpremote connect COM3 fs cp lora_sender.py :lora_sender.py
````

### Upload files to Board B (receiver)

```bash
mpremote connect COM4 fs cp lora_min.py :lora_min.py
mpremote connect COM4 fs cp lora_receiver.py :lora_receiver.py
```

---

## ▶️ Run

### Receiver first (Board B)

```bash
mpremote connect COM4 run lora_receiver.py
```

### Then sender (Board A)

```bash
mpremote connect COM3 run lora_sender.py
```

You should see:

* Receiver prints HELLO reception + derived `q` + sends encrypted key reply
* Sender prints key reply + brute-force unwrap success + encrypted data TX
* Receiver prints decrypted `msg=...` with `ctr=...`

---

## 🧪 Notes on Reliability (FHSS timing)

If you see intermittent `RX timeout/CRC` and sometimes need to rerun:

* **Slot-phase mismatch:** each ESP32 boot starts `ticks_ms()` at 0, so hop schedules may not align.

  * Fix: have receiver **sync to sender’s timestamp** from HELLO, or start both at the same time.
* **Slot-edge race:** sending/receiving in the last ~200–900 ms of a hop slot is flaky.

  * Fix: add a **guard window** and avoid sending near slot boundaries.
* **Radio state after soft reboot:** SX1276 can remain in a weird state.

  * Fix: toggle the **RST pin** at startup (hard reset).

---

## 🧰 Troubleshooting Checklist

If nothing is received:

* Frequency/hop table mismatch
* SF/BW/CR/sync word mismatch
* Wrong DIO0 pin or DIO0 not connected
* No antenna / bad antenna / loose connector
* Power issues (ESP32 brownout or noisy supply)

---

## 📖 References

* SX1276 Datasheet (Semtech)
* Original inspiration: [https://github.com/winniebinnie/SX1276](https://github.com/winniebinnie/SX1276)
