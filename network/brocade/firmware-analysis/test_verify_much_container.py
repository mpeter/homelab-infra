import bz2
import tempfile
import unittest
import zlib
from pathlib import Path

from verify_much_container import verify


class VerifyMuchContainerTests(unittest.TestCase):
    def make_image(
        self,
        input_size: int | None = None,
        expected_length: int | None = None,
        trailing_bytes: bytes = b"",
    ) -> bytes:
        decoded = b"firmware segment"
        payload = bz2.compress(decoded)
        table_offset = 0x60
        payload_offset = table_offset + 0x28
        image = bytearray(payload_offset + len(payload) + len(trailing_bytes))
        image[:4] = b"MUCH"
        image[0x04:0x06] = (0x07F3).to_bytes(2, "big")
        image[0x14:0x18] = table_offset.to_bytes(4, "big")
        image[0x1E:0x20] = (0x28).to_bytes(2, "big")
        image[0x20:0x22] = (1).to_bytes(2, "big")
        image[table_offset + 0x04 : table_offset + 0x08] = payload_offset.to_bytes(
            4, "big"
        )
        image[table_offset + 0x10 : table_offset + 0x14] = (
            len(decoded) if expected_length is None else expected_length
        ).to_bytes(4, "big")
        image[table_offset + 0x20 : table_offset + 0x24] = (
            len(payload) + len(trailing_bytes) if input_size is None else input_size
        ).to_bytes(4, "big")
        image[table_offset + 0x24 : table_offset + 0x28] = zlib.crc32(decoded).to_bytes(
            4, "big"
        )
        image[payload_offset:] = payload
        image[payload_offset + len(payload) :] = trailing_bytes
        return bytes(image)

    def verify_bytes(self, image: bytes) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "firmware.bin"
            path.write_bytes(image)
            verify(path)

    def test_accepts_matching_record_sizes(self) -> None:
        self.verify_bytes(self.make_image())

    def test_rejects_mismatched_compressed_input_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "compressed input|bzip2"):
            self.verify_bytes(self.make_image(input_size=1))

    def test_rejects_trailing_bytes_in_compressed_input_extent(self) -> None:
        with self.assertRaisesRegex(ValueError, "bzip2 consumed"):
            self.verify_bytes(self.make_image(trailing_bytes=b"\x00"))

    def test_rejects_output_larger_than_declared_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds declared decoded length"):
            self.verify_bytes(self.make_image(expected_length=1))


if __name__ == "__main__":
    unittest.main()
