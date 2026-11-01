#!/usr/bin/env python3
"""Read-only NSO metadata extraction; all derived game data goes outside git.

No third-party Python dependencies. Addresses are lowercase guest hexadecimal.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import unicodedata

DEFAULT_GAME = Path(r"C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc\update-2.0.2-20261025\game\exefs")
DEFAULT_OUTPUT = Path(r"C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\za-atlas-data\parts\P2")
BASES = {"main": 0x7000000000, "sdk": 0x7008000000}
SCHEMAS = {
    "segments": ("module", "name", "start", "end", "perm"),
    "strings": ("addr", "module", "text", "encoding"),
    "symbols": ("addr", "module", "mangled", "demangled", "kind"),
    "rtti": ("class", "typeinfo", "vtable", "bases"),
    "vslots": ("vtable", "slot", "func"),
}


def lower_priority():
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.SetPriorityClass.restype = ctypes.c_int
        kernel.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        kernel.GetPriorityClass.restype = ctypes.c_uint32
        process = kernel.GetCurrentProcess()
        if not kernel.SetPriorityClass(process, 0x4000) or kernel.GetPriorityClass(process) != 0x4000:
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.nice(10)
    return "BelowNormal" if os.name == "nt" else "nice+10"


class Ownership:
    """Fail closed if this package claim is replaced or disappears."""
    def __init__(self, output: Path, agent: str):
        self.owner_path = output.parent.parent / "claims" / "P2" / "owner.json"
        self.heartbeat_path = self.owner_path.with_name("heartbeat")
        self.agent = agent
        self.claim_id = None
        self.last_check = 0.0
        self.last_heartbeat = 0.0
        self.check(force=True)

    def check(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_check < 1:
            return
        try:
            owner = json.loads(self.owner_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError("lost P2 ownership: missing owner") from error
        if owner.get("agent") != self.agent or (self.claim_id is not None and owner.get("claim_id") != self.claim_id):
            raise RuntimeError("lost P2 ownership: agent or claim generation changed")
        self.claim_id = owner["claim_id"]
        self.last_check = now
        if now - self.last_heartbeat >= 60:
            self.heartbeat_path.write_text(time.strftime("%Y%m%d-%H%M%S"), encoding="utf-8")
            self.last_heartbeat = now


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lz4_block(src: bytes, expected: int) -> bytes:
    """Decode a raw LZ4 block with explicit input/output bounds checks."""
    dst = bytearray()
    i = 0
    while i < len(src):
        token = src[i]
        i += 1
        literals = token >> 4
        if literals == 15:
            while True:
                if i >= len(src):
                    raise ValueError("truncated LZ4 literal length")
                more = src[i]
                i += 1
                literals += more
                if more != 255:
                    break
        if i + literals > len(src) or len(dst) + literals > expected:
            raise ValueError("invalid LZ4 literal bounds")
        dst.extend(src[i:i + literals])
        i += literals
        if i == len(src):
            break
        if i + 2 > len(src):
            raise ValueError("truncated LZ4 match offset")
        distance = src[i] | src[i + 1] << 8
        i += 2
        length = token & 15
        if length == 15:
            while True:
                if i >= len(src):
                    raise ValueError("truncated LZ4 match length")
                more = src[i]
                i += 1
                length += more
                if more != 255:
                    break
        length += 4
        if not 0 < distance <= len(dst) or len(dst) + length > expected:
            raise ValueError("invalid LZ4 match bounds")
        if distance >= length:
            dst.extend(dst[len(dst) - distance:len(dst) - distance + length])
        else:
            # Repeating a whole available period also handles overlapping matches.
            period = dst[-distance:]
            dst.extend((period * ((length + distance - 1) // distance))[:length])
    if len(dst) != expected:
        raise ValueError(f"LZ4 size mismatch: {len(dst)} != {expected}")
    return bytes(dst)


class Nso:
    def __init__(self, path: Path, module: str):
        self.module, self.base = module, BASES[module]
        raw = path.read_bytes()
        if raw[:4] != b"NSO0" or len(raw) < 0x100:
            raise ValueError(f"not NSO0: {path}")
        self.input_sha256 = hashlib.sha256(raw).hexdigest()
        self.build_id = raw[0x40:0x60].rstrip(b"\0").hex()
        self.flags = struct.unpack_from("<I", raw, 0xC)[0]
        self.segments = []
        for i, (name, perm) in enumerate(((".text", "r-x"), (".rodata", "r--"), (".data", "rw-"))):
            fo, mo, size = struct.unpack_from("<III", raw, 0x10 + i * 0x10)
            stored = struct.unpack_from("<I", raw, 0x60 + i * 4)[0] if self.flags & 1 << i else size
            if fo + stored > len(raw):
                raise ValueError("NSO segment exceeds file")
            payload = raw[fo:fo + stored]
            payload = lz4_block(payload, size) if self.flags & 1 << i else payload
            digest = hashlib.sha256(payload).digest()
            if self.flags & 1 << (i + 3) and digest != raw[0xA0 + 32 * i:0xC0 + 32 * i]:
                raise ValueError(f"NSO decompressed segment hash mismatch: {module}/{name}")
            self.segments.append({"name": name, "perm": perm, "off": mo, "size": size, "bytes": payload})
        self.bss_size = struct.unpack_from("<I", raw, 0x3C)[0]
        end = max(s["off"] + s["size"] for s in self.segments)
        self.size = end + self.bss_size
        self.image = bytearray(self.size)
        for s in self.segments:
            self.image[s["off"]:s["off"] + s["size"]] = s["bytes"]
        self.mod0 = self.u32(4)
        if self.image[self.mod0:self.mod0 + 4] != b"MOD0":
            raise ValueError("missing MOD0")
        self.dynamic = self.mod0 + self.i32(self.mod0 + 4)
        self.dyn = {}
        for off in range(self.dynamic, len(self.image) - 15, 16):
            tag, val = struct.unpack_from("<QQ", self.image, off)
            if tag == 0:
                break
            self.dyn.setdefault(tag, val)
        else:
            raise ValueError("unterminated dynamic table")
        self.symbols = []
        count = self.u32(self.dyn[4] + 4) if 4 in self.dyn else self.gnu_hash_count()
        stride = self.dyn.get(11, 24)
        if stride != 24:
            raise ValueError("unexpected Elf64_Sym size")
        for i in range(count):
            off = self.dyn[6] + stride * i
            name, info, other, section, value, size = struct.unpack_from("<IBBHQQ", self.image, off)
            self.symbols.append({"name": self.cstr(self.dyn[5] + name), "info": info,
                                 "section": section, "value": value, "size": size})
        self.relocations = []
        self.relative_count = 0
        for start_tag, size_tag in ((7, 8), (23, 2)):
            start, size = self.dyn.get(start_tag, 0), self.dyn.get(size_tag, 0)
            if size % 24:
                raise ValueError("invalid RELA table size")
            for off in range(start, start + size, 24):
                address, info, addend = struct.unpack_from("<QQq", self.image, off)
                self.relocations.append((address, info & 0xFFFFFFFF, info >> 32, addend))
        where = 0
        for off in range(self.dyn.get(36, 0), self.dyn.get(36, 0) + self.dyn.get(35, 0), 8):
            entry = self.u64(off)
            if not entry & 1:
                self.relocations.append((entry, 1027, 0, self.u64(entry)))
                self.relative_count += 1
                where = entry + 8
            else:
                for bit in range(1, 64):
                    if entry & 1 << bit:
                        address = where + 8 * (bit - 1)
                        self.relocations.append((address, 1027, 0, self.u64(address)))
                        self.relative_count += 1
                where += 63 * 8

    def u32(self, off):
        return struct.unpack_from("<I", self.image, off)[0]

    def i32(self, off):
        return struct.unpack_from("<i", self.image, off)[0]

    def u64(self, off):
        return struct.unpack_from("<Q", self.image, off)[0]

    def cstr(self, off):
        if not 0 <= off < len(self.image):
            raise ValueError("string offset outside NSO image")
        end = self.image.find(b"\0", off)
        if end < 0:
            raise ValueError("unterminated NSO string")
        return bytes(self.image[off:end]).decode("utf-8", "strict")

    def gnu_hash_count(self):
        start = self.dyn.get(0x6FFFFEF5)
        if start is None:
            return 0
        buckets, first, bloom_size, shift = struct.unpack_from("<IIII", self.image, start)
        table = start + 16 + bloom_size * 8
        maximum = first - 1
        for i in range(buckets):
            symbol = self.u32(table + 4 * i)
            if not symbol:
                continue
            while True:
                chain = self.u32(table + buckets * 4 + 4 * (symbol - first))
                maximum = max(maximum, symbol)
                symbol += 1
                if chain & 1:
                    break
        return maximum + 1


def demangle_many(names):
    names = list(dict.fromkeys(names))
    program = shutil.which("llvm-cxxfilt") or shutil.which("c++filt")
    if not program:
        candidate = Path(r"C:\Program Files\LLVM\bin\llvm-cxxfilt.exe")
        program = str(candidate) if candidate.exists() else None
    if not program:
        raise RuntimeError("llvm-cxxfilt or c++filt is required for truthful demangling")
    result = {}
    for at in range(0, len(names), 2000):
        chunk = names[at:at + 2000]
        run = subprocess.run([program], input="\n".join(chunk) + "\n", text=True,
                             encoding="utf-8", capture_output=True, check=True)
        output = run.stdout.splitlines()
        if len(chunk) != len(output):
            raise ValueError("demangler output row count mismatch")
        result.update(zip(chunk, output))
    return result, program


def wide_is_text(value):
    """Keep coherent Unicode scripts; reject arbitrary mixtures of uint16 data."""
    if len(value) < 4 or not all(c.isprintable() for c in value):
        return False
    counts = collections.Counter()
    letters = 0
    for character in value:
        category = unicodedata.category(character)
        if category[0] in "LN":
            letters += 1
        if category[0] in "PNSZ":
            counts["common"] += 1
            continue
        name = unicodedata.name(character, "")
        script = "other"
        for candidate in ("LATIN", "HEBREW", "ARABIC", "CYRILLIC", "GREEK", "HANGUL", "THAI", "DEVANAGARI"):
            if candidate in name:
                script = candidate
                break
        if any(candidate in name for candidate in ("CJK", "HIRAGANA", "KATAKANA", "IDEOGRAPHIC")):
            script = "JAPANESE_CJK"
        counts[script] += 1
    if letters < 3 or counts["other"]:
        return False
    scripts = {key: count for key, count in counts.items() if key != "common"}
    if not scripts:
        return False
    dominant = max(scripts, key=scripts.get)
    return (scripts[dominant] + counts["common"]) / len(value) >= 0.9


def iter_strings(nso):
    """NUL-terminated printable UTF-8 and UTF-16LE strings in .rodata.

    Require four Unicode characters. Wide strings must have a coherent script
    and must not overlap already identified UTF-8 strings. This remains a
    heuristic, because arbitrary binary data can also form valid Unicode.
    """
    segment = nso.segments[1]
    data = segment["bytes"]
    origin = nso.base + segment["off"]
    narrow_intervals = []
    for match in re.finditer(rb"[^\x00-\x1f\x7f]{4,}\x00", data):
        payload = match.group()[:-1]
        try:
            value = payload.decode("utf-8", "strict")
        except UnicodeDecodeError:
            continue
        if len(value) >= 4 and all(c.isprintable() or c in "\t\r\n" for c in value):
            narrow_intervals.append((match.start(), match.end()))
            yield {"addr": f"{origin + match.start():x}", "module": nso.module,
                   "text": value, "encoding": "utf-8"}
    narrow_starts = [a for a, b in narrow_intervals]
    # Both byte alignments are considered. Restrict lengths to avoid large
    # binary runs and accept surrogate pairs through Python's strict decoder.
    for alignment in (0, 1):
        start = alignment
        for pos in range(alignment, len(data) - 1, 2):
            unit = data[pos] | data[pos + 1] << 8
            if unit == 0:
                interval = bisect.bisect_left(narrow_starts, pos + 2) - 1
                overlap = interval >= 0 and narrow_intervals[interval][1] > start
                if pos - start >= 8 and not overlap:
                    payload = data[start:pos]
                    try:
                        value = payload.decode("utf-16le", "strict")
                    except UnicodeDecodeError:
                        value = ""
                    if wide_is_text(value):
                        yield {"addr": f"{origin + start:x}", "module": nso.module,
                               "text": value, "encoding": "utf-16le"}
                start = pos + 2
            elif unit < 0x20 or unit == 0x7F or pos - start > 16384:
                start = pos + 2


def relocate(modules):
    exports = {}
    for nso in modules:
        for sym in nso.symbols:
            if sym["section"] and sym["name"]:
                exports.setdefault(sym["name"], nso.base + sym["value"])
    pointers, unknown = {}, collections.Counter()
    for nso in modules:
        for where, kind, index, addend in nso.relocations:
            if kind == 1027:  # R_AARCH64_RELATIVE
                target = nso.base + addend
            elif kind in (257, 1025, 1026):  # ABS64, GLOB_DAT, JUMP_SLOT
                sym = nso.symbols[index] if index < len(nso.symbols) else None
                if sym is None:
                    unknown[f"{nso.module}:invalid_symbol_index"] += 1
                    continue
                target = nso.base + sym["value"] if sym["section"] else exports.get(sym["name"])
                if target is None:
                    unknown[f"{nso.module}:unresolved_import"] += 1
                    continue
                target += addend
            else:
                unknown[f"{nso.module}:reloc_{kind}"] += 1
                continue
            pointers[nso.base + where] = target
    return exports, pointers, unknown


def extract_rtti(modules, exports, pointers):
    """Identify ABI typeinfo objects from proven ABI vptrs, then vtable groups."""
    abi_types = {}
    for name, address in exports.items():
        if name.startswith("_ZTVN10__cxxabiv1") and any(kind in name for kind in ("__class_type_info", "__si_class_type_info", "__vmi_class_type_info")):
            abi_types[address + 16] = name
    typeinfos = {}
    warnings = []

    def locate(guest):
        for nso in modules:
            if nso.base <= guest < nso.base + nso.size:
                return nso, guest - nso.base
        return None, 0

    for address, value in pointers.items():
        if value not in abi_types:
            continue
        nameptr = pointers.get(address + 8)
        if nameptr is None:
            continue
        nso, offset = locate(nameptr)
        if nso is None:
            continue
        try:
            raw_name = nso.cstr(offset).lstrip("*")
        except (ValueError, UnicodeDecodeError):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_$]+", raw_name) or not raw_name:
            continue
        typeinfos[address] = {"raw_name": raw_name, "abi": abi_types[value]}
    names, demangler = demangle_many("_ZTS" + t["raw_name"] for t in typeinfos.values())
    for address, info in typeinfos.items():
        human = names.get("_ZTS" + info["raw_name"], "")
        if human.startswith("typeinfo name for "):
            info["class"] = human[len("typeinfo name for "):]
        else:
            info["class"] = info["raw_name"]
        bases = []
        nso, offset = locate(address)
        abi = info["abi"]
        if "__si_class_type_info" in abi:
            base = pointers.get(address + 16)
            if base in typeinfos:
                bases.append(base)
        elif "__vmi_class_type_info" in abi:
            count = nso.u32(offset + 20)
            if count > 4096:
                warnings.append(f"invalid vmi base count at {address:x}: {count}")
            else:
                for i in range(count):
                    base = pointers.get(address + 24 + i * 16)
                    if base in typeinfos:
                        bases.append(base)
        info["base_addrs"] = bases
    tables = collections.defaultdict(list)
    slot_rows = []
    text_ranges = [(nso.base + nso.segments[0]["off"], nso.base + nso.segments[0]["off"] + nso.segments[0]["size"]) for nso in modules]
    function_exports = {nso.base + s["value"] for nso in modules for s in nso.symbols if s["section"] and s["info"] & 15 == 2}
    for typeptr_address, target in pointers.items():
        if target not in typeinfos:
            continue
        nso, offset = locate(typeptr_address - 8)
        if nso is None or offset < 0:
            continue
        offset_to_top = struct.unpack_from("<q", nso.image, offset)[0]
        if not -(1 << 30) <= offset_to_top <= 0:
            continue
        table = typeptr_address - 8
        local_slots = []
        for slot in range(4096):
            function = pointers.get(typeptr_address + 8 + slot * 8)
            if function is None:
                break
            if not any(a <= function < b for a, b in text_ranges) and function not in function_exports:
                break
            local_slots.append({"vtable": f"{table:x}", "slot": slot, "func": f"{function:x}"})
        if local_slots:
            tables[target].append(table)
            slot_rows.extend(local_slots)
    rows = []
    for address, info in sorted(typeinfos.items()):
        for table in tables.get(address, [None]):
            rows.append({"class": info["class"], "typeinfo": f"{address:x}",
                         "vtable": f"{table:x}" if table is not None else None,
                         "bases": [typeinfos[b]["class"] for b in info["base_addrs"]]})
    return rows, slot_rows, {"abi_vtable_types": abi_types, "typeinfo_objects": len(typeinfos),
                            "vtable_groups": sum(map(len, tables.values())), "warnings": warnings}


def write_rows(output, name, rows, ownership):
    count = 0
    destination = output / (name + ".jsonl")
    temporary = destination.with_suffix(".jsonl.tmp")
    ownership.check(force=True)
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            ownership.check()
            if tuple(row) != SCHEMAS[name]:
                raise ValueError(f"schema mismatch for {name}: {row.keys()}")
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    ownership.check(force=True)
    temporary.replace(destination)
    return {"records": count, "bytes": destination.stat().st_size,
            "sha256": file_sha256(destination)}


def run(args):
    priority = lower_priority()
    started = time.perf_counter()
    ownership = Ownership(args.output, args.agent)
    args.output.mkdir(parents=True, exist_ok=True)
    modules = []
    for module in ("main", "sdk"):
        nso = Nso(args.exefs / module, module)
        modules.append(nso)
        ownership.check(force=True)
        print(json.dumps({"stage": "nso_loaded", "module": module, "seconds": round(time.perf_counter() - started, 3),
                          "symbols": len(nso.symbols), "relocations": len(nso.relocations),
                          "relr_expanded": nso.relative_count}), flush=True)
    names, demangler = demangle_many(s["name"] for n in modules for s in n.symbols if s["name"])
    exports, pointers, unknown = relocate(modules)
    rtti, slots, diagnostics = extract_rtti(modules, exports, pointers)
    files = {}
    segments = []
    for nso in modules:
        for s in nso.segments:
            segments.append({"module": nso.module, "name": s["name"], "start": f"{nso.base + s['off']:x}",
                             "end": f"{nso.base + s['off'] + s['size']:x}", "perm": s["perm"]})
        if nso.bss_size:
            end = max(s["off"] + s["size"] for s in nso.segments)
            segments.append({"module": nso.module, "name": ".bss", "start": f"{nso.base + end:x}",
                             "end": f"{nso.base + end + nso.bss_size:x}", "perm": "rw-"})
    files["segments.jsonl"] = write_rows(args.output, "segments", segments, ownership)
    files["strings.jsonl"] = write_rows(args.output, "strings", (r for n in modules for r in iter_strings(n)), ownership)
    kinds = {0: "notype", 1: "object", 2: "function", 3: "section", 4: "file", 6: "tls", 10: "ifunc"}
    symbol_rows = []
    imported = collections.Counter()
    for nso in modules:
        for sym in nso.symbols:
            if not sym["name"]:
                continue
            if not sym["section"]:
                imported[nso.module] += 1
                continue
            symbol_rows.append({"addr": f"{nso.base + sym['value']:x}", "module": nso.module,
                                "mangled": sym["name"], "demangled": names[sym["name"]],
                                "kind": kinds.get(sym["info"] & 15, "unknown")})
    files["symbols.jsonl"] = write_rows(args.output, "symbols", symbol_rows, ownership)
    files["rtti.jsonl"] = write_rows(args.output, "rtti", rtti, ownership)
    files["vslots.jsonl"] = write_rows(args.output, "vslots", slots, ownership)
    found_anchor = None if args.check_string is None else False
    string_encodings = collections.Counter()
    with (args.output / "strings.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if args.check_string is not None:
                found_anchor |= row["text"] == args.check_string
            string_encodings[row["encoding"]] += 1
    sdk_nn = sum(row["module"] == "sdk" and row["kind"] == "function" and "nn::" in row["demangled"] for row in symbol_rows)
    if found_anchor is False or not sdk_nn:
        raise RuntimeError(f"P2 acceptance failed: condition={found_anchor}, sdk_nn={sdk_nn}")
    summary = {
        "package": "P2", "schema_version": 1, "files": files, "record_counts": {k: v["records"] for k, v in files.items()},
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "process_priority": priority,
        "inputs": [{"module": n.module, "base": f"{n.base:x}", "build_id": n.build_id,
                    "sha256": n.input_sha256, "nso_flags": n.flags, "symbols_total": len(n.symbols),
                    "imports_not_emitted_as_fake_addresses": imported[n.module], "relocations": len(n.relocations),
                    "relocation_kinds": dict(collections.Counter(str(r[1]) for r in n.relocations)),
                    "relr_expanded": n.relative_count} for n in modules],
        "checks": {"condition_string_found": found_anchor, "sdk_nn_demangled_functions": sdk_nn,
                   "string_encodings": dict(string_encodings), "nso_segment_sha256_verified_where_flagged": True},
        "rtti": diagnostics, "relocations_unresolved": dict(unknown), "demangler": demangler,
        "known_limitations": [
            "Strings are heuristically identified NUL-terminated printable runs in .rodata; minimum four Unicode characters.",
            "UTF-16LE candidates require coherent Unicode scripts, at least three letters/numbers and no overlap with UTF-8 strings. Binary false positives remain possible; mixed-script text may be missed.",
            "UTF-16BE is not extracted (guest AArch64 little endian); embedded NULs and nonterminated strings are not extracted.",
            "symbols.jsonl contains defined dynamic symbols only; unresolved imports do not receive invented addresses.",
            "RTTI needs a provable ABI typeinfo vptr resolved through relocations; stripped or custom RTTI and pointer-authenticated tables may be absent.",
            "vtable is the Itanium header address (offset-to-top), with slot zero at vtable+16; secondary groups emit separate rows.",
            "Vslots stop at the first unresolved, null or non-code pointer; relative 32-bit and custom vtables are not decoded.",
        ],
    }
    if not rtti:
        summary["known_limitations"].append("No Itanium RTTI objects could be proven from resolved ABI vptrs; no class names were guessed.")
    ownership.check(force=True)
    done_tmp = args.output / "DONE.json.tmp"
    done_tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ownership.check(force=True)
    done_tmp.replace(args.output / "DONE.json")
    print(json.dumps({"stage": "done", "seconds": summary["runtime_seconds"], "counts": summary["record_counts"],
                      "checks": summary["checks"], "rtti_objects": diagnostics["typeinfo_objects"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exefs", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--check-string", help="Optional exact string acceptance check, supplied outside tool source")
    run(parser.parse_args())
