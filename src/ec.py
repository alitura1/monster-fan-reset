#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ec.py - Monster Abra A5 (Tongfang/Uniwill) icin guvenli EC erisim katmani.

Katmanlar:
  1) PawnIO + LpcACPIEC.bin  -> sadece port 0x62/0x66'ya raw in/out byte
  2) ACPI EC protokolu (RD_EC=0x80 / WR_EC=0x81) -> 8-bit EC RAM (0x00-0xFF)
  3) Uniwill "direct" 16-bit EC RAM erisimi (0x8a-0x8e register protokolu)
     -> TUXEDO tuxedo-drivers uniwill_wmi.c uw_ec_*_addr_direct birebir portu

Tum bekleyislerde timeout var: handshake takilirsa exception (guvenli basarisizlik).
EC islemleri sirasinda 'Global\\Access_EC' mutex'i (varsa) tutulur.

KAYNAK: github.com/tuxedocomputers/tuxedo-drivers (GPL-2.0) src/uniwill_wmi.c,
        src/uniwill_keyboard.h, src/tuxedo_io/tuxedo_io.c
"""

import ctypes
from ctypes import wintypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PAWNIO_DLL = r"C:\Program Files\PawnIO\PawnIOLib.dll"
MODULE_BIN = os.path.join(HERE, "LpcACPIEC.bin")

# --- ACPI EC portlari / komutlari ---
EC_DATA = 0x62          # data port
EC_SC   = 0x66          # status/command port
RD_EC   = 0x80
WR_EC   = 0x81
EC_OBF  = 0x01          # output buffer full (EC -> host hazir)
EC_IBF  = 0x02          # input buffer full (host -> EC bekliyor)

# --- Uniwill "direct" 16-bit EC RAM register'lari (8-bit EC uzayinda) ---
UW_LDAT  = 0x8a         # adres dusuk bayt
UW_HDAT  = 0x8b         # adres yuksek bayt
UW_FLAGS = 0x8c
UW_CMDL  = 0x8d         # data dusuk bayt
UW_CMDH  = 0x8e         # data yuksek bayt
UW_BIT_RFLG = 0        # read flag
UW_BIT_WFLG = 1        # write flag
UW_BIT_BFLG = 2        # busy flag
UW_BIT_DRDY = 7        # data ready

# Timeout ayarlari
EC_HANDSHAKE_TIMEOUT = 0.100   # 100 ms (IBF/OBF bekleme)
UW_DRDY_TIMEOUT      = 0.500   # 500 ms (Uniwill DRDY bekleme)
POLL_SLEEP           = 0.0002  # 0.2 ms poll araligi


class ECError(Exception):
    pass


class PawnIO:
    """PawnIOLib.dll sarmalayicisi + LpcACPIEC modulu."""

    def __init__(self):
        if not os.path.exists(MODULE_BIN):
            raise ECError(f"Modul bulunamadi: {MODULE_BIN}")
        try:
            self.dll = ctypes.WinDLL(PAWNIO_DLL)
        except OSError as e:
            raise ECError(f"PawnIOLib.dll yuklenemedi: {e}")

        self.dll.pawnio_open.argtypes = [ctypes.POINTER(wintypes.HANDLE)]
        self.dll.pawnio_open.restype = ctypes.c_long
        self.dll.pawnio_load.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.c_size_t]
        self.dll.pawnio_load.restype = ctypes.c_long
        self.dll.pawnio_execute.argtypes = [
            wintypes.HANDLE, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.dll.pawnio_execute.restype = ctypes.c_long
        self.dll.pawnio_close.argtypes = [wintypes.HANDLE]
        self.dll.pawnio_close.restype = ctypes.c_long

        self.handle = wintypes.HANDLE()
        hr = self.dll.pawnio_open(ctypes.byref(self.handle))
        if hr != 0:
            raise ECError(f"pawnio_open basarisiz: 0x{hr & 0xFFFFFFFF:08X} "
                          f"(PawnIO surucusu calisiyor mu? Yonetici misin?)")

        with open(MODULE_BIN, "rb") as f:
            blob = f.read()
        hr = self.dll.pawnio_load(self.handle, blob, len(blob))
        if hr != 0:
            self.close()
            raise ECError(f"pawnio_load basarisiz: 0x{hr & 0xFFFFFFFF:08X} "
                          f"(modul imzasi/surum uyumsuz olabilir)")

    def execute(self, name: str, in_vals, out_count: int):
        # DEFINE_IOCTL_SIZED in/out boyutlari TAM eslesmeli (yoksa E_INVALIDARG 0x80070057)
        in_arr = (ctypes.c_uint64 * max(len(in_vals), 1))(*in_vals)
        out_arr = (ctypes.c_uint64 * max(out_count, 1))()
        ret_size = ctypes.c_size_t(0)
        hr = self.dll.pawnio_execute(
            self.handle, name.encode("ascii"),
            in_arr, len(in_vals),
            out_arr, out_count, ctypes.byref(ret_size))
        if hr != 0:
            raise ECError(f"pawnio_execute('{name}') basarisiz: 0x{hr & 0xFFFFFFFF:08X}")
        return [out_arr[i] for i in range(ret_size.value)]

    def close(self):
        if getattr(self, "handle", None):
            try:
                self.dll.pawnio_close(self.handle)
            except Exception:
                pass
            self.handle = wintypes.HANDLE()


class EC:
    """Yuksek seviye EC erisimi (8-bit ACPI + Uniwill 16-bit direct)."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.pio = PawnIO()
        self._mutex = self._open_ec_mutex()

    # ---- dusuk seviye port erisimi ----
    def _inb(self, port: int) -> int:
        return self.pio.execute("ioctl_pio_read", [port & 0xFFFF], 1)[0] & 0xFF

    def _outb(self, port: int, value: int) -> None:
        self.pio.execute("ioctl_pio_write", [port & 0xFFFF, value & 0xFF], 0)

    # ---- EC mutex (best-effort) ----
    def _open_ec_mutex(self):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        MUTEX_ALL_ACCESS = 0x1F0001
        for name in (r"Global\Access_EC", "Access_EC"):
            h = k32.OpenMutexW(MUTEX_ALL_ACCESS, False, name)
            if h:
                if self.verbose:
                    print(f"[ec] Access_EC mutex acildi: {name}")
                self._k32 = k32
                return h
        self._k32 = k32
        if self.verbose:
            print("[ec] Access_EC mutex bulunamadi (best-effort, devam).")
        return None

    def _lock(self):
        if self._mutex:
            self._k32.WaitForSingleObject(self._mutex, 1000)  # 1s

    def _unlock(self):
        if self._mutex:
            self._k32.ReleaseMutex(self._mutex)

    # ---- ACPI EC 8-bit protokolu ----
    def _wait(self, mask: int, want_set: bool, timeout: float):
        deadline = time.perf_counter() + timeout
        while True:
            st = self._inb(EC_SC)
            bit = (st & mask) != 0
            if bit == want_set:
                return
            if time.perf_counter() > deadline:
                raise ECError(f"EC handshake timeout (SC=0x{st:02X}, mask=0x{mask:02X}, "
                              f"want_set={want_set})")
            time.sleep(POLL_SLEEP)

    def _drain_obf(self):
        # OS/OEM servisinden kalan bayatlamis OBF verisini temizle
        for _ in range(32):
            if self._inb(EC_SC) & EC_OBF:
                self._inb(EC_DATA)
            else:
                return

    def _ec_read8_once(self, offset: int) -> int:
        self._drain_obf()
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)
        self._outb(EC_SC, RD_EC)
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)
        self._outb(EC_DATA, offset)
        self._wait(EC_OBF, True, EC_HANDSHAKE_TIMEOUT)
        return self._inb(EC_DATA)

    def _ec_write8_once(self, offset: int, value: int) -> None:
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)
        self._outb(EC_SC, WR_EC)
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)
        self._outb(EC_DATA, offset)
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)
        self._outb(EC_DATA, value)
        self._wait(EC_IBF, False, EC_HANDSHAKE_TIMEOUT)

    # retry'li, kilitli 8-bit erisim (OS/OEM yarisina karsi)
    def ec_read8(self, offset: int, retries: int = 8) -> int:
        last = None
        for _ in range(retries):
            self._lock()
            try:
                return self._ec_read8_once(offset)
            except ECError as e:
                last = e
            finally:
                self._unlock()
            time.sleep(0.001)
        raise last

    def ec_write8(self, offset: int, value: int, retries: int = 8) -> None:
        last = None
        for _ in range(retries):
            self._lock()
            try:
                self._ec_write8_once(offset, value)
                return
            except ECError as e:
                last = e
            finally:
                self._unlock()
            time.sleep(0.001)
        raise last

    # ---- Uniwill 16-bit "direct" EC RAM erisimi ----
    # (uniwill_wmi.c: uw_ec_read_addr_direct / uw_ec_write_addr_direct)
    def _uw_wait_drdy(self):
        # Kernel surucusu 15ms araliklarla yokluyor; EC'yi dovmemek icin yumusak yokla
        deadline = time.perf_counter() + UW_DRDY_TIMEOUT
        while True:
            tmp = self._ec_read8_once(UW_FLAGS)
            if tmp & (1 << UW_BIT_DRDY):
                return
            if time.perf_counter() > deadline:
                raise ECError("Uniwill DRDY timeout")
            time.sleep(0.008)

    def _uw_clear_flags(self):
        try:
            self._ec_write8_once(UW_FLAGS, 0x00)
        except ECError:
            pass

    def uw_read_ram(self, addr16: int, retries: int = 6) -> int:
        lo = addr16 & 0xFF
        hi = (addr16 >> 8) & 0xFF
        last = None
        for _ in range(retries):
            self._lock()
            try:
                flags = self._ec_read8_once(UW_FLAGS)
                flags |= (1 << UW_BIT_BFLG)
                self._ec_write8_once(UW_FLAGS, flags)
                self._ec_write8_once(UW_LDAT, lo)
                self._ec_write8_once(UW_HDAT, hi)
                flags &= ~(1 << UW_BIT_DRDY)
                flags |= (1 << UW_BIT_RFLG)
                self._ec_write8_once(UW_FLAGS, flags)
                self._uw_wait_drdy()
                data_low = self._ec_read8_once(UW_CMDL)
                self._uw_clear_flags()
                return data_low & 0xFF
            except ECError as e:
                last = e
                self._uw_clear_flags()
            finally:
                self._unlock()
            time.sleep(0.002)
        raise last

    def uw_write_ram(self, addr16: int, data: int, retries: int = 6) -> None:
        lo = addr16 & 0xFF
        hi = (addr16 >> 8) & 0xFF
        last = None
        for _ in range(retries):
            self._lock()
            try:
                flags = self._ec_read8_once(UW_FLAGS)
                flags |= (1 << UW_BIT_BFLG)
                self._ec_write8_once(UW_FLAGS, flags)
                self._ec_write8_once(UW_LDAT, lo)
                self._ec_write8_once(UW_HDAT, hi)
                self._ec_write8_once(UW_CMDL, data & 0xFF)
                self._ec_write8_once(UW_CMDH, 0x00)
                flags &= ~(1 << UW_BIT_DRDY)
                flags |= (1 << UW_BIT_WFLG)
                self._ec_write8_once(UW_FLAGS, flags)
                self._uw_wait_drdy()
                self._uw_clear_flags()
                return
            except ECError as e:
                last = e
                self._uw_clear_flags()
            finally:
                self._unlock()
            time.sleep(0.002)
        raise last

    def uw_write_ram_verify(self, addr16: int, data: int, retries: int = 3) -> None:
        last = None
        for _ in range(retries):
            self.uw_write_ram(addr16, data)
            last = self.uw_read_ram(addr16)
            if last == (data & 0xFF):
                return
            time.sleep(0.005)
        raise ECError(f"uw_write_ram_verify basarisiz: 0x{addr16:04X} "
                      f"yazilan=0x{data:02X} okunan=0x{last:02X}")

    def close(self):
        try:
            self.pio.close()
        finally:
            if getattr(self, "_mutex", None):
                try:
                    self._k32.CloseHandle(self._mutex)
                except Exception:
                    pass


# Bilinen register adresleri (TUXEDO uniwill referansi)
REG = {
    "FAN_CTRL_STATUS": 0x078e,   # bit6 (0x40) = has_universal_ec_fan_control
    "BAREBONE_ID":     0x0740,
    "MODE_0751":       0x0751,   # bit6 (0x40) = "full fan mode"
    "MODE_0741":       0x0741,
    "CUSTOM_PROFILE":  0x0727,
    "FAN0_DUTY":       0x1804,
    "FAN1_DUTY":       0x1809,
    "FAN_TEMP_CPU":    0x043e,
    "FAN_TEMP_GPU":    0x044f,
    "CUSTOM_TBL_EN0":  0x07c5,   # bit7
    "CUSTOM_TBL_EN1":  0x07c6,   # bit2
    "CPU_TBL_SPEED":   0x0f20,
    "GPU_TBL_SPEED":   0x0f50,
}
NB02_FAN_SPEED_MAX = 0xC8


def _self_test():
    """Sadece OKUMA yapan guvenli tani. Hicbir yazma yok."""
    print("=== EC self-test (sadece okuma) ===")
    ec = EC(verbose=True)
    try:
        ver = ctypes.c_uint32(0)
        try:
            ec.pio.dll.pawnio_version.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
            ec.pio.dll.pawnio_version.restype = ctypes.c_long
            ec.pio.dll.pawnio_version(ctypes.byref(ver))
            v = ver.value
            print(f"PawnIO surum: {v>>16}.{(v>>8)&0xFF}.{v&0xFF}")
        except Exception as e:
            print(f"PawnIO surum okunamadi: {e}")

        # 8-bit EC saglik: birkac standart offset
        sc = ec._inb(EC_SC)
        print(f"EC_SC (0x66) durum = 0x{sc:02X}")

        fan_ctrl = ec.uw_read_ram(REG["FAN_CTRL_STATUS"])
        has_uw = (fan_ctrl >> 6) & 1
        print(f"0x078e FAN_CTRL_STATUS = 0x{fan_ctrl:02X}  -> has_universal_ec_fan_control={has_uw}")

        bb = ec.uw_read_ram(REG["BAREBONE_ID"])
        print(f"0x0740 BAREBONE_ID     = 0x{bb:02X}")

        rom = "".join(chr(ec.uw_read_ram(0x0770 + i)) if 32 <= ec.uw_read_ram(0x0770 + i) < 127 else "."
                      for i in range(16))
        print(f"0x0770 ROMID           = '{rom}'")

        mode = ec.uw_read_ram(REG["MODE_0751"])
        print(f"0x0751 MODE            = 0x{mode:02X}  (full_fan_mode bit6={(mode>>6)&1})")

        t_cpu = ec.uw_read_ram(REG["FAN_TEMP_CPU"])
        t_gpu = ec.uw_read_ram(REG["FAN_TEMP_GPU"])
        print(f"0x043e FAN_TEMP_CPU    = {t_cpu} C")
        print(f"0x044f FAN_TEMP_GPU    = {t_gpu} C")

        d0 = ec.uw_read_ram(REG["FAN0_DUTY"])
        d1 = ec.uw_read_ram(REG["FAN1_DUTY"])
        print(f"0x1804 FAN0_DUTY       = 0x{d0:02X} ({round(d0/NB02_FAN_SPEED_MAX*100)}%)")
        print(f"0x1809 FAN1_DUTY       = 0x{d1:02X} ({round(d1/NB02_FAN_SPEED_MAX*100)}%)")
        print("=== self-test OK ===")
    finally:
        ec.close()


class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, s):
        for st in self.streams:
            try:
                st.write(s); st.flush()
            except Exception:
                pass
    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


if __name__ == "__main__":
    logpath = os.path.join(HERE, "diag.log")
    logf = open(logpath, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, logf)
    sys.stderr = sys.stdout
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "selftest":
            _self_test()
        else:
            print("Kullanim: python ec.py selftest")
    except Exception as e:
        import traceback
        print("HATA:", e)
        traceback.print_exc()
    finally:
        logf.flush(); logf.close()
