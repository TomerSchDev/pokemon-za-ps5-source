"""Bounded condition-vtable metadata using the existing P2 NSO decoder only.

No console, game/save writes or disassembly. Heavy NSO decompression requires
the canonical shared PC turn. Output contains addresses and provenance only.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--nso", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--got", action="append", type=lambda x: int(x, 16), default=[])
    p.add_argument("--got-window", action="append", default=[], help="HEX_GOT:QWORDS, bounded per-target override")
    p.add_argument("--qwords", type=int, default=36)
    p.add_argument("--bytes", action="append", default=[], help="Bounded numeric jump-table window: HEX_ADDRESS:LENGTH")
    a = p.parse_args()
    got_windows = [(got, a.qwords) for got in a.got]
    for spec in a.got_window:
        got, count = spec.split(":")
        got_windows.append((int(got, 16), int(count, 0)))
    if not 1 <= len(got_windows) <= 8 or not all(1 <= count <= 96 for _, count in got_windows):
        p.error("At most 8 GOT addresses and 96 qwords per target")
    windows = []
    for spec in a.bytes:
        address, length = spec.split(":")
        address, length = int(address, 16), int(length, 0)
        if not 1 <= length <= 128 or len(windows) >= 8:
            p.error("At most eight byte windows, each <=128 bytes")
        windows.append((address, length))
    queue = module("canonical_pc_queue", a.repo / "tools/console-install-queue/console_queue.py")
    agent, ticket, token = [os.environ.get("PC_TEST_" + x, "") for x in ("AGENT", "TICKET", "TOKEN")]
    if not all((agent, ticket, token)):
        p.error("A canonical PC resource turn is required")
    board = queue.Board(resource="pc")
    board.check(agent, ticket, token)
    P2 = module("existing_p2_nso", a.repo / "tools/za-atlas/P2/extract.py")
    P2.lower_priority()
    started = time.monotonic()
    nso = P2.Nso(a.nso, "main")
    if nso.input_sha256 != "2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9":
        raise ValueError("NSO differs from the atlas P2 input pin; do not attribute methods to this build")
    if nso.build_id != "b1f12fd919eae86ab8a978317677e64bce443d1f":
        raise ValueError("Unexpected main Build ID")
    board.heartbeat(agent, ticket, token)
    _, pointers, unknown = P2.relocate([nso])
    result = {"schema": "za-condition-vtable-peek-1", "input_sha256": nso.input_sha256,
              "build_id": nso.build_id, "decoder": str(a.repo / "tools/za-atlas/P2/extract.py"),
              "relocations": len(nso.relocations), "unresolved": dict(unknown), "tables": [], "byte_windows": []}
    for address, length in windows:
        if not nso.base <= address <= nso.base + nso.size - length:
            raise ValueError("Byte window outside main")
        off = address - nso.base
        result["byte_windows"].append({"address": hex(address), "bytes": list(nso.image[off:off+length])})
    for got, count in got_windows:
        if not nso.base <= got < nso.base + nso.size:
            raise ValueError("GOT address outside main")
        target = pointers.get(got)
        row = {"got": hex(got), "relocated_target": hex(target) if target is not None else None, "qwords": []}
        if target is not None and nso.base <= target < nso.base + nso.size:
            for index in range(count):
                addr = target + 8 * index
                if addr + 8 > nso.base + nso.size:
                    break
                value = pointers.get(addr)
                row["qwords"].append({"offset": hex(index * 8), "address": hex(addr),
                                     "relocated": hex(value) if value is not None else None,
                                     "raw": hex(nso.u64(addr - nso.base))})
        result["tables"].append(row)
    result["elapsed_seconds"] = time.monotonic() - started
    board.check(agent, ticket, token)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.out.exists():
        raise FileExistsError(a.out)
    a.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(a.out), "tables": len(result["tables"]), "seconds": result["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
