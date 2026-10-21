#!/usr/bin/env python3
"""Read settings from the fixed PiKVM screen descriptor without opening its TTY."""

import ctypes
import json
import os
from pathlib import Path
import platform
import stat
import sys
import termios

PID = 78187
SERIAL_FD = 4
EXPECTED_STARTTIME = 5441045
KERNEL = "6.12.105-1-rpi"
MACHINE = "aarch64"
DEVICE = "/dev/ttyUSB0"
ADAPTER = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AK08H7HL-if00-port0"
# Linux v6.12 scripts/syscall.tbl: common syscall 438 is pidfd_getfd.
# https://raw.githubusercontent.com/torvalds/linux/v6.12/scripts/syscall.tbl
PIDFD_GETFD = 438
EXE = "/usr/bin/screen-5.0.2"
PROC = Path(f"/proc/{PID}")


class Rejected(Exception):
    """The fixed process or descriptor could not be verified."""


def snapshot():
    if (PROC / "comm").read_text() != "screen\n":
        raise Rejected("unexpected serial owner")
    if os.readlink(PROC / "exe") != EXE:
        raise Rejected("unexpected serial owner executable")
    raw = (PROC / "stat").read_text()
    left = raw.find("(")
    right = raw.rfind(")")
    if (
        left < 0
        or right <= left
        or raw[:left].strip() != str(PID)
        or raw[left + 1 : right] != "screen"
    ):
        raise Rejected("unexpected process stat identity")
    fields = raw[right + 1 :].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise Rejected("missing process start time")
    starttime = int(fields[19])
    if starttime != EXPECTED_STARTTIME:
        raise Rejected("unexpected process start time")
    if os.path.realpath(ADAPTER) != DEVICE:
        raise Rejected("unexpected FTDI adapter target")
    descriptor = PROC / "fd" / str(SERIAL_FD)
    if os.readlink(descriptor) != DEVICE:
        raise Rejected("unexpected owner descriptor target")
    device = os.stat(DEVICE)
    adapter = os.stat(ADAPTER)
    owner = os.stat(descriptor)
    identity = (device.st_rdev, device.st_dev, device.st_ino)
    if not all(stat.S_ISCHR(info.st_mode) for info in (device, adapter, owner)):
        raise Rejected("serial descriptor is not a character device")
    if any(
        (info.st_rdev, info.st_dev, info.st_ino) != identity
        for info in (adapter, owner)
    ):
        raise Rejected("serial descriptor device identity mismatch")
    return starttime, *identity


def get_existing_fd(pidfd):
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        getfd = libc.syscall
    except (OSError, AttributeError) as error:
        raise Rejected("libc syscall unavailable") from error
    getfd.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    getfd.restype = ctypes.c_long
    result = getfd(
        ctypes.c_long(PIDFD_GETFD),
        ctypes.c_int(pidfd),
        ctypes.c_int(SERIAL_FD),
        ctypes.c_uint(0),
    )
    if result < 0:
        raise Rejected(f"pidfd_getfd failed errno {ctypes.get_errno()}")
    return result


def baud(speed):
    for name in dir(termios):
        if (
            name.startswith("B")
            and name[1:].isdigit()
            and getattr(termios, name) == speed
        ):
            return int(name[1:])
    raise Rejected("unsupported serial baud encoding")


def decode(attrs):
    if len(attrs) != 7:
        raise Rejected("unexpected termios shape")
    iflag, _, cflag, _, ispeed, ospeed, _ = attrs
    sizes = {
        termios.CS5: 5,
        termios.CS6: 6,
        termios.CS7: 7,
        termios.CS8: 8,
    }
    size = cflag & termios.CSIZE
    if size not in sizes or not hasattr(termios, "CRTSCTS"):
        raise Rejected("unsupported serial flags")
    if hasattr(termios, "CMSPAR") and cflag & termios.CMSPAR:
        raise Rejected("unsupported mark or space parity")
    return {
        "input_baud": baud(ispeed),
        "output_baud": baud(ospeed),
        "data_bits": sizes[size],
        "parity": "none"
        if not cflag & termios.PARENB
        else "odd"
        if cflag & termios.PARODD
        else "even",
        "stop_bits": 2 if cflag & termios.CSTOPB else 1,
        "CRTSCTS": bool(cflag & termios.CRTSCTS),
        "IXON": bool(iflag & termios.IXON),
        "IXOFF": bool(iflag & termios.IXOFF),
        "CLOCAL": bool(cflag & termios.CLOCAL),
        "HUPCL": bool(cflag & termios.HUPCL),
    }


def inspect():
    if (
        platform.machine() != MACHINE
        or platform.release() != KERNEL
        or ctypes.sizeof(ctypes.c_long) != 8
    ):
        raise Rejected("unexpected PiKVM kernel context")
    if not hasattr(os, "pidfd_open"):
        raise Rejected("pidfd_open unavailable")
    before = snapshot()
    pidfd = None
    duplicate = None
    try:
        pidfd = os.pidfd_open(PID, 0)
        # Catch PID reuse between the initial metadata read and obtaining pidfd.
        if snapshot() != before:
            raise Rejected("serial owner changed before duplication")
        duplicate = get_existing_fd(pidfd)
        info = os.fstat(duplicate)
        if (
            not stat.S_ISCHR(info.st_mode)
            or (info.st_rdev, info.st_dev, info.st_ino) != before[1:]
        ):
            raise Rejected("duplicated serial descriptor identity mismatch")
        settings = decode(termios.tcgetattr(duplicate))
        after = snapshot()
        if after != before:
            raise Rejected("serial owner or descriptor changed")
        return {
            "pid": PID,
            "owner_executable": EXE,
            "owner_fd": SERIAL_FD,
            "adapter": ADAPTER,
            "device": DEVICE,
            "kernel": KERNEL,
            "machine": MACHINE,
            "owner_starttime_before": before[0],
            "owner_starttime_after": after[0],
            "settings": settings,
            "settings_observed": True,
            "serial_control_verified": False,
            "independent_rescue_verified": False,
            "restore_verified": False,
        }
    finally:
        try:
            if duplicate is not None:
                os.close(duplicate)
        finally:
            if pidfd is not None:
                os.close(pidfd)


def main():
    if len(sys.argv) != 1:
        print("Serial descriptor inspection rejects arguments.", file=sys.stderr)
        return 2
    try:
        result = inspect()
    except (Rejected, OSError, ValueError, termios.error):
        print("Serial descriptor settings could not be verified.", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
