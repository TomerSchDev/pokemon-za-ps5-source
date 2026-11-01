"""Extract actual generated functions to a PRIVATE temporary host-test directory."""
from pathlib import Path
import importlib.util
import sys

own = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", own / "prepare_dlc_dex_hook.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
aot, patched, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
parts = []
for unit, fn, rename in (("main_012.c", "f_70000393b8", None),
                         ("main_1058.c", "f_7002ab3298", None),
                         ("main_306.c", "f_70009d0114", "native_setter")):
    text = (aot / "main" / unit).read_text()
    body = p.function_body(text, fn)
    parts.append(body.replace(fn, rename) if rename else body)
for source, rename in ((aot / "main" / p.UNIT, "original_dex_getter"),
                       (patched / p.UNIT, "patched_dex_getter")):
    parts.append(p.function_body(source.read_text(), p.FUNCTION).replace(p.FUNCTION, rename))
(out / "actual_functions.inc").write_text("\n".join(parts))
