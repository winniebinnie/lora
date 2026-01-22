# chirp_experiment.py (MicroPython) - COPY/PASTE WHOLE FILE
import time

CHIRP_START_PREFIX  = b"CHIRP_START:"   # countdown in ms until start
CHIRP_BEACON_PREFIX = b"CHIRP:"         # chirp beacon prefix


# -------------------------
# Helpers
# -------------------------
def build_freq_list(start_mhz, stop_mhz, step_khz):
    step_mhz = step_khz / 1000.0
    freqs = []
    f = start_mhz
    while f <= stop_mhz + 1e-9:
        freqs.append(round(f, 6))
        f += step_mhz
    return freqs

def save_csv(path, rows, header):
    with open(path, "w") as fp:
        fp.write(header)
        for row in rows:
            fp.write(",".join(str(x) for x in row) + "\n")

def _ticks_now():
    return time.ticks_ms()

def _sleep_until(target_ms):
    while True:
        dt = time.ticks_diff(target_ms, _ticks_now())
        if dt <= 0:
            return
        time.sleep_ms(20 if dt > 20 else dt)

def _make_start_packet(remaining_ms):
    return CHIRP_START_PREFIX + str(int(remaining_ms)).encode()

def _parse_start_packet(pkt):
    if not pkt or not pkt.startswith(CHIRP_START_PREFIX):
        return None
    try:
        return int(pkt[len(CHIRP_START_PREFIX):].decode())
    except:
        return None

def _epoch_s_or_zero():
    # If RTC/NTP isn't set, MicroPython often returns 2000-based epoch or something odd.
    # We'll still log it; you can ignore if it's not meaningful.
    try:
        return int(time.time())
    except:
        return 0


# -------------------------
# TX: countdown sync + chirp (long windows)
# -------------------------
def chirp_sender_countdown_sync_and_tx(
    lora,
    base_freq_mhz,
    freqs_mhz,
    start_delay_ms=12000,
    announce_interval_ms=250,
    window_ms=800,              # longer per-frequency window
    beacon_interval_ms=80,      # send beacons repeatedly within window
    tx_timeout_ms=1500,
    print_live=True
):
    lora.set_frequency(int(base_freq_mhz * 1_000_000))
    start_at = time.ticks_add(_ticks_now(), start_delay_ms)

    # Countdown announce loop
    while True:
        remaining = time.ticks_diff(start_at, _ticks_now())
        if remaining <= 0:
            break

        pkt = _make_start_packet(remaining)
        ok = lora.send(pkt, timeout_ms=tx_timeout_ms)

        if print_live:
            print("SYNC TX: base={:.3f} MHz remaining={}ms ok={}".format(
                base_freq_mhz, remaining, ok
            ))

        time.sleep_ms(announce_interval_ms)

    if print_live:
        print("SYNC TX: start time reached, beginning chirp")

    # Chirp sweep with long windows
    for f in freqs_mhz:
        lora.set_frequency(int(f * 1_000_000))
        t_end = time.ticks_add(_ticks_now(), window_ms)

        if print_live:
            print("CHIRP TX: f={:.3f} MHz window={}ms".format(f, window_ms))

        while time.ticks_diff(t_end, _ticks_now()) > 0:
            beacon = CHIRP_BEACON_PREFIX + ("{:.6f}".format(f)).encode()
            lora.send(beacon, timeout_ms=tx_timeout_ms)
            time.sleep_ms(beacon_interval_ms)

        _sleep_until(t_end)


# -------------------------
# RX: wait for sync then scan + log time
# -------------------------
def chirp_receiver_wait_then_scan(
    lora,
    base_freq_mhz,
    freqs_mhz,
    wait_timeout_ms=0,
    settle_ms=12,
    window_ms=800,              # match TX window_ms
    listen_chunk_ms=120,
    default_rssi_dbm=-200,
    aggregator="max",           # "max" or "avg"
    save_path="rssi_scan.csv",
    print_live=True
):
    lora.set_frequency(int(base_freq_mhz * 1_000_000))
    time.sleep_ms(settle_ms)

    if print_live:
        print("SYNC RX: waiting on base {:.3f} MHz for CHIRP_START...".format(base_freq_mhz))

    t0_wait = _ticks_now()
    start_time_ms = None
    last_remaining = None

    # Wait for countdown sync packet
    while start_time_ms is None:
        pkt, rssi, snr = lora.recv(timeout_ms=300)
        remaining = _parse_start_packet(pkt)
        if remaining is not None:
            last_remaining = remaining
            start_time_ms = time.ticks_add(_ticks_now(), remaining)
            if print_live:
                print("SYNC RX: got countdown remaining={}ms (rssi={} snr={})".format(remaining, rssi, snr))
            break

        if wait_timeout_ms and time.ticks_diff(_ticks_now(), t0_wait) > wait_timeout_ms:
            if print_live:
                print("SYNC RX: timeout waiting for CHIRP_START")
            return []

    if print_live:
        print("SYNC RX: starting chirp scan in ~{}ms".format(last_remaining))

    _sleep_until(start_time_ms)

    scan_start_ticks = _ticks_now()
    if print_live:
        print("SYNC RX: starting chirp scan now (t_ms=0)")

    rows = []
    header = "idx,freq_mhz,t_ms,rssi_dbm,snr_db,epoch_s\n"

    for idx, f in enumerate(freqs_mhz):
        lora.set_frequency(int(f * 1_000_000))
        time.sleep_ms(settle_ms)

        rssis = []
        snrs  = []

        t_end = time.ticks_add(_ticks_now(), window_ms)
        while time.ticks_diff(t_end, _ticks_now()) > 0:
            remaining = time.ticks_diff(t_end, _ticks_now())
            to_ms = listen_chunk_ms if remaining > listen_chunk_ms else remaining
            pkt, rssi, snr = lora.recv(timeout_ms=to_ms)

            if pkt is not None and pkt.startswith(CHIRP_BEACON_PREFIX):
                try:
                    rssis.append(int(rssi))
                except:
                    pass
                try:
                    snrs.append(float(snr))
                except:
                    pass

        if rssis:
            rssi_out = int(sum(rssis) / len(rssis)) if aggregator == "avg" else max(rssis)
        else:
            rssi_out = default_rssi_dbm

        snr_out = (sum(snrs) / len(snrs)) if snrs else 0.0

        # Time logging
        t_ms = time.ticks_diff(_ticks_now(), scan_start_ticks)  # ms since scan start
        epoch_s = _epoch_s_or_zero()

        rows.append((idx, f, t_ms, rssi_out, snr_out, epoch_s))

        if print_live:
            print("CHIRP RX: idx={} f={:.3f} MHz t_ms={} rssi={} dBm samples={}".format(
                idx, f, t_ms, rssi_out, len(rssis)
            ))

    try:
        save_csv(save_path, rows, header=header)
        if print_live:
            print("Saved:", save_path)
    except Exception as e:
        if print_live:
            print("CSV save failed:", e)

    return rows

