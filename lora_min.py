# Minimal SX1276 LoRa driver for MicroPython (ESP32)
# Blocking send/receive via polling. No interrupts.
# Tested logic; adapt pins/frequency as needed.

from machine import Pin, SPI
import time
import struct

class SX1276:
    # Registers (subset)
    REG_FIFO                = 0x00
    REG_OP_MODE             = 0x01
    REG_FRF_MSB             = 0x06
    REG_FRF_MID             = 0x07
    REG_FRF_LSB             = 0x08
    REG_PA_CONFIG           = 0x09
    REG_OCP                 = 0x0B
    REG_LNA                 = 0x0C
    REG_FIFO_ADDR_PTR       = 0x0D
    REG_FIFO_TX_BASE_ADDR   = 0x0E
    REG_FIFO_RX_BASE_ADDR   = 0x0F
    REG_FIFO_RX_CURRENT_ADDR= 0x10
    REG_IRQ_FLAGS           = 0x12
    REG_RX_NB_BYTES         = 0x13
    REG_PKT_SNR_VALUE       = 0x19
    REG_PKT_RSSI_VALUE      = 0x1A
    REG_MODEM_CONFIG1       = 0x1D
    REG_MODEM_CONFIG2       = 0x1E
    REG_PREAMBLE_MSB        = 0x20
    REG_PREAMBLE_LSB        = 0x21
    REG_PAYLOAD_LENGTH      = 0x22
    REG_MODEM_CONFIG3       = 0x26
    REG_PKT_RSSI_VALUE_LF   = 0x1B  # (not used)
    REG_DIO_MAPPING1        = 0x40
    REG_VERSION             = 0x42
    REG_PA_DAC              = 0x4D

    # Modes
    MODE_LONG_RANGE_MODE    = 0x80  # LoRa
    MODE_SLEEP              = 0x00
    MODE_STDBY              = 0x01
    MODE_TX                 = 0x03
    MODE_RX_CONTINUOUS      = 0x05

    # IRQ flags
    IRQ_RX_DONE_MASK        = 0x40
    IRQ_TX_DONE_MASK        = 0x08
    IRQ_PAYLOAD_CRC_ERROR   = 0x20

    FXOSC = 32000000
    FSTEP = FXOSC / (1 << 19)

    def __init__(self, spi_id=1, sck=18, mosi=23, miso=19, cs=5, rst=17, baudrate=5_000_000):
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self._reset()
        # Enter LoRa + sleep, then standby
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_SLEEP)
        time.sleep_ms(10)
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_STDBY)

        # Check version (SX1276/77/78/79 typically 0x12)
        ver = self._read_reg(self.REG_VERSION)
        if ver != 0x12:  # Some clones report different, but 0x12 is standard
            raise AssertionError("LoRa chip not found (VERSION=0x%02X)" % ver)

        # Basic radio defaults (BW125, CR4/5, Explicit header, CRC on, SF7)
        # ModemConfig1: [BW|CR|ImplicitHeader]
        #   BW=125kHz -> 0x70, CR=4/5 -> 0x02, Explicit(0)
        self._write_reg(self.REG_MODEM_CONFIG1, 0x72)  # 0b0111_0010
        # ModemConfig2: [SF|TxCont|RxPayloadCrcOn|SymbTimeoutHi]
        #   SF7 -> 0x70, CRC on -> 0x04
        self._write_reg(self.REG_MODEM_CONFIG2, 0x74)  # 0b0111_0100
        # ModemConfig3: LowDataRateOptimize(0), AgcAutoOn(1)
        self._write_reg(self.REG_MODEM_CONFIG3, 0x04)

        # Preamble 8 symbols
        self._write_reg(self.REG_PREAMBLE_MSB, 0x00)
        self._write_reg(self.REG_PREAMBLE_LSB, 0x08)

        # FIFO base addresses
        self._write_reg(self.REG_FIFO_TX_BASE_ADDR, 0x00)
        self._write_reg(self.REG_FIFO_RX_BASE_ADDR, 0x00)

        # PA config: PA_BOOST on, power will be set via set_tx_power()
        self._write_reg(self.REG_PA_CONFIG, 0x8F)  # placeholder
        self._write_reg(self.REG_OCP, 0x20 | 0x13)  # OCP on, 100mA
        self._write_reg(self.REG_LNA, 0x23)  # LNA boost

        # Clear IRQs
        self._write_reg(self.REG_IRQ_FLAGS, 0xFF)

    # --- Low-level SPI ---
    def _reset(self):
        self.rst.value(0); time.sleep_ms(10)
        self.rst.value(1); time.sleep_ms(10)

    def _write_buf(self, addr, buf):
        self.cs.value(0)
        self.spi.write(bytearray([addr | 0x80]) + buf)
        self.cs.value(1)

    def _read_buf(self, addr, length):
        self.cs.value(0)
        self.spi.write(bytearray([addr & 0x7F]))
        data = self.spi.read(length)
        self.cs.value(1)
        return data

    def _write_reg(self, addr, val):
        self._write_buf(addr, bytearray([val & 0xFF]))

    def _read_reg(self, addr):
        return self._read_buf(addr, 1)[0]

    # --- Radio helpers ---
    def set_frequency(self, freq_hz):
        frf = int(freq_hz / self.FSTEP)
        self._write_reg(self.REG_FRF_MSB, (frf >> 16) & 0xFF)
        self._write_reg(self.REG_FRF_MID, (frf >> 8) & 0xFF)
        self._write_reg(self.REG_FRF_LSB, frf & 0xFF)

    def set_tx_power(self, level_dbm=14):
        # Use PA_BOOST path (typical on SX1276 modules)
        # level 2..17 dBm with PA_DAC=0x84; level 5..20 dBm with PA_DAC=0x87 (use carefully)
        level = max(2, min(17, level_dbm))
        self._write_reg(self.REG_PA_CONFIG, 0x80 | (level - 2))  # PA_BOOST + power
        # Ensure PA_DAC normal (0x84). If you need 20 dBm, set to 0x87 and raise level.
        self._write_reg(self.REG_PA_DAC, 0x84)

    def set_spreading_factor(self, sf=7):
        sf = max(6, min(12, sf))
        mc2 = self._read_reg(self.REG_MODEM_CONFIG2)
        mc2 = (mc2 & 0x0F) | ((sf << 4) & 0xF0)
        # CRC on (bit2=1), explicit header
        mc2 = (mc2 | 0x04)
        self._write_reg(self.REG_MODEM_CONFIG2, mc2)
        # LowDataRateOptimize recommended if SF11/12 with BW125
        mc3 = self._read_reg(self.REG_MODEM_CONFIG3)
        if sf >= 11:
            mc3 |= 0x08
        else:
            mc3 &= ~0x08
        self._write_reg(self.REG_MODEM_CONFIG3, mc3)

    def standby(self):
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_STDBY)

    def sleep(self):
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_SLEEP)

    # --- TX / RX ---
    def send(self, data: bytes, timeout_ms=5000):
        """Blocking send. Returns True if TX done, False on timeout."""
        self.standby()
        # Clear IRQs
        self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
        # Set FIFO ptr
        tx_base = self._read_reg(self.REG_FIFO_TX_BASE_ADDR)
        self._write_reg(self.REG_FIFO_ADDR_PTR, tx_base)
        # Load FIFO
        self._write_buf(self.REG_FIFO, data)
        # Payload length (explicit header will include it, but safe to set)
        self._write_reg(self.REG_PAYLOAD_LENGTH, len(data))
        # Go TX
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_TX)

        t0 = time.ticks_ms()
        while True:
            irq = self._read_reg(self.REG_IRQ_FLAGS)
            if irq & self.IRQ_TX_DONE_MASK:
                self._write_reg(self.REG_IRQ_FLAGS, self.IRQ_TX_DONE_MASK)  # clear
                self.standby()
                return True
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                self.standby()
                return False

    def rx_continuous(self):
        """Enter RX_CONTINUOUS and keep it there (for fast polling reads)."""
        # Clear IRQs
        self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
        # Set RX base and ptr
        rx_base = self._read_reg(self.REG_FIFO_RX_BASE_ADDR)
        self._write_reg(self.REG_FIFO_ADDR_PTR, rx_base)
        # Continuous RX
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_RX_CONTINUOUS)

    def recv_keep_rx(self, timeout_ms=0):
        """Like recv(), but assumes we are already in RX_CONTINUOUS and
        does NOT switch to standby after a packet. Returns (payload, rssi_dbm, snr_db)
        or (None, None, None) on timeout/CRC error.
        """
        t0 = time.ticks_ms()
        while True:
            irq = self._read_reg(self.REG_IRQ_FLAGS)

            if irq & self.IRQ_RX_DONE_MASK:
                # CRC error
                if irq & self.IRQ_PAYLOAD_CRC_ERROR:
                    self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
                    return (None, None, None)

                fifo_addr = self._read_reg(self.REG_FIFO_RX_CURRENT_ADDR)
                self._write_reg(self.REG_FIFO_ADDR_PTR, fifo_addr)
                nbytes = self._read_reg(self.REG_RX_NB_BYTES)
                payload = self._read_buf(self.REG_FIFO, nbytes)

                pkt_snr = self._read_reg(self.REG_PKT_SNR_VALUE)
                if pkt_snr > 127:
                    pkt_snr -= 256
                snr_db = pkt_snr / 4.0

                pkt_rssi = self._read_reg(self.REG_PKT_RSSI_VALUE)
                rssi_dbm = -157 + pkt_rssi

                # Clear IRQs, BUT stay in RX_CONTINUOUS
                self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
                return (payload, rssi_dbm, snr_db)

            if timeout_ms and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return (None, None, None)


    def recv(self, timeout_ms=0):
        """Blocking receive. timeout_ms=0 means wait forever.
        Returns (payload_bytes, rssi_dbm, snr_db) or (None, None, None) on timeout/CRC error."""
        # Clear IRQs
        self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
        # Set RX base and ptr
        rx_base = self._read_reg(self.REG_FIFO_RX_BASE_ADDR)
        self._write_reg(self.REG_FIFO_ADDR_PTR, rx_base)
        # Continuous RX
        self._write_reg(self.REG_OP_MODE, self.MODE_LONG_RANGE_MODE | self.MODE_RX_CONTINUOUS)

        t0 = time.ticks_ms()
        while True:
            irq = self._read_reg(self.REG_IRQ_FLAGS)
            if irq & self.IRQ_RX_DONE_MASK:
                # Check CRC
                if irq & self.IRQ_PAYLOAD_CRC_ERROR:
                    self._write_reg(self.REG_IRQ_FLAGS, 0xFF)  # clear all and continue
                    # CRC error -> treat as no packet
                    self.standby()
                    return (None, None, None)

                # Where is the packet?
                fifo_addr = self._read_reg(self.REG_FIFO_RX_CURRENT_ADDR)
                self._write_reg(self.REG_FIFO_ADDR_PTR, fifo_addr)
                nbytes = self._read_reg(self.REG_RX_NB_BYTES)
                payload = self._read_buf(self.REG_FIFO, nbytes)

                # RSSI / SNR
                pkt_snr = self._read_reg(self.REG_PKT_SNR_VALUE)
                # signed value: two's complement, /4 dB
                if pkt_snr > 127:
                    pkt_snr -= 256
                snr_db = pkt_snr / 4.0

                pkt_rssi = self._read_reg(self.REG_PKT_RSSI_VALUE)
                # RSSI in dBm depends on freq band; for HF (>= 779 MHz), formula ~ -157 + pkt_rssi
                rssi_dbm = -157 + pkt_rssi
                # Clear IRQs & go standby so next call is clean
                self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
                self.standby()
                return (payload, rssi_dbm, snr_db)

            if timeout_ms and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                self.standby()
                return (None, None, None)
    
    # BW/CR/CRC helpers for CSS

    def set_bandwidth(self, bw_hz=125000):
        # REG_MODEM_CONFIG1 bits 7:4
        # 125k=0x70, 250k=0x80, 500k=0x90 (SX1276 common set)
        bw_map = {
            125000: 0x70,
            250000: 0x80,
            500000: 0x90,
        }
        if bw_hz not in bw_map:
            raise ValueError("Unsupported BW: %s (use 125000/250000/500000)" % bw_hz)

        mc1 = self._read_reg(self.REG_MODEM_CONFIG1)
        mc1 = (mc1 & 0x0F) | bw_map[bw_hz]   # keep low nibble, set BW
        self._write_reg(self.REG_MODEM_CONFIG1, mc1)

        # Update LowDataRateOptimize based on Tsym > 16ms rule-of-thumb
        self._update_ldro()

    def set_coding_rate(self, cr=5):
        # LoRa CR is 4/5..4/8, encode into REG_MODEM_CONFIG1 bits 3:1
        # CR=5 -> 0x02, 6 -> 0x04, 7 -> 0x06, 8 -> 0x08
        cr_map = {5: 0x02, 6: 0x04, 7: 0x06, 8: 0x08}
        if cr not in cr_map:
            raise ValueError("Unsupported CR: %s (use 5..8 meaning 4/5..4/8)" % cr)

        mc1 = self._read_reg(self.REG_MODEM_CONFIG1)
        mc1 = (mc1 & 0xF1) | cr_map[cr]      # keep BW + header bit, set CR bits
        self._write_reg(self.REG_MODEM_CONFIG1, mc1)

    def set_crc(self, enable=True):
        mc2 = self._read_reg(self.REG_MODEM_CONFIG2)
        if enable:
            mc2 |= 0x04  # RxPayloadCrcOn
        else:
            mc2 &= ~0x04
        self._write_reg(self.REG_MODEM_CONFIG2, mc2)

    def _get_bw_hz(self):
        mc1 = self._read_reg(self.REG_MODEM_CONFIG1)
        bw_nibble = mc1 & 0xF0
        if bw_nibble == 0x70: return 125000
        if bw_nibble == 0x80: return 250000
        if bw_nibble == 0x90: return 500000
        return 125000  # fallback

    def _get_sf(self):
        mc2 = self._read_reg(self.REG_MODEM_CONFIG2)
        return (mc2 >> 4) & 0x0F

    def _update_ldro(self):
        # Enable LowDataRateOptimize if Tsym > ~16ms
        bw = self._get_bw_hz()
        sf = self._get_sf()
        tsym_ms = ( (1 << sf) * 1000 ) / bw

        mc3 = self._read_reg(self.REG_MODEM_CONFIG3)
        if tsym_ms > 16:
            mc3 |= 0x08
        else:
            mc3 &= ~0x08
        self._write_reg(self.REG_MODEM_CONFIG3, mc3)
