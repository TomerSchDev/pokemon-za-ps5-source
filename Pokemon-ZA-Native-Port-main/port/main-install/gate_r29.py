"""Run a release installer's steps on a console whose eboots are all r29-ui based (main 1.x).

install-r28b.mount_at_menu waits for the OLD native menu's klog line, which the r29-ui launcher never prints; the
installers' backup/isolate steps call it directly. This wrapper points it at install-main.mount (same logic, the r29-ui
launcher's ready lines) before running the requested step of the given installer.

    py -3 -X utf8 gate_r29.py <installer.py> <step> --local DIR
"""
import importlib.util, sys
from pathlib import Path

installer, step = Path(sys.argv[1]).resolve(), sys.argv[2]
spec = importlib.util.spec_from_file_location("gate_installer", installer)
i = importlib.util.module_from_spec(spec); sys.modules["gate_installer"] = i
sys.argv = [str(installer), step] + sys.argv[3:]
source = installer.read_text(encoding="utf-8")
main_at = source.index('\nif __name__ == "__main__":')
exec(compile(source[:main_at], str(installer), "exec"), i.__dict__)          # definitions only
mm = i.__dict__.get("mm") or i                                                   # install-main module
i.m.mount_at_menu = lambda c, lease, out, expected, label: mm.mount(c, lease, out, expected, label)
i.__dict__["__name__"] = "__main__"
exec(compile(source[main_at:], str(installer), "exec"), i.__dict__)             # the installer's own dispatch
