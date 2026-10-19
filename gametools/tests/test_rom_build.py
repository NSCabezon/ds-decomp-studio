import struct
import sys
import unittest
from pathlib import Path

from ndspy import _common

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rom_build import secure_area_crc_fix


class SecureAreaChecksumTests(unittest.TestCase):
    def setUp(self):
        self.original = bytearray(0x8000)
        self.original[0x0c:0x10] = b"AL7E"
        struct.pack_into("<I", self.original, 0x20, 0x4000)
        self.original[0x4000:] = bytes(range(256)) * 64
        struct.pack_into("<H", self.original, 0x6c, 0x1234)
        self.header_crc(self.original)
        self.rebuilt = bytearray(self.original)
        struct.pack_into("<H", self.rebuilt, 0x6c, 0)
        self.header_crc(self.rebuilt)

    @staticmethod
    def header_crc(image):
        struct.pack_into("<H", image, 0x15e, _common.crc16(image[:0x15e]))

    def test_unchanged_secure_area_preserves_only_missing_metadata(self):
        self.assertTrue(secure_area_crc_fix(bytes(self.original), self.rebuilt))
        self.assertEqual(self.rebuilt, self.original)

    def test_changed_secure_area_is_never_repaired(self):
        self.rebuilt[0x4567] ^= 1
        before = bytes(self.rebuilt)
        self.assertFalse(secure_area_crc_fix(bytes(self.original), self.rebuilt))
        self.assertEqual(self.rebuilt, before)

    def test_existing_nonzero_checksum_is_not_overwritten(self):
        struct.pack_into("<H", self.rebuilt, 0x6c, 0x5678)
        self.header_crc(self.rebuilt)
        before = bytes(self.rebuilt)
        self.assertFalse(secure_area_crc_fix(bytes(self.original), self.rebuilt))
        self.assertEqual(self.rebuilt, before)

    def test_other_header_changes_remain_visible(self):
        self.rebuilt[0] = ord("L")
        self.assertTrue(secure_area_crc_fix(bytes(self.original), self.rebuilt))
        self.assertEqual(self.rebuilt[0], ord("L"))
        self.assertNotEqual(self.rebuilt, self.original)
        self.assertEqual(struct.unpack_from("<H", self.rebuilt, 0x15e)[0],
                         _common.crc16(self.rebuilt[:0x15e]))

    def test_different_game_or_arm9_location_is_not_repaired(self):
        for offset, value in [(0x0c, b"TEST"), (0x20, struct.pack("<I", 0x8000))]:
            with self.subTest(offset=offset):
                rebuilt = bytearray(self.rebuilt)
                rebuilt[offset:offset + len(value)] = value
                before = bytes(rebuilt)
                self.assertFalse(secure_area_crc_fix(bytes(self.original), rebuilt))
                self.assertEqual(rebuilt, before)

    def test_truncated_input_is_not_repaired(self):
        before = bytes(self.rebuilt)
        self.assertFalse(secure_area_crc_fix(bytes(self.original[:0x4000]), self.rebuilt))
        self.assertEqual(self.rebuilt, before)


if __name__ == "__main__":
    unittest.main()
