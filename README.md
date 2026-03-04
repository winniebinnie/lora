````markdown
# LoRa SX1276 (MicroPython) — FHSS + RSSI Handshake + Synthesized Rolling Keys

MicroPython examples for **ESP32 + SX1276** (RFM95 / Ra-02 class modules) implementing a lightweight secure communication demo with:

- **FHSS-like time-slot frequency hopping**
- **RSSI-based handshake** for wrapping/unwrapping a session key (experimental)
- **Synthesized rolling per-message keys** using **LCG + SHA-256**
- **AES-CBC encrypted data messages** using a fresh derived key per counter value

> ⚠️ **Security note (important)**
> This is a **learning / experimental prototype**.
> RSSI-derived values can have **low entropy** and should **not** be treated as strong cryptographic secrets by themselves.
> Do not use this as production security without stronger key exchange, authentication, and formal review.

---

## What this repo demonstrates

This project demonstrates a lightweight secure-ish LoRa link between two ESP32 nodes:

- **Alice (sender / initiator)**
- **Bob (receiver / responder)**

### Handshake overview

1. Alice sends `hello=1,nonce=<hex>`
2. Bob receives HELLO and measures **RSSI**
3. Bob quantizes RSSI (`q`) and derives a **wrapping key** from:
   - quantized RSSI (`q`)
   - nonce
4. Bob generates a random `SESSION_KEY`
5. Bob encrypts `SESSION_KEY || TAG_BLOCK` with AES-ECB using the wrapping key and replies with:
   - `ek=<encrypted_session_key_block>`
   - `nonce=<same nonce>`
   - `q=<Bob's quantized RSSI>`
6. Alice receives the reply and **brute-forces within an RSSI window** to unwrap the session key (to tolerate RSSI mismatch)

### Rolling per-message key overview (updated behavior)

After handshake succeeds:

- RSSI is **not used directly as each message key**
- Instead, RSSI (via `q`) + nonce is used to derive a **32-bit synthesized seed**
- A lightweight **LCG (Linear Congruential Generator)** advances per message counter
- The LCG state is mixed with `SESSION_KEY` using **SHA-256** to derive a fresh per-message AES key

This makes the design closer to:

- **RSSI-assisted session synchronization + seeding**
- **Counter-driven rolling keys (LCG + SHA-256)**

rather than “raw RSSI key per packet”.

---

## Repository files

- `lora_min.py` — Minimal SX1276 driver/wrapper used by the examples
- `lora_sender.py` — Initiator/sender (HELLO → key reply receive → encrypted data TX)
- `lora_receiver.py` — Responder/receiver (HELLO RX → key reply TX → decrypt data)
- *(optional/local)* RSSI logging scripts for CSV analysis (if used in experiments)

---

## Core mechanisms used in the code

### 1) FHSS-like slot hopping

Both nodes hop across a shared frequency table based on:

- a shared `SECRET_SEED`
- current time slot (`ticks_ms() // HOP_INTERVAL_MS`)

This is **time-slot hopping**, not full LoRaWAN FHSS.

### 2) RSSI-based wrapping key (handshake only)

Bob derives a wrapping key from:

- `q = quantized RSSI`
- `nonce`

using SHA-256 (e.g., `RSSI-KDFv1|...`) and truncates to 16 bytes.

Alice reconstructs it by brute-forcing nearby RSSI values within a configurable window:

- `RSSI_WINDOW_DB`
- `RSSI_STEP_DB`

### 3) Session key exchange (wrapped)

Bob generates a random `SESSION_KEY` and encrypts:

- `SESSION_KEY || TAG_BLOCK`

using AES-ECB with the wrapping key.

`TAG_BLOCK` is used by Alice to detect successful unwrap.

### 4) Synthesized rolling per-message key (LCG + SHA-256)

Once a session is established, both sides derive the same rolling key stream using:

- `SESSION_KEY`
- synthesized 32-bit seed from `q + nonce`
- message `counter`

Per-message key derivation (conceptually):

1. Advance LCG by `counter + 1` steps
2. Hash (`SESSION_KEY`, LCG state) with SHA-256
3. Take the first 16 bytes as the AES key

### 5) Encrypted data frames

Data messages are encrypted using:

- **AES-CBC**
- random IV
- PKCS#7 padding

Payload format (text K/V style):

- `iv=<hex>,msg=<hex>,counter=<n>,t=<ticks>,kind=data`

---

## Hardware / Wiring (ESP32 + SX1276)

Typical wiring (adjust to match your scripts):

- **MISO** → GPIO19
- **MOSI** → GPIO23
- **SCK** → GPIO18
- **CS / NSS** → GPIO5
- **RST** → GPIO17
- **DIO0** → GPIO26

✅ Sender and receiver must use the **same wiring** and **same radio parameters**.

---

## Radio configuration (must match on both boards)

Check and keep these consistent in `lora_sender.py` and `lora_receiver.py`:

- `TX_POWER`
- `SPREADING_FACTOR`
- `FREQ_TABLE_MHZ`
- `HOP_INTERVAL_MS`
- `SECRET_SEED`
- `HOP_GUARD_MS`
- `TAG_BLOCK`

If these do not match, handshake/data decryption will fail.

---

## Frequency / Region

The current scripts use a hopping table around the **920–923 MHz** range (for example, `920.6 ... 923.4 MHz`).

⚠️ Use only frequencies that are legal for your country/region and your lab environment.

Update `FREQ_TABLE_MHZ` as needed.

---

## Setup (MicroPython on ESP32)

### 1) Flash MicroPython to both ESP32 boards

Use `esptool.py` (or your preferred method).

### 2) Upload files with `mpremote`

#### Board A (Sender / Alice)

```bash
mpremote connect COM3 fs cp lora_min.py :lora_min.py
mpremote connect COM3 fs cp lora_sender.py :lora_sender.py
````

#### Board B (Receiver / Bob)

```bash
mpremote connect COM4 fs cp lora_min.py :lora_min.py
mpremote connect COM4 fs cp lora_receiver.py :lora_receiver.py
```

---

## Run

### Start receiver first (Bob)

```bash
mpremote connect COM4 run lora_receiver.py
```

### Then start sender (Alice)

```bash
mpremote connect COM3 run lora_sender.py
```

---

## Expected console flow (high level)

### Receiver (Bob)

* Receives HELLO
* Prints RSSI/SNR
* Derives wrapping key from quantized RSSI (`q`)
* Generates `SESSION_KEY`
* Prints/uses synthesized rolling seed (`seed32`)
* Sends encrypted key reply (`ek, nonce, q`)

### Sender (Alice)

* Sends HELLO with nonce
* Receives key reply
* Brute-force unwraps session key using RSSI reply ± window
* Confirms `TAG_BLOCK`
* Derives synthesized rolling seed (`seed32`)
* Derives per-message key from `SESSION_KEY + LCG state + counter`
* Sends encrypted data frames

---

## Reliability notes (FHSS timing / slotting)

If you see intermittent `RX timeout/CRC` or handshake failures:

### 1) Slot-phase mismatch

Each ESP32 starts `ticks_ms()` independently, so the hop schedule may drift or start out of phase.

**Symptoms**

* no reply
* RX timeout
* occasional success only when rebooted together

**Mitigations**

* start both boards at nearly the same time
* increase slot interval
* add a synchronization timestamp mechanism
* tune `HOP_GUARD_MS`

### 2) Slot-edge race

Transmitting near the end of a slot can cause missed frames.

**Mitigation**

* avoid sending near slot boundaries
* use a guard window (`HOP_GUARD_MS`)

### 3) SX1276 state after soft reboot

The radio may remain in an unstable state.

**Mitigation**

* hard reset radio using `RST` pin on startup

---

## Troubleshooting checklist

### If nothing is received

* Frequency/hop table mismatch
* `SECRET_SEED` mismatch
* `HOP_INTERVAL_MS` mismatch
* SF/BW/CR/sync word mismatch (driver defaults/config)
* Wrong `DIO0` pin / not connected
* No antenna / bad antenna / loose connector
* Power supply instability / ESP32 brownout
* Nonce mismatch (stale or unrelated frames)
* `TAG_BLOCK` mismatch between sender/receiver

### If handshake succeeds but data decryption fails

* Counter parsing mismatch
* Rolling seed mismatch (`q`, nonce, or seed derivation inconsistency)
* `SESSION_KEY` unwrap failure (false positive / wrong RSSI window)
* AES mode / IV / padding parsing issue

---

## Important limitations

This demo is useful for:

* studying **LoRa timing + hopping behavior**
* experimenting with **RSSI-assisted key synchronization**
* prototyping **lightweight rolling key derivation on MicroPython**

This demo is **not** a replacement for:

* authenticated encryption protocols
* replay protection frameworks
* secure key exchange protocols
* formally analyzed cryptographic systems

In production, use standard cryptographic designs and authenticated message protection.

---

## Suggested future improvements

* Add explicit **message authentication** (e.g., MAC / AEAD)
* Add replay protection using counter validation windows
* Add handshake timeout/retry state machine
* Add better time synchronization for slot hopping
* Log RSSI/SNR to CSV automatically for experiments
* Replace/augment LCG with a stronger deterministic construction (while keeping embedded constraints in mind)

---

## References / inspiration

* Semtech **SX1276** datasheet
* Original inspiration for driver usage:

  * [https://github.com/winniebinnie/SX1276](https://github.com/winniebinnie/SX1276)

