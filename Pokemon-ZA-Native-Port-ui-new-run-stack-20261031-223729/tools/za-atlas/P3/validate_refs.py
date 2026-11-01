#!/usr/bin/env python3
"""Validate the complete P3 artifact without retaining its records in memory."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

spec = importlib.util.spec_from_file_location("p3_refs", Path(__file__).with_name("build_refs.py"))
build = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build
spec.loader.exec_module(build)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=build.ROOT / "parts/P3")
    args = parser.parse_args()
    build.low_priority()
    started = time.monotonic()
    summary = json.loads((args.output / "verification.json").read_text(encoding="utf-8"))
    p1_path = build.ROOT / "parts/P1/functions.jsonl"
    definitions = {}
    if p1_path.exists():
        with p1_path.open(encoding="utf-8") as source:
            for line in source:
                entry = json.loads(line)
                definitions[entry["addr"]] = (entry["unit"], entry["line_start"], entry["line_end"])
    ranges = [(int(row["start"], 16), int(row["end"], 16)) for row in summary["segment_ranges"]]
    expected_keys = {"func", "target", "unit", "line", "how"}
    by_how = Counter()
    by_unit = Counter()
    function_groups = set()
    last_group = None
    seen = set()
    anchor_hits = []
    fn_hits = []
    count = 0
    for count, line in enumerate((args.output / "refs.jsonl").open(encoding="utf-8"), 1):
        row = json.loads(line)
        assert set(row) == expected_keys, (count, "schema")
        assert re.fullmatch("[0-9a-f]+", row["func"]), (count, "func address")
        assert re.fullmatch("[0-9a-f]+", row["target"]), (count, "target address")
        assert build.in_range(int(row["target"], 16), ranges), (count, "non-segment target")
        assert isinstance(row["line"], int) and row["line"] > 0, (count, "source line")
        assert row["how"] in ("literal", "adrp_add"), (count, "method")
        assert re.fullmatch(r"(?:main|sdk)_\d+\.c", row["unit"]), (count, "source unit")
        if definitions:
            assert row["func"] in definitions, (count, "function missing in P1")
            unit, start, end = definitions[row["func"]]
            assert row["unit"] == unit and start <= row["line"] <= end, (count, "source bounds differ from P1")
        group = (row["unit"], row["func"])
        if group != last_group:
            assert group not in function_groups, (count, "noncontiguous repeated function")
            function_groups.add(group)
            last_group = group
            seen.clear()
        key = (row["target"], row["line"])
        assert key not in seen, (count, "duplicate reference")
        seen.add(key)
        by_how[row["how"]] += 1
        by_unit[row["unit"]] += 1
        if row["target"] == "700329eb22":
            anchor_hits.append(row)
        if row["func"] == "7000a1158c":
            fn_hits.append(row)
    assert count == summary["records"]["refs.jsonl"], "count mismatch"
    assert dict(by_how) == summary["by_how"], "method counts mismatch"
    assert build.sha256(args.output / "refs.jsonl") == summary["files"]["refs.jsonl"]["sha256"], "hash mismatch"
    assert summary["units"] == 1411, "not all 1411 C units scanned"
    assert summary["functions_scanned"] == 270401, "function count differs from P1 metadata"
    keys = summary["kmoney_split_constants"]
    assert any(row["unit"] == "main_303.c" and row["func"] == "70009c18d8" and row["line"] == 21540 for row in keys), "KMoney main_303 reconstruction"
    assert any(row["unit"] == "main_384.c" and row["func"] == "7000dbb28c" and row["line"] == 5060 for row in keys), "KMoney main_384 reconstruction"
    result = {"passed": True, "records": count, "units_with_refs": len(by_unit),
              "functions_with_refs": len(function_groups), "by_how": dict(by_how),
              "schema_and_ranges": "passed", "duplicates": 0,
              "all_C_units": summary["units"], "all_functions": summary["functions_scanned"],
              "p1_source_bounds_crosscheck": "passed" if definitions else "P1 unavailable",
              "anchor": {"target": "700329eb22", "references": anchor_hits},
              "evaluator_refs": fn_hits, "kmoney_reconstruction": "passed",
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    (args.output / "acceptance.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
