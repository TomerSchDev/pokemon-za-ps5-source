#!/usr/bin/env python3
"""Stream static-recompiler C units into the za-atlas P1 JSONL contract.

Only reads --aot. All generated records, scratch files and validation reports
are written under --out. Native source byte ranges include the definition line
through its closing brace, inclusive of the source line ending.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

DEF = re.compile(rb"^\s*void\s+f_([0-9a-fA-F]+)\s*\(\s*Cpu\s*\*\s*c\s*\)\s*\{")
DECL = re.compile(rb"^\s*void\s+f_([0-9a-fA-F]+)\s*\(\s*Cpu\s*\*\s*c\s*\)\s*;")
CALL = re.compile(rb"\bf_([0-9a-fA-F]+)\s*\(\s*c\s*\)")
ICALL = re.compile(rb"\b(?:rt_)?dispatch\s*\(\s*c\s*\)")
NON_CODE = re.compile(rb'//[^\r\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.DOTALL)
NAMES = ("functions.jsonl", "calls.jsonl", "icalls.jsonl")


def low_priority():
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.SetPriorityClass.restype = ctypes.c_int
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000):
            raise ctypes.WinError(ctypes.get_last_error())
    elif hasattr(os, "nice"):
        os.nice(10)


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def emit(out, row):
    out.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")


def ensure_owner(out, agent):
    if agent is None:
        return
    owner_path = Path(out).parent.parent / "claims" / "P1" / "owner.json"
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    if owner.get("agent") != agent:
        raise RuntimeError("lost P1 claim; stop all writes")


def heartbeat(out, agent):
    if agent is None:
        return
    ensure_owner(out, agent)
    claim = Path(__file__).resolve().parents[1] / "claim.py"
    result = subprocess.run([sys.executable, "-I", str(claim), "heartbeat", "--agent", agent,
                             "--package", "P1", "--root", str(Path(out).parent.parent)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("claim heartbeat failed: " + result.stdout + result.stderr)


def code_line(raw, in_comment):
    """Erase strings/comments before counting braces and call tokens."""
    if in_comment:
        end = raw.find(b"*/")
        if end < 0:
            return b"", True
        raw = raw[end + 2:]
    # The generated C uses one-line comments almost exclusively. Preserve the
    # remaining prefix if a block comment extends into subsequent source lines.
    clean = NON_CODE.sub(b"", raw)
    start = clean.find(b"/*")
    if start >= 0:
        return clean[:start], True
    return clean, False


def scan_unit(path, module, streams):
    unit = path.name
    current = None
    offset = 0
    depth = 0
    in_comment = False
    line_no = 0
    counts = dict.fromkeys(NAMES, 0)
    with path.open("rb") as src:
        for line_no, raw in enumerate(src, 1):
            start_offset = offset
            offset += len(raw)
            code, in_comment = code_line(raw, in_comment)
            definition = DEF.match(code)
            if definition:
                if current is not None:
                    raise ValueError(f"nested definition at {unit}:{line_no}")
                current = {"addr": definition[1].decode("ascii").lower(), "module": module,
                           "unit": unit, "line_start": line_no}
                function_offset = start_offset
                depth = 0
                # The definition itself has a Cpu argument and is not a call.
                body = code[definition.end():]
            else:
                body = code
            if current is None:
                continue
            for match in CALL.finditer(body):
                emit(streams["calls.jsonl"], {"caller": current["addr"],
                     "callee": match[1].decode("ascii").lower(), "unit": unit, "line": line_no})
                counts["calls.jsonl"] += 1
            for _ in ICALL.finditer(body):
                emit(streams["icalls.jsonl"], {"caller": current["addr"], "unit": unit, "line": line_no})
                counts["icalls.jsonl"] += 1
            depth += code.count(b"{") - code.count(b"}")
            if depth == 0:
                current["line_end"] = line_no
                current["c_bytes"] = offset - function_offset
                emit(streams["functions.jsonl"], current)
                counts["functions.jsonl"] += 1
                current = None
            elif depth < 0:
                raise ValueError(f"negative function brace depth at {unit}:{line_no}")
    if current is not None:
        raise ValueError(f"unterminated function {current['addr']} in {unit}")
    return {"unit": unit, "module": module, "source_bytes": offset, "source_lines": line_no,
            "counts": counts}


def scan_batch(args):
    paths, output, worker_id, agent = args
    low_priority()
    ensure_owner(output, agent)
    directory = Path(output) / "_work" / str(worker_id)
    directory.mkdir(parents=True, exist_ok=True)
    streams = {name: (directory / name).open("w", encoding="utf-8", newline="\n") for name in NAMES}
    units = []
    try:
        for filename, module in paths:
            ensure_owner(output, agent)
            units.append(scan_unit(Path(filename), module, streams))
            if len(units) % 10 == 0:
                write_json(directory / "progress.json", {"completed_units": len(units), "total_units": len(paths),
                           "source_bytes": sum(x["source_bytes"] for x in units), "latest": filename})
    finally:
        for stream in streams.values():
            stream.close()
    write_json(directory / "progress.json", {"completed_units": len(units), "total_units": len(paths),
               "source_bytes": sum(x["source_bytes"] for x in units), "complete": True})
    return {"directory": str(directory), "units": units}


def table_manifest(aot, module):
    """Independently validate declarations, guest-address array and fn-pointer array."""
    path = Path(aot) / module / (module + "_table.c")
    declarations, addrs, pointers = set(), [], []
    declared_count = None
    mode = None
    with path.open("rb") as src:
        for raw in src:
            declaration = DECL.match(raw)
            if declaration:
                addr = declaration[1].decode("ascii").lower()
                if addr in declarations:
                    raise ValueError(f"duplicate declaration {addr} in {path.name}")
                declarations.add(addr)
            if raw.startswith(f"const uint64_t {module}_fn_addrs[]".encode()):
                mode = "addresses"
                continue
            if raw.startswith(f"const GuestFn {module}_fn_ptrs[]".encode()):
                mode = "pointers"
                continue
            if mode == "addresses":
                addrs.extend(m.decode("ascii").lower() for m in re.findall(rb"0x([0-9a-fA-F]+)", raw))
            elif mode == "pointers":
                pointers.extend(m.decode("ascii").lower() for m in re.findall(rb"\bf_([0-9a-fA-F]+)", raw))
            if b"};" in raw:
                mode = None
            count_match = re.search(rb"_fn_count\s*=\s*(\d+)", raw)
            if count_match:
                declared_count = int(count_match[1])
    if not declared_count or not (len(declarations) == len(addrs) == len(pointers) == declared_count):
        raise ValueError(f"table count mismatch for {module}")
    if declarations != set(addrs) or addrs != pointers or len(set(addrs)) != len(addrs):
        raise ValueError(f"table identities/order mismatch for {module}")
    return declarations, {"file": path.name, "declarations": len(declarations), "registered": declared_count,
                          "address_pointer_order_matches": True}


def validate_output(aot, out):
    expected = {}
    tables = {}
    for module in ("main", "sdk"):
        expected[module], tables[module] = table_manifest(aot, module)
    actual = {"main": set(), "sdk": set()}
    counts = dict.fromkeys(NAMES, 0)
    anchor = None
    byte_samples = []
    schema = {"functions.jsonl": {"addr", "module", "unit", "line_start", "line_end", "c_bytes"},
              "calls.jsonl": {"caller", "callee", "unit", "line"},
              "icalls.jsonl": {"caller", "unit", "line"}}
    for name in NAMES:
        with (Path(out) / name).open(encoding="utf-8") as src:
            for raw in src:
                row = json.loads(raw)
                if set(row) != schema[name]:
                    raise ValueError(f"unexpected schema in {name}")
                counts[name] += 1
                if name == "functions.jsonl":
                    addr, module = row["addr"], row["module"]
                    if addr in actual[module]:
                        raise ValueError(f"duplicate definition {addr}")
                    if row["line_start"] > row["line_end"] or row["c_bytes"] <= 0:
                        raise ValueError(f"invalid byte/line extent {addr}")
                    actual[module].add(addr)
                    if len(byte_samples) < 4 or addr == "7000a1158c":
                        byte_samples.append(row)
                    if addr == "7000a1158c":
                        anchor = row
    for module in actual:
        if actual[module] != expected[module]:
            missing = sorted(expected[module] - actual[module])
            extra = sorted(actual[module] - expected[module])
            raise ValueError(f"definition/table mismatch {module}: missing={missing[:10]} extra={extra[:10]}")
    if actual["main"] & actual["sdk"]:
        raise ValueError("duplicate guest address across modules")
    if anchor is None or anchor["unit"] != "main_310.c":
        raise ValueError("acceptance function not found in expected unit")
    all_functions = actual["main"] | actual["sdk"]
    anchor_calls = []
    missing_callees = set()
    for name in ("calls.jsonl", "icalls.jsonl"):
        with (Path(out) / name).open(encoding="utf-8") as src:
            for raw in src:
                row = json.loads(raw)
                if row["caller"] not in all_functions:
                    raise ValueError(f"unknown caller in {name}")
                if name == "calls.jsonl":
                    if row["callee"] not in all_functions:
                        missing_callees.add(row["callee"])
                    if row["caller"] == "7000a1158c":
                        anchor_calls.append(row)
    if not any(row["callee"] == "700033e770" for row in anchor_calls):
        raise ValueError("acceptance call edge missing")
    # Re-read complete source files for several independent byte extent checks.
    for row in byte_samples:
        total = 0
        with (Path(aot) / row["module"] / row["unit"]).open("rb") as src:
            for lineno, raw in enumerate(src, 1):
                if row["line_start"] <= lineno <= row["line_end"]:
                    total += len(raw)
                if lineno == row["line_end"]:
                    break
        if total != row["c_bytes"]:
            raise ValueError("independent c_bytes check failed")
    return {"counts": counts, "tables": tables, "definition_counts": {m: len(x) for m, x in actual.items()},
            "duplicates": 0, "anchor_function": anchor, "anchor_calls": anchor_calls,
            "independent_byte_extent_samples": len(byte_samples),
            "unresolved_direct_callees": sorted(missing_callees)}


def build(aot, out, workers=2, agent=None):
    started = time.monotonic()
    low_priority()
    aot, out = Path(aot), Path(out)
    ensure_owner(out, agent)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "DONE.json").exists():
        raise ValueError("P1 already has DONE.json; preserve it rather than silently overwrite")
    heartbeat(out, agent)
    metadata = {}
    for name in ("main.generated", "sdk.generated", "inputs.json", "build-result.json"):
        path = aot / name
        if path.exists():
            metadata[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "keys": sorted(json.loads(path.read_text(encoding="utf-8")))}
    paths = [(str(path), module) for module in ("main", "sdk")
             for path in sorted((aot / module).glob("*.c"))]
    workers = max(1, min(2, workers))
    batches = [paths[i::workers] for i in range(workers)]
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(scan_batch, (batch, str(out), i, agent)) for i, batch in enumerate(batches)}
        while pending:
            ready, pending = wait(pending, timeout=45, return_when=FIRST_COMPLETED)
            heartbeat(out, agent)
            for future in ready:
                results.append(future.result())
    ensure_owner(out, agent)
    results.sort(key=lambda x: x["directory"])
    for name in NAMES:
        temp = out / (name + ".tmp")
        with temp.open("wb") as dst:
            for result in results:
                with (Path(result["directory"]) / name).open("rb") as src:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        os.replace(temp, out / name)
    heartbeat(out, agent)
    validation = validate_output(aot, out)
    validation["source_units"] = len(paths)
    validation["source_bytes"] = sum(unit["source_bytes"] for result in results for unit in result["units"])
    validation["metadata_inspection"] = metadata
    validation["metadata_limitation"] = "Stamp files contain hashes/configuration, not source line/function boundaries."
    write_json(out / "validation.json", validation)
    duration = round(time.monotonic() - started, 3)
    limitations = ["Graph describes generated C call sites, including direct tail calls; inlined guest calls are not recoverable from these units.",
                   "Indirect rt_dispatch/dispatch targets remain unresolved in icalls.jsonl.",
                   "c_bytes is generated C source byte length, not original guest machine-code size."]
    if validation["unresolved_direct_callees"]:
        limitations.append("Some direct callees have no definition in the selected main/sdk unit corpus; see validation.json.")
    done = {"package": "P1", "agent": agent, "runtime_seconds": duration,
            "records": validation["counts"], "files": {}, "validation": {"passed": True,
            "source_units": len(paths), "definition_counts": validation["definition_counts"],
            "table_declarations_match": True, "duplicates": 0, "anchor_call_passed": True},
            "known_limitations": limitations}
    for name in (*NAMES, "validation.json"):
        path = out / name
        digest = hashlib.sha256()
        with path.open("rb") as src:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                digest.update(chunk)
        done["files"][name] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
    ensure_owner(out, agent)
    write_json(out / "DONE.json", done)
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aot", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--agent", help="Owner ID from claim.py; required for coordinated live builds")
    args = ap.parse_args()
    print(json.dumps(build(args.aot, args.out, args.workers, args.agent), ensure_ascii=False))


if __name__ == "__main__":
    main()
