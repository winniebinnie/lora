# Thesis RSSI Probe Tools

These scripts are meant to be added to your existing ESP32 + SX1276 MicroPython repo.

## Why these scripts exist

Your current `lora_sender.py` and `lora_receiver.py` already implement an RSSI-assisted handshake.
For the master thesis, you first need cleaner experimental data:

- bidirectional paired RSSI
- packet sequence ID
- Network-side RSSI
- End-device RSSI
- SNR on both sides
- fixed LoRa parameters

The main dataset should come from `PAIR,` rows printed by `rssi_probe_device.py`.

## Files

- `rssi_probe_device.py` — End Device / Alice. Sends probe requests and prints paired CSV rows.
- `rssi_probe_network.py` — Network-side / Bob. Replies with the RSSI/SNR it measured.
- `rssi_eve_sniffer.py` — Optional passive Eve logger.
- `analyze_paired_rssi.py` — Desktop Python analysis for MWA, quantization, BDR, entropy, and key-generation rate.

## Basic workflow

1. Copy your existing `lora.py` to both ESP32 boards.
2. Copy `rssi_probe_network.py` to the Network-side ESP32.
3. Copy `rssi_probe_device.py` to the End-device ESP32.
4. Start the Network-side first.
5. Start the End-device second and save its serial output.
6. Run the offline analyzer on the captured End-device serial log.

Example:

```powershell
mpremote connect COM5 fs cp lora.py :
mpremote connect COM5 run rssi_probe_network.py

mpremote connect COM6 fs cp lora.py :
mpremote connect COM6 run rssi_probe_device.py | Tee-Object paired_device_log.txt

python analyze_paired_rssi.py paired_device_log.txt --out results
```

## Recommended first run

- frequency: 922 MHz
- SF: 7
- bandwidth: 125 kHz
- coding rate: 4/5
- TX power: 14 dBm
- distance: 100 cm
- environment: indoor_static
- packet pairs: 500

Then repeat with:

- indoor_dynamic
- outdoor_los
- distances such as 100 cm, 300 cm, 500 cm, 1000 cm
