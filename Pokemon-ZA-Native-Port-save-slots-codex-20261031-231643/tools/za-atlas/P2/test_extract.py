"""Synthetic format and ownership tests, plus streaming validation of P2 output."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("atlas_p2", Path(__file__).with_name("extract.py"))
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)


class FormatTests(unittest.TestCase):
    def test_lz4_literals_and_overlapping_match(self):
        self.assertEqual(p2.lz4_block(bytes([0x50]) + b"hello", 5), b"hello")
        self.assertEqual(p2.lz4_block(bytes([0x15, 65, 1, 0]), 10), b"A" * 10)
        for payload, size in ((b"\xf0", 10), (b"\x10A\0\0", 5), (b"\x10A", 2)):
            with self.assertRaises(ValueError):
                p2.lz4_block(payload, size)

    def test_unicode_and_no_ascii_as_wide(self):
        for value in ("hello_world", "שלום עולם", "日本語文字", "Пример текста"):
            self.assertTrue(p2.wide_is_text(value), value)
        for value in ("古AಠБ", "&&&&", "ab\0cd", "ab"):
            self.assertFalse(p2.wide_is_text(value), value)
        class FakeNso:
            module = "main"
            base = 0x7000000000
            segments = [{}, {"bytes": b"hello_world\0\0" + "שלום עולם".encode("utf-16le") + b"\0\0", "off": 0x1000}]
        rows = list(p2.iter_strings(FakeNso()))
        self.assertEqual([r["text"] for r in rows if r["encoding"] == "utf-8"], ["hello_world"])
        self.assertIn("שלום עולם", [r["text"] for r in rows if r["encoding"] == "utf-16le"])
        self.assertEqual(sum(r["encoding"] == "utf-16le" for r in rows), 1)

    def test_owner_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=p2.DEFAULT_OUTPUT) as temporary:
            root = Path(temporary)
            owner = root / "claims" / "P2" / "owner.json"
            owner.parent.mkdir(parents=True)
            owner.write_text(json.dumps({"agent": "test", "claim_id": "first"}), encoding="utf-8")
            guard = p2.Ownership(root / "parts" / "P2", "test")
            owner.write_text(json.dumps({"agent": "test", "claim_id": "second"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "lost"):
                guard.check(force=True)

    def test_nso_mod0_symbols_and_relr_bitmap(self):
        image = bytearray(0x3000)
        struct.pack_into("<I", image, 4, 0x80)
        image[0x80:0x84] = b"MOD0"
        struct.pack_into("<i", image, 0x84, 0x2000 - 0x80)
        # Two symbols (including null), an exported function, and two RELR words.
        dynamic = [(4, 0x1000), (5, 0x1100), (6, 0x1200), (11, 24), (35, 16), (36, 0x1300), (0, 0)]
        for i, pair in enumerate(dynamic):
            struct.pack_into("<QQ", image, 0x2000 + 16 * i, *pair)
        struct.pack_into("<II", image, 0x1000, 1, 2)
        image[0x1100:0x1107] = b"\0entry\0"
        struct.pack_into("<IBBHQQ", image, 0x1218, 1, 0x12, 0, 1, 0x300, 4)
        struct.pack_into("<QQ", image, 0x1300, 0x2400, 3)
        struct.pack_into("<QQ", image, 0x2400, 0x300, 0x308)
        header = bytearray(0x100)
        header[:4] = b"NSO0"
        struct.pack_into("<I", header, 0xC, 0x38)  # raw segments with hashes
        for i in range(3):
            struct.pack_into("<III", header, 0x10 + i * 0x10, 0x100 + 0x1000 * i, 0x1000 * i, 0x1000)
            header[0xA0 + i * 32:0xC0 + i * 32] = hashlib.sha256(image[i * 0x1000:(i + 1) * 0x1000]).digest()
        with tempfile.TemporaryDirectory(dir=p2.DEFAULT_OUTPUT) as temporary:
            path = Path(temporary) / "sample.nso"
            path.write_bytes(header + image)
            nso = p2.Nso(path, "main")
            self.assertEqual(nso.symbols[1]["name"], "entry")
            self.assertEqual(nso.relative_count, 2)
            exports, pointers, unknown = p2.relocate([nso])
            self.assertEqual(exports["entry"], p2.BASES["main"] + 0x300)
            self.assertEqual(pointers[p2.BASES["main"] + 0x2408], p2.BASES["main"] + 0x308)
            corrupt = bytearray(path.read_bytes())
            corrupt[-1] ^= 1
            path.write_bytes(corrupt)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                p2.Nso(path, "main")


def validate_output(output):
    manifest = json.loads((output / "DONE.json").read_text(encoding="utf-8"))
    results = {}
    hex_pattern = re.compile(r"[0-9a-f]+")
    text_ranges = []
    for line in (output / "segments.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        if row["name"] == ".text":
            text_ranges.append((int(row["start"], 16), int(row["end"], 16)))
    for filename, details in manifest["files"].items():
        path = output / filename
        assert p2.file_sha256(path) == details["sha256"], filename
        kind = filename.removesuffix(".jsonl")
        count = 0
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                assert tuple(row) == p2.SCHEMAS[kind], (filename, count)
                for field in ("addr", "start", "end", "typeinfo", "vtable", "func"):
                    if row.get(field) is not None:
                        assert hex_pattern.fullmatch(row[field]), (filename, field)
                if kind == "vslots":
                    address = int(row["func"], 16)
                    assert any(start <= address < end for start, end in text_ranges), (filename, count)
                if kind == "segments":
                    assert int(row["start"], 16) < int(row["end"], 16)
                count += 1
        assert count == details["records"], filename
        assert path.stat().st_size == details["bytes"], filename
        results[filename] = count
    assert manifest["checks"]["condition_string_found"]
    assert manifest["checks"]["sdk_nn_demangled_functions"] > 0
    assert manifest["process_priority"] == "BelowNormal"
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--validate":
        print(json.dumps({"validated": validate_output(Path(sys.argv[2]))}))
    else:
        unittest.main()
