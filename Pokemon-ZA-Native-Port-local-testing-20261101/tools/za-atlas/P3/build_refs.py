#!/usr/bin/env python3
"""Build guest references from translated C without modifying game inputs.

Only a function is buffered at once. Unknown expressions, incoming branch targets,
and calls invalidate register constants instead of guessing runtime addresses.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO.parent / "za-atlas-data"
GAME = Path(r"C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc\update-2.0.2-20261025")
DEFINITION = re.compile(r"^void f_([0-9a-f]+)\(Cpu \*c\)\s*\{")
LITERAL = re.compile(r"\b0x([0-9a-fA-F]+)(?:ull|ULL|ul|UL|u|U|ll|LL)?\b")
ASSIGN = re.compile(r"c->x\[(\d+)\]\s*=(?!=)\s*([^;]+);")
EA = re.compile(r"\buint64_t ea\s*=\s*([^;]+);")
GOTO = re.compile(r"\bgoto (L_[0-9a-f]+)\b")
LABEL = re.compile(r"^(L_[0-9a-f]+):")
CALL = re.compile(r"\bf_[0-9a-f]+\(c\)|\b(?:rt_)?dispatch\(c\)")
TOKEN = re.compile(r"\s*(c->x\[\d+\]|0x[0-9a-fA-F]+(?:[uUlL]+)?|\d+(?:[uUlL]+)?|[A-Za-z_]\w*|<<|>>|[()~+*\-&|^])")
REG = re.compile(r"c->x\[(\d+)\]$")
TYPES = {"uint64_t": 64, "uint32_t": 32, "uint16_t": 16, "uint8_t": 8,
         "int64_t": -64, "int32_t": -32, "int16_t": -16, "int8_t": -8}
PRECEDENCE = {"|": 1, "^": 2, "&": 3, "<<": 4, ">>": 4, "+": 5, "-": 5, "*": 6}
MASK64 = (1 << 64) - 1


def low_priority():
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.SetPriorityClass.restype = ctypes.c_int
        kernel.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        kernel.GetPriorityClass.restype = ctypes.c_uint32
        handle = kernel.GetCurrentProcess()
        if not kernel.SetPriorityClass(handle, 0x4000) or kernel.GetPriorityClass(handle) != 0x4000:
            raise OSError("could not set BELOW_NORMAL_PRIORITY_CLASS")
    else:
        try:
            os.nice(10)
        except OSError:
            pass


class Expression:
    """Small, non-executing evaluator for constant integer/register expressions."""
    def __init__(self, text, regs):
        self.tokens = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = TOKEN.match(text, pos)
            if not m:
                raise ValueError("unknown C expression")
            self.tokens.append(m.group(1))
            pos = m.end()
        self.pos = 0
        self.regs = regs

    def atom(self):
        if self.pos >= len(self.tokens):
            raise ValueError("missing operand")
        tok = self.tokens[self.pos]
        self.pos += 1
        if tok in ("~", "-", "+"):
            value = self.atom()
            return ~value if tok == "~" else (-value if tok == "-" else value)
        if tok == "(":
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos] in TYPES and self.tokens[self.pos + 1] == ")":
                width = TYPES[self.tokens[self.pos]]
                self.pos += 2
                value = self.atom() & ((1 << abs(width)) - 1)
                if width < 0 and value & (1 << (abs(width) - 1)):
                    value -= 1 << abs(width)
                return value
            value = self.expr()
            if self.pos >= len(self.tokens) or self.tokens[self.pos] != ")":
                raise ValueError("missing close parenthesis")
            self.pos += 1
            return value
        r = REG.fullmatch(tok)
        if r:
            value = self.regs.get(int(r.group(1)))
            if value is None:
                raise ValueError("unknown register")
            return value
        if tok[0].isdigit():
            return int(re.sub(r"[uUlL]+$", "", tok), 0)
        raise ValueError("not a constant")

    def expr(self, min_prec=0):
        left = self.atom()
        while self.pos < len(self.tokens):
            op = self.tokens[self.pos]
            prec = PRECEDENCE.get(op, -1)
            if prec < min_prec:
                break
            self.pos += 1
            right = self.expr(prec + 1)
            if op == "+": left += right
            elif op == "-": left -= right
            elif op == "*": left *= right
            elif op == "&": left &= right
            elif op == "|": left |= right
            elif op == "^": left ^= right
            elif op in ("<<", ">>"):
                if not 0 <= right < 64:
                    raise ValueError("undefined shift")
                left = left << right if op == "<<" else left >> right
            if left.bit_length() > 128:
                raise ValueError("excessively large constant")
        return left


def evaluate(text, regs):
    try:
        parser = Expression(text, regs)
        value = parser.expr()
        return value & MASK64 if parser.pos == len(parser.tokens) else None
    except (ValueError, OverflowError, RecursionError):
        return None


def ranges_from_nso(exefs):
    """Read only NSO headers; module bases match runtime/rt.h."""
    ranges = []
    for module, base in (("main", 0x7000000000), ("sdk", 0x7008000000)):
        with (exefs / module).open("rb") as src:
            header = src.read(0x100)
        if header[:4] != b"NSO0":
            raise ValueError(f"invalid NSO header: {module}")
        for index, (name, perm) in enumerate((("text", "rx"), ("rodata", "r"), ("data", "rw"))):
            _, offset, size = struct.unpack_from("<III", header, 0x10 + index * 0x10)
            ranges.append({"module": module, "name": name, "start": base + offset, "end": base + offset + size, "perm": perm})
        bss_size = struct.unpack_from("<I", header, 0x3c)[0]
        if bss_size:
            ranges.append({"module": module, "name": "bss", "start": ranges[-1]["end"], "end": ranges[-1]["end"] + bss_size, "perm": "rw"})
    return ranges


def in_range(value, ranges):
    return value is not None and any(start <= value < end for start, end in ranges)


def scan_function(addr, unit, lines, ranges):
    targets = {m.group(1) for _, text in lines for m in GOTO.finditer(text)}
    regs = {}
    rows = []
    key_checks = []
    for lineno, text in lines:
        label = LABEL.match(text)
        if label and label.group(1) in targets:
            regs.clear()
        found = {}
        for match in LITERAL.finditer(text):
            value = int(match.group(1), 16)
            if in_range(value, ranges):
                found[value] = "literal"
        for match in EA.finditer(text):
            expression = match.group(1)
            if "c->x[" in expression:
                value = evaluate(expression, regs)
                if in_range(value, ranges):
                    found.setdefault(value, "adrp_add")
        for match in ASSIGN.finditer(text):
            reg = int(match.group(1))
            expression = match.group(2)
            value = evaluate(expression, regs)
            if value is None:
                regs.pop(reg, None)
                continue
            regs[reg] = value
            if "c->x[" in expression and in_range(value, ranges):
                found.setdefault(value, "adrp_add")
            if value == 0x4f35d0dd and "c->x[" in expression:
                key_checks.append({"func": addr, "unit": unit, "line": lineno,
                                   "constant": "4f35d0dd", "construction": "movz_movk", "guest_address": False})
        rows.extend({"func": addr, "target": f"{target:x}", "unit": unit,
                     "line": lineno, "how": how} for target, how in sorted(found.items()))
        if CALL.search(text):
            # AAPCS64 caller-saved x0-x18 and LR; x19-x29 survive a call.
            for reg in list(regs):
                if reg <= 18 or reg == 30:
                    regs.pop(reg, None)
        if "goto " in text or re.search(r"\breturn\b", text):
            regs.clear()
    return rows, key_checks


def scan_unit(job):
    path, shard, ranges = job
    path, shard = Path(path), Path(shard)
    fn = None
    lines = []
    count = functions = literal = derived = 0
    keys = []
    with path.open("r", encoding="utf-8", errors="strict", newline="") as source, shard.open("w", encoding="utf-8", newline="\n") as output:
        def flush():
            nonlocal count, functions, literal, derived
            if fn is None:
                return
            rows, checks = scan_function(fn, path.name, lines, ranges)
            functions += 1
            keys.extend(checks)
            for row in rows:
                output.write(json.dumps(row, separators=(",", ":")) + "\n")
                count += 1
                if row["how"] == "literal": literal += 1
                else: derived += 1
        for lineno, text in enumerate(source, 1):
            definition = DEFINITION.match(text)
            if definition:
                flush()
                fn = definition.group(1)
                lines = []
            if fn is not None:
                lines.append((lineno, text))
        flush()
    return {"unit": path.name, "functions": functions, "records": count,
            "literal": literal, "adrp_add": derived, "source_bytes": path.stat().st_size,
            "shard": str(shard), "key_checks": keys}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def heartbeat(agent):
    if agent:
        result = subprocess.run([sys.executable, "-I", str(REPO / "tools/za-atlas/claim.py"), "heartbeat", "--agent", agent, "--package", "P3"], cwd=REPO, capture_output=True, text=True)
        if result.returncode or '"lost": true' in result.stdout:
            raise RuntimeError(f"claim lost or heartbeat failed: {result.stdout} {result.stderr}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aot", type=Path, default=GAME / "aot")
    parser.add_argument("--exefs", type=Path, default=GAME / "game/exefs")
    parser.add_argument("--output", type=Path, default=ROOT / "parts/P3")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--agent")
    parser.add_argument("--unit", action="append", help="Limit to a filename; sample runs do not produce DONE.json")
    args = parser.parse_args()
    low_priority()
    started = time.monotonic()
    heartbeat(args.agent)
    args.output.mkdir(parents=True, exist_ok=True)
    shard_dir = args.output / "_shards"
    shard_dir.mkdir(exist_ok=True)
    segments = ranges_from_nso(args.exefs)
    ranges = [(x["start"], x["end"]) for x in segments]
    units = sorted([*args.aot.joinpath("main").glob("*.c"), *args.aot.joinpath("sdk").glob("*.c")], key=lambda p: (p.parent.name, p.name))
    if args.unit:
        units = [path for path in units if path.name in args.unit]
    if not units:
        raise ValueError("no C units found")
    jobs = [(str(path), str(shard_dir / f"{index:04d}.jsonl"), ranges) for index, path in enumerate(units)]
    results = []
    last_hb = time.monotonic()
    with mp.Pool(max(1, min(args.workers, 2)), initializer=low_priority) as pool:
        pending = pool.imap_unordered(scan_unit, jobs, chunksize=1)
        while len(results) < len(jobs):
            try:
                result = pending.next(timeout=15)
                results.append(result)
                if len(results) % 50 == 0 or len(results) == len(jobs):
                    print(json.dumps({"units_done": len(results), "units_total": len(jobs), "functions": sum(r["functions"] for r in results), "records": sum(r["records"] for r in results), "elapsed_seconds": round(time.monotonic() - started, 2)}), flush=True)
            except mp.TimeoutError:
                pass
            if time.monotonic() - last_hb > 120:
                heartbeat(args.agent)
                last_hb = time.monotonic()
    heartbeat(args.agent)
    output = args.output / "refs.jsonl"
    with output.open("wb") as target:
        for job in jobs:
            with Path(job[1]).open("rb") as source:
                shutil.copyfileobj(source, target, 1 << 20)
    checks = sorted([entry for result in results for entry in result["key_checks"]], key=lambda x: (x["unit"], x["line"]))
    summary = {"package": "P3", "agent": args.agent, "units": len(units),
               "functions_scanned": sum(r["functions"] for r in results),
               "records": {"refs.jsonl": sum(r["records"] for r in results)},
               "by_how": {"literal": sum(r["literal"] for r in results), "adrp_add": sum(r["adrp_add"] for r in results)},
               "source_bytes": sum(r["source_bytes"] for r in results),
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "segment_ranges": [{**entry, "start": f'{entry["start"]:x}', "end": f'{entry["end"]:x}'} for entry in segments],
               "kmoney_split_constants": checks,
               "files": {"refs.jsonl": {"sha256": sha256(output), "bytes": output.stat().st_size}},
               "limitations": ["Conservative intraprocedural constant propagation, not runtime execution.",
                               "Unknown loads/expressions and branch joins kill register state; dynamic addresses are not guessed.",
                               "adrp_add covers a reconstructed register address and constant effective-address arithmetic.",
                               "KMoney 0x4f35d0dd is a MOVZ/MOVK save-block key, not a guest address, so it is evidence only.",
                               "FN_ENTER, return addresses, and code literals are included because the contract asks for all segment addresses."]}
    (args.output / "verification.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    mp.freeze_support()
    main()
