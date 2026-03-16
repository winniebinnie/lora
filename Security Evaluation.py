import pandas as pd
import numpy as np
import re
import math
from math import erfc

# =========================
# Load CSV
# =========================
csv_path = "sniffer_log.csv"
df = pd.read_csv(csv_path)

# =========================
# Extract ciphertext (msg=...)
# =========================
msg_pattern = re.compile(r"msg=([0-9a-fA-F]+)")
counter_pattern = re.compile(r"counter=(\d+)")

msgs = []
counters = []

for text in df["payload_text"].astype(str):
    msg_match = msg_pattern.search(text)
    counter_match = counter_pattern.search(text)

    if msg_match:
        msgs.append(msg_match.group(1).lower())
        counters.append(int(counter_match.group(1)) if counter_match else None)

print(f"Total rows in CSV: {len(df)}")
print(f"Valid msg rows used: {len(msgs)}")
print(f"Excluded rows: {len(df) - len(msgs)}")

# =========================
# Convert hex ciphertexts to one long bitstream
# =========================
def hex_to_bits(hex_str: str) -> str:
    return bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)

bitstream = "".join(hex_to_bits(m) for m in msgs)
n = len(bitstream)

print(f"Total bits analyzed: {n}")

# =========================================================
# 1) Monobit Test
# =========================================================
ones = bitstream.count("1")
zeros = n - ones

S_n = ones - zeros
s_obs = abs(S_n) / math.sqrt(n)
p_value = erfc(s_obs / math.sqrt(2))

print("\n--- Monobit Test ---")
print(f"Ones  = {ones}")
print(f"Zeros = {zeros}")
print(f"S_n   = {S_n}")
print(f"s_obs = {s_obs:.6f}")
print(f"p     = {p_value:.6f}")

alpha = 0.01
if p_value >= alpha:
    print(f"Result: PASS at alpha = {alpha}")
else:
    print(f"Result: FAIL at alpha = {alpha}")

# =========================================================
# 2) Correlation Coefficient Test (lag-1)
# =========================================================
x = np.fromiter((1 if b == "1" else 0 for b in bitstream), dtype=np.int8)

# Adjacent-bit correlation
r = np.corrcoef(x[:-1], x[1:])[0, 1]

print("\n--- Correlation Coefficient Test (lag-1) ---")
print(f"r = {r:.12f}")

# =========================================================
# 3) Approximate SAC-like Avalanche Check
# =========================================================
# NOTE:
# This is NOT a formal SAC test.
# It only compares adjacent ciphertexts when the counter changes by 1 bit.
# Formal SAC requires controlled one-bit input changes under fixed crypto conditions.

def hamming_distance_hex(h1: str, h2: str) -> int:
    b1 = int(h1, 16)
    b2 = int(h2, 16)
    return (b1 ^ b2).bit_count()

def bit_count_of_hex(h: str) -> int:
    return len(h) * 4

pairs = []
for i in range(len(msgs) - 1):
    c1 = counters[i]
    c2 = counters[i + 1]

    if c1 is None or c2 is None:
        continue

    # Only compare consecutive counters
    if c2 - c1 == 1:
        # Check if counter changed by exactly one bit
        if ((c1 ^ c2).bit_count() == 1):
            hd = hamming_distance_hex(msgs[i], msgs[i + 1])
            total_bits = bit_count_of_hex(msgs[i])
            ratio = hd / total_bits
            pairs.append(ratio)

print("\n--- SAC-like Avalanche Check (Approximation Only) ---")
if pairs:
    print(f"Number of eligible pairs = {len(pairs)}")
    print(f"Mean avalanche ratio     = {np.mean(pairs):.6f}")
    print(f"Std. dev.                = {np.std(pairs):.6f}")
    print("Ideal target is near 0.5")
else:
    print("No suitable pairs found for approximate avalanche analysis.")