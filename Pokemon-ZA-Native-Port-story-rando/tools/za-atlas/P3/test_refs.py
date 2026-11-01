"""Meaningful regression cases for conservative constant/reference recovery."""
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location("p3_refs", Path(__file__).with_name("build_refs.py"))
refs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = refs
spec.loader.exec_module(refs)


class ReferenceTests(unittest.TestCase):
    def scan(self, text):
        return refs.scan_function("7000000100", "main_000.c", list(enumerate(text.splitlines(), 1)), [(0x7000000000, 0x7000100000)])

    def test_split_page_and_add_across_instruction_labels(self):
        rows, _ = self.scan("""c->x[8] = (uint64_t)(0x7000002000ull);
L_7000000104:;
c->x[1] = (uint64_t)(c->x[8] + 0x123ull);""")
        self.assertIn({"func": "7000000100", "target": "7000002123", "unit": "main_000.c", "line": 3, "how": "adrp_add"}, rows)

    def test_effective_address_before_load_clobbers_register(self):
        rows, _ = self.scan("""c->x[8] = (uint64_t)(0x7000002000ull);
{ uint64_t ea = c->x[8] + 0x230ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }
c->x[1] = (uint64_t)(c->x[8] + 0x10ull);""")
        self.assertTrue(any(row["target"] == "7000002230" and row["line"] == 2 for row in rows))
        self.assertFalse(any(row["target"] == "7000002240" for row in rows))

    def test_volatile_register_lost_at_call_callee_saved_survives(self):
        rows, _ = self.scan("""c->x[8] = (uint64_t)(0x7000002000ull);
c->x[19] = (uint64_t)(0x7000003000ull);
c->x[30] = 0x7000000200ull; f_7000000100(c);
c->x[0] = (uint64_t)(c->x[8] + 0x20ull);
c->x[1] = (uint64_t)(c->x[19] + 0x10ull);""")
        self.assertFalse(any(row["target"] == "7000002020" for row in rows))
        self.assertTrue(any(row["target"] == "7000003010" for row in rows))

    def test_branch_join_discards_ambiguous_linear_state(self):
        rows, _ = self.scan("""if (COND_EQ(c)) { goto L_7000000110; }
c->x[8] = (uint64_t)(0x7000002000ull);
L_7000000110:;
c->x[0] = (uint64_t)(c->x[8] + 0x20ull);""")
        self.assertFalse(any(row["target"] == "7000002020" for row in rows))

    def test_kmoney_movz_movk_is_not_guest_reference(self):
        rows, keys = self.scan("""c->x[8] = (uint32_t)(0xd0ddull);
c->x[8] = (uint32_t)((c->x[8] & 0xffffffff0000ffffull) | 0x4f350000ull);""")
        self.assertEqual(rows, [])
        self.assertEqual(keys[0]["constant"], "4f35d0dd")
        self.assertFalse(keys[0]["guest_address"])

    def test_width_casts_and_unknown_expressions(self):
        self.assertEqual(refs.evaluate("(uint32_t)(0x7000001234ull)", {}), 0x1234)
        self.assertEqual(refs.evaluate("(uint64_t)((uint32_t)c->x[8] + 0x20ull)", {8: 0x7000001000}), 0x1020)
        self.assertIsNone(refs.evaluate("(uint64_t)(c->x[8] + unknown)", {8: 0x7000001000}))
        self.assertIsNone(refs.evaluate("evil()", {}))

    def test_duplicates_and_non_guest_constants_filtered(self):
        rows, _ = self.scan("c->x[8] = (uint64_t)(0x7000002000ull | 0x7000002000ull);\nc->x[8] = 0x12345678ull;")
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {"func", "target", "unit", "line", "how"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
