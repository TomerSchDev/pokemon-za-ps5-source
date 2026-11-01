"""Checks parser boundaries/call kinds against synthetic C, without game data."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("index_functions", Path(__file__).with_name("index_functions.py"))
index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index)


class ParserTests(unittest.TestCase):
    def test_nested_braces_comments_tail_calls_and_crlf_bytes(self):
        fixture = (b'void f_100(Cpu *c);\r\n'
                   b'/* f_dead(c); {\r\n'
                   b'   rt_dispatch(c); } */\r\n'
                   b'void f_100(Cpu *c) {\r\n'
                   b'  const char *x = "} f_dead(c);";\r\n'
                   b'  if (1) { f_200(c); } /* f_bad(c); */\r\n'
                   b'  rt_dispatch(c); dispatch(c);\r\n'
                   b'  __attribute__((musttail)) return f_300(c);\r\n'
                   b'}\r\n'
                   b'void f_200(Cpu *c) { return; }\r\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main_001.c"
            path.write_bytes(fixture)
            streams = {name: io.StringIO() for name in index.NAMES}
            result = index.scan_unit(path, "main", streams)
        rows = {name: [json.loads(line) for line in out.getvalue().splitlines()]
                for name, out in streams.items()}
        self.assertEqual(result["source_bytes"], len(fixture))
        self.assertEqual([(x["addr"], x["line_start"], x["line_end"]) for x in rows["functions.jsonl"]],
                         [("100", 4, 9), ("200", 10, 10)])
        self.assertEqual(rows["functions.jsonl"][0]["c_bytes"], sum(map(len, fixture.splitlines(keepends=True)[3:9])))
        self.assertEqual([(x["callee"], x["line"]) for x in rows["calls.jsonl"]], [("200", 6), ("300", 8)])
        self.assertEqual([x["line"] for x in rows["icalls.jsonl"]], [7, 7])

    def test_unterminated_function_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sdk_000.c"
            path.write_bytes(b"void f_100(Cpu *c) {\n f_200(c);\n")
            with self.assertRaisesRegex(ValueError, "unterminated"):
                index.scan_unit(path, "sdk", {name: io.StringIO() for name in index.NAMES})

    def test_registry_order_is_checked_not_only_counts(self):
        table = (b"void f_100(Cpu *c);\nvoid f_200(Cpu *c);\n"
                 b"const uint64_t main_fn_addrs[] = {\n0x100ull,\n0x200ull};\n"
                 b"const GuestFn main_fn_ptrs[] = {\nf_200,\nf_100};\n"
                 b"const uint64_t main_fn_count = 2;\n")
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "main"
            module.mkdir()
            (module / "main_table.c").write_bytes(table)
            with self.assertRaisesRegex(ValueError, "order mismatch"):
                index.table_manifest(directory, "main")


if __name__ == "__main__":
    unittest.main()
