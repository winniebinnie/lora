import csv
import matplotlib.pyplot as plt

CSV_FILE = "lora_rx_log.csv"  # ชื่อไฟล์ csv ของคุณ

time_s = []
rssi = []

with open(CSV_FILE, newline="") as f:
    reader = csv.DictReader(f)
    t0 = None
    for row in reader:
        now_ms = int(row["now_ms"])      # เวลา ณ ตอนรับแพ็กเก็ต (ms)
        rssi_dbm = float(row["rssi_dbm"])

        if t0 is None:
            t0 = now_ms  # ใช้ค่าตัวแรกเป็นจุดเริ่ม (เวลา 0)

        # แปลงเป็นวินาที และทำให้เริ่มจาก 0
        t_rel = (now_ms - t0) / 1000.0

        time_s.append(t_rel)
        rssi.append(rssi_dbm)

# วาดกราฟ
plt.figure()
plt.plot(time_s, rssi, marker=".")
plt.xlabel("Time (s)")
plt.ylabel("RSSI (dBm)")
plt.title("LoRa RSSI vs Time")
plt.grid(True)

# เซฟเป็นรูป
plt.savefig("lora_rssi_time.png")
# หรือจะโชว์หน้าจอด้วยก็ได้
# plt.show()

print("saved: lora_rssi_time.png")
