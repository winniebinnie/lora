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
# TX: countdown sync + chirp
# -------------------------
def chirp_sender_countdown_sync_and_tx(
    lora,
    base_freq_mhz,
    freqs_mhz,
    start_delay_ms=3000,
    announce_interval_ms=150,
    window_ms=200,
    beacon_interval_ms=25,
    inter_sweep_gap_ms=800,
    num_sweeps=5,
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

    # ABSOLUTE schedule (must match RX)
    nfreq = len(freqs_mhz)
    sweep_period_ms = (nfreq * window_ms) + inter_sweep_gap_ms
    tx_offset_ms = 30  # small guard so RX is listening when TX starts slot

    # Anchor sweep0 to the synced start_at
    global_start = start_at

    for sweep in range(num_sweeps):
        sweep_start = time.ticks_add(global_start, sweep * sweep_period_ms)

        if print_live:
            print("=== SWEEP {}/{} ===".format(sweep + 1, num_sweeps))

        for idx, f in enumerate(freqs_mhz):
            slot_start = time.ticks_add(sweep_start, idx * window_ms)
            slot_end   = time.ticks_add(slot_start, window_ms)

            _sleep_until(slot_start)

            lora.set_frequency(int(f * 1_000_000))

            # wait slightly into the slot before first TX
            _sleep_until(time.ticks_add(slot_start, tx_offset_ms))

            while time.ticks_diff(slot_end, _ticks_now()) > 0:
                # include sweep id to verify alignment (optional but helpful)
                beacon = CHIRP_BEACON_PREFIX + ("%d,{:.6f}".format(f) % sweep).encode()
                lora.send(beacon, timeout_ms=tx_timeout_ms)
                time.sleep_ms(beacon_interval_ms)

            _sleep_until(slot_end)

        # stay aligned to sweep_period boundary (don’t just sleep a fixed gap)
        _sleep_until(time.ticks_add(sweep_start, sweep_period_ms))


# -------------------------
# RX: wait for sync then scan + log time
# -------------------------
def chirp_receiver_wait_then_scan(
    lora,
    base_freq_mhz,
    freqs_mhz,
    wait_timeout_ms=0,
    settle_ms=5,
    window_ms=200,
    listen_chunk_ms=120,
    default_rssi_dbm=-200,
    aggregator="avg",
    num_sweeps=5,
    inter_sweep_gap_ms=800,
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

    if print_live:
        print("SYNC RX: starting chirp scan now (t_ms=0)")

    rows = []
    header = "sweep,idx,freq_mhz,t_ms,rssi_dbm,snr_db,epoch_s\n"

    rx_pretune_ms = 40

    nfreq = len(freqs_mhz)
    sweep_period_ms = (nfreq * window_ms) + inter_sweep_gap_ms

    # Anchor to the same absolute origin as TX (the synced start_time_ms)
    global_start = start_time_ms

    for sweep in range(num_sweeps):
        sweep_start = time.ticks_add(global_start, sweep * sweep_period_ms)

        if print_live:
            print("=== SWEEP {}/{} ===".format(sweep + 1, num_sweeps))

        for idx, f in enumerate(freqs_mhz):
            slot_start = time.ticks_add(sweep_start, idx * window_ms)
            slot_end   = time.ticks_add(slot_start, window_ms)

            tune_at = time.ticks_add(slot_start, -rx_pretune_ms)
            _sleep_until(tune_at)

            lora.set_frequency(int(f * 1_000_000))
            time.sleep_ms(settle_ms)

            lora.rx_continuous()
            _sleep_until(slot_start)

            rssis = []
            snrs  = []

            while time.ticks_diff(slot_end, _ticks_now()) > 0:
                remaining = time.ticks_diff(slot_end, _ticks_now())
                to_ms = listen_chunk_ms if remaining > listen_chunk_ms else remaining

                pkt, rssi, snr = lora.recv_keep_rx(timeout_ms=to_ms)

                if pkt is not None and pkt.startswith(CHIRP_BEACON_PREFIX):
                    # optional debug: verify sweep id is what we expect
                    # expected format: b"CHIRP:<sweep>,<freq>"
                    try:
                        body = pkt[len(CHIRP_BEACON_PREFIX):].decode()
                        sw_str, _freq_str = body.split(",", 1)
                        if int(sw_str) != sweep:
                            # wrong sweep => ignore (keeps logs clean)
                            continue
                    except:
                        pass

                    try: rssis.append(float(rssi))
                    except: pass
                    try: snrs.append(float(snr))
                    except: pass

            lora.standby()

            if rssis:
                rssi_out = (sum(rssis) / len(rssis)) if aggregator == "avg" else max(rssis)
            else:
                rssi_out = float(default_rssi_dbm)

            snr_out = (sum(snrs) / len(snrs)) if snrs else 0.0
            t_ms = time.ticks_diff(_ticks_now(), sweep_start)
            epoch_s = _epoch_s_or_zero()

            rows.append((sweep, idx, f, t_ms, rssi_out, snr_out, epoch_s))

            if print_live:
                print("CHIRP RX: sweep={} idx={} f={:.3f} MHz t_ms={} rssi={} dBm samples={}".format(
                    sweep, idx, f, t_ms, rssi_out, len(rssis)
                ))

        # keep aligned to the sweep boundary
        _sleep_until(time.ticks_add(sweep_start, sweep_period_ms))

    try:
        save_csv(save_path, rows, header=header)
        if print_live:
            print("Saved:", save_path)
    except Exception as e:
        if print_live:
            print("CSV save failed:", e)

    return rows

# -------------------------
# Fixed-frequency RSSI logging (time series)
# -------------------------

def fixed_freq_sender_tx(
    lora,
    freq_mhz,
    duration_ms=300000,
    beacon_interval_ms=100,
    tx_timeout_ms=1500,
    prefix=b"FIX:",
    print_every=200,
):
    """
    Transmit short beacons repeatedly at one fixed frequency.
    duration_ms=300000 => 5 minutes
    """
    lora.set_frequency(int(freq_mhz * 1_000_000))
    t0 = _ticks_now()
    t_end = time.ticks_add(t0, duration_ms)

    i = 0
    while time.ticks_diff(t_end, _ticks_now()) > 0:
        # Keep payload short to reduce airtime
        pkt = prefix + ("%d" % i).encode()
        ok = lora.send(pkt, timeout_ms=tx_timeout_ms)

        if print_every and (i % print_every == 0):
            print("FIX TX: f={:.3f} MHz i={} ok={}".format(freq_mhz, i, ok))

        i += 1
        time.sleep_ms(beacon_interval_ms)


def fixed_freq_receiver_log(
    lora,
    freq_mhz,
    duration_ms=300000,
    listen_chunk_ms=200,
    settle_ms=5,
    save_path="rssi_920.csv",
    prefix=b"FIX:",
    print_every=200,
    flush_every=50,
):
    """
    Receive continuously at one fixed frequency and log RSSI/SNR per packet.
    STREAMS directly to CSV (no large RAM usage).
    CSV columns: t_ms,rssi_dbm,snr_db,epoch_s
    """
    import gc

    lora.set_frequency(int(freq_mhz * 1_000_000))
    time.sleep_ms(settle_ms)
    lora.rx_continuous()

    t0 = _ticks_now()
    t_end = time.ticks_add(t0, duration_ms)

    n = 0
    try:
        f = open(save_path, "w")
        f.write("t_ms,rssi_dbm,snr_db,epoch_s\n")

        while time.ticks_diff(t_end, _ticks_now()) > 0:
            pkt, rssi, snr = lora.recv_keep_rx(timeout_ms=listen_chunk_ms)
            if pkt is None:
                continue
            if prefix and (not pkt.startswith(prefix)):
                continue

            t_ms = time.ticks_diff(_ticks_now(), t0)
            epoch_s = _epoch_s_or_zero()

            # Write CSV line with minimal allocations
            f.write(str(t_ms))
            f.write(",")
            f.write(str(rssi))
            f.write(",")
            f.write(str(snr))
            f.write(",")
            f.write(str(epoch_s))
            f.write("\n")

            if print_every and (n % print_every == 0):
                print("FIX RX: t_ms={} rssi={} snr={}".format(t_ms, rssi, snr))

            if flush_every and (n % flush_every == 0):
                f.flush()
                gc.collect()

            n += 1

        f.flush()
        f.close()
        print("Saved:", save_path, "rows:", n)

    finally:
        try:
            lora.standby()
        except:
            pass

    return n