#!/usr/bin/env python3
"""Read-only structural verifier for a FastIron MUCH image.

This verifies the observable record table, bzip2 payloads, decoded lengths,
and per-record CRC32 values. It deliberately does not rebuild an image.
"""

from __future__ import annotations

import argparse
import bz2
import struct
import sys
import zlib
from pathlib import Path

MAX_DECODED_SIZE = 64 * 1024 * 1024


def be16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError(f"truncated 16-bit value at {offset:#x}")
    return int.from_bytes(data[offset : offset + 2], "big")


def be32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"truncated 32-bit value at {offset:#x}")
    return int.from_bytes(data[offset : offset + 4], "big")


def decompress_at(
    data: bytes, offset: int, input_size: int, expected_length: int
) -> tuple[bytes, int]:
    if input_size <= 0 or offset + input_size > len(data):
        raise ValueError("compressed input lies outside image")
    if expected_length > MAX_DECODED_SIZE:
        raise ValueError(f"decoded length exceeds {MAX_DECODED_SIZE:#x} byte limit")

    decoder = bz2.BZ2Decompressor()
    payload = data[offset : offset + input_size]
    decoded = bytearray()
    while True:
        pending = payload if decoder.needs_input else b""
        chunk = decoder.decompress(
            pending, max_length=expected_length - len(decoded) + 1
        )
        decoded.extend(chunk)
        if len(decoded) > expected_length:
            raise ValueError(f"payload at {offset:#x} exceeds declared decoded length")
        if decoder.eof:
            break
        if decoder.needs_input:
            raise ValueError(f"payload at {offset:#x} did not reach a bzip2 end marker")

    consumed = input_size - len(decoder.unused_data)
    return bytes(decoded), consumed


def verify(path: Path) -> None:
    image = path.read_bytes()
    if image[:4] != b"MUCH":
        raise ValueError("missing MUCH magic")

    table_offset = be32(image, 0x14)
    record_stride = be16(image, 0x1E)
    record_count = be16(image, 0x20)
    if record_stride != 0x28:
        raise ValueError(f"unexpected record stride {record_stride:#x}")
    if not 0 < record_count <= 16:
        raise ValueError(f"unsafe record count {record_count}")
    if table_offset + record_count * record_stride > len(image):
        raise ValueError("record table lies outside image")

    print(f"{path.name}: revision={be16(image, 0x04):#06x} records={record_count}")
    for index in range(record_count):
        record = table_offset + index * record_stride
        payload_offset = be32(image, record + 0x04)
        expected_length = be32(image, record + 0x10)
        input_size = be32(image, record + 0x20)
        expected_crc = be32(image, record + 0x24)
        if (
            payload_offset >= len(image)
            or image[payload_offset : payload_offset + 3] != b"BZh"
        ):
            raise ValueError(f"record {index}: no bzip2 stream at {payload_offset:#x}")
        decoded, consumed = decompress_at(
            image, payload_offset, input_size, expected_length
        )
        if consumed != input_size:
            raise ValueError(
                f"record {index}: bzip2 consumed {consumed:#x} bytes, expected {input_size:#x}"
            )
        actual_crc = zlib.crc32(decoded) & 0xFFFFFFFF
        if len(decoded) != expected_length:
            raise ValueError(
                f"record {index}: decoded length {len(decoded):#x}, expected {expected_length:#x}"
            )
        if actual_crc != expected_crc:
            raise ValueError(
                f"record {index}: CRC {actual_crc:#010x}, expected {expected_crc:#010x}"
            )
        print(
            f"  record {index}: payload={payload_offset:#x} decoded={len(decoded):#x} "
            f"bzip2-consumed={consumed:#x} record-input-size={input_size:#x} crc={actual_crc:#010x}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        verify(args.image)
    except (OSError, ValueError, struct.error) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
