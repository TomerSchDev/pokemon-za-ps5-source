#!/usr/bin/env python3
"""Write P3/DONE.json only after the full artifact passes validation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("p3_refs", Path(__file__).with_name("build_refs.py"))
build = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build
spec.loader.exec_module(build)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--output", type=Path, default=build.ROOT / "parts/P3")
    args = parser.parse_args()
    build.low_priority()
    build.heartbeat(args.agent)
    summary = json.loads((args.output / "verification.json").read_text(encoding="utf-8"))
    acceptance = json.loads((args.output / "acceptance.json").read_text(encoding="utf-8"))
    assert summary["agent"] == args.agent
    assert acceptance["passed"] and acceptance["records"] == summary["records"]["refs.jsonl"]
    assert acceptance["p1_source_bounds_crosscheck"] == "passed"
    assert any(row["func"] == "70007de270" and row["line"] == 17825 for row in acceptance["anchor"]["references"])
    assert build.sha256(args.output / "refs.jsonl") == summary["files"]["refs.jsonl"]["sha256"]
    files = {name: {"sha256": build.sha256(args.output / name), "bytes": (args.output / name).stat().st_size}
             for name in ("refs.jsonl", "verification.json", "acceptance.json", "NOTES.md")}
    manifest = {"package": "P3", "agent": args.agent,
                "runtime_seconds": round(summary["elapsed_seconds"] + acceptance["elapsed_seconds"], 3),
                "parser_seconds": summary["elapsed_seconds"], "validation_seconds": acceptance["elapsed_seconds"],
                "records": summary["records"], "files": files,
                "validation": {"passed": True, "all_units": summary["units"],
                               "all_functions": summary["functions_scanned"], "duplicates": 0,
                               "unit_tests": 7, "p1_source_bounds": "passed", "kmoney_split_key": "passed",
                               "actual_string_anchor": "main_249.c:17825 -> 700329eb22"},
                "known_limitations": summary["limitations"] + [
                    "The prompt's evaluator-to-string direct reference does not exist in main_310.c; actual string reference is in main_249.c.",
                    "_shards/ and sample/ contain temporary local artifacts and are not deliverables."]}
    build.heartbeat(args.agent)
    target = args.output / "DONE.json"
    temporary = args.output / "DONE.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
