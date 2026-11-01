from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest

own = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", own / "prepare_dlc_dex_hook.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
aot, nso = map(Path, sys.argv[1:3])
sys.argv = sys.argv[:1]

class GuardTests(unittest.TestCase):
    def test_only_one_function_changes(self):
        original = (aot / "main" / p.UNIT).read_text()
        patched = p.patch_text(original)
        self.assertEqual(original.replace(p.function_body(original, p.FUNCTION), ""),
                         patched.replace(p.function_body(patched, p.FUNCTION), ""))
        self.assertEqual(patched.replace(p.REPLACEMENT, p.ANCHOR), original)
        with self.assertRaises(ValueError):
            p.patch_text(patched)

    def test_changed_anchor(self):
        original = (aot / "main" / p.UNIT).read_text()
        with self.assertRaises(ValueError):
            p.patch_text(original.replace("0x70008d41bcull", "0x70008d41bdull"))

    def test_preparation_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            report = p.prepare(aot, nso, temp / "out")
            self.assertEqual(report["target_hash"], "58e63b00d271631f")
            self.assertEqual(p.prepare(aot, nso, temp / "out"), report)
            self.assertEqual(json.loads((temp / "out" / "dlc-dex-hook-manifest.json").read_text()), report)
            (temp / "out" / p.UNIT).write_text("different")
            with self.assertRaises(ValueError):
                p.prepare(aot, nso, temp / "out")
            changed = temp / "aot"
            changed.mkdir()
            (changed / p.UNIT).write_bytes((aot / "main" / p.UNIT).read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                p.prepare(changed, nso, temp / "not-created")
            self.assertFalse((temp / "not-created").exists())
            badnso = temp / "bad-main"
            badnso.write_bytes(b"NSO0" + bytes(0x100))
            with self.assertRaises(ValueError):
                p.prepare(aot, badnso, temp / "not-created")

    def test_no_in_place(self):
        with self.assertRaises(ValueError):
            p.prepare(aot, nso, aot / "main")

if __name__ == "__main__":
    unittest.main()
