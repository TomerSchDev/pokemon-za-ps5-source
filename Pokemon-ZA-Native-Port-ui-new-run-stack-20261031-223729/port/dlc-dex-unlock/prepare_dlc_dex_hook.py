"""Prepare the one audited 2.0.2 DLC Dex hook. Inputs are never edited."""
from pathlib import Path
import argparse
import hashlib
import json
import re

REVISION = "dlc-dex-unlock-r1"
BUILD_ID = "b1f12fd919eae86ab8a978317677e64bce443d1f"
UNIT = "main_287.c"
FUNCTION = "f_70008d4178"
SOURCE_SHA256 = "1c8e0186dd2b993060f63d1e381f9765fed756d0e0f71031007c6a2f91e7f442"
ANCHOR = ("    c->x[30] = 0x70008d41bcull; f_70000393b8(c);\n"
          "    c->x[19] = (uint32_t)(0u | (uint32_t)c->x[0]);\n")
REPLACEMENT = ("    c->x[30] = 0x70008d41bcull; f_70000393b8(c);\n"
               "    /* dlc-dex-unlock-r1: no work when already enabled; otherwise native SetFlag + readback. */\n"
               "    if ((uint32_t)c->x[0] == 0) {\n"
               "        extern unsigned za_dlc_dex_unlock_pump(Cpu *);\n"
               "        c->x[0] = za_dlc_dex_unlock_pump(c);\n"
               "    }\n"
               "    c->x[19] = (uint32_t)(0u | (uint32_t)c->x[0]);\n")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def function_body(text, name):
    pattern = re.compile(r"^void (f_[0-9a-f]+)\(Cpu \*c\) \{", re.M)
    starts = list(pattern.finditer(text))
    for i, m in enumerate(starts):
        if m[1] == name:
            return text[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
    raise ValueError("missing function: " + name)

def patch_text(text):
    if text.count(ANCHOR) != 1:
        raise ValueError("hook anchor differs or is not unique")
    body = function_body(text, FUNCTION)
    if body.count(ANCHOR) != 1:
        raise ValueError("anchor outside audited function")
    for needle in ("0x200ull; uint64_t v = LD32(ea)", "c->x[0] + 0x328ull",
                   "f_70000393b8(c)", "c->x[0] + 0x880ull", "L_70008d4238:;"):
        if body.count(needle) != 1:
            raise ValueError("audited getter no longer matches: " + needle)
    return text.replace(ANCHOR, REPLACEMENT)

def prepare(aot, nso, out):
    aot, nso, out = Path(aot), Path(nso), Path(out)
    source = (aot / "main" / UNIT) if (aot / "main" / UNIT).is_file() else aot / UNIT
    raw = source.read_bytes()
    if sha(raw) != SOURCE_SHA256:
        raise ValueError("unapproved source SHA-256: " + UNIT)
    image = nso.read_bytes()
    if image[:4] != b"NSO0" or image[0x40:0x60].rstrip(b"\0").hex() != BUILD_ID:
        raise ValueError("unapproved game NSO/build ID")
    encoded = patch_text(raw.decode("utf-8").replace("\r\n", "\n")).encode()
    target = out / UNIT
    if target.resolve() == source.resolve():
        raise ValueError("output aliases input")
    if target.exists() and target.read_bytes() != encoded:
        raise ValueError("refusing to overwrite a different output")
    report = dict(revision=REVISION, build_id=BUILD_ID, console_tested=False,
                  unit=UNIT, function=FUNCTION, original_sha256=sha(raw), patched_sha256=sha(encoded),
                  new_object="za_dlc_dex_unlock.o", extern="za_dlc_dex_unlock_pump",
                  target_flag="FLAG_DLC_DEX_ENABLE", target_hash="58e63b00d271631f",
                  native_setter="f_70009d0114", native_getter="f_70000393b8")
    out.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    (out / "dlc-dex-hook-manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aot", required=True, type=Path)
    p.add_argument("--nso", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(prepare(args.aot, args.nso, args.out), indent=2))
