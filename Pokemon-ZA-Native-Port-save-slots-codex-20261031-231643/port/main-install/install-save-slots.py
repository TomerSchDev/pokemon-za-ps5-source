"""Install the save-slots candidate (main-1.0.0 + save-slot menu, delete, slot.zrs writer) on PPSA91762 for its
console gate, through the shared queue. PREPARED, NOT RUN: the coordinator runs the gate with Tomer.

A thin wrapper over install-main.py (same lease, all-runs save backup, staged/readback/rename eboot swap,
randomizer-assets staged + read back with the old folder kept, owned close). Only the release constants differ:
  BASE = main-1.0.0's eboot (51b7e65b..., what the 1.0.0 gate installed), NEW = the candidate's eboot from the
  package's SHA256SUMS.json, SOURCE = the package made by port/ui-v2/tools/build-save-slots.py --package.
Order: init -> backup -> assets -> install -> shot -> complete   (isolate only if side-branch mods are back; pushrun
is not needed: the new launcher creates runs itself, and the gate run made by 1.0.0 stays listed as supported).
Rollback: eboot.bin.before-r28b-<tag> (= main-1.0.0) and randomizer-assets.before-<release>-<tag>. Saves are never
restored or written. slot.zrs files written by the candidate are display data only; 1.0.0 ignores them.

  py -3 port/main-install/install-save-slots.py init --local <dir> --handoff "<Tomer's statement>"
  py -3 port/main-install/install-save-slots.py backup|assets|install|shot|complete --local <dir>
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("install_main", HERE / "install-main.py")
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)
m = im.m

PACKAGE_SOURCE = Path(r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\save-slots-pkg-20261031-03")
sums = json.loads((PACKAGE_SOURCE / "SHA256SUMS.json").read_text(encoding="utf-8"))
assert "randomizer-assets/slot-names.json" in sums, "the package lacks slot-names.json"

im.RELEASE = "save-slots-candidate-20261031"
im.SOURCE = PACKAGE_SOURCE
im.PACKAGE = ROOT / "artifacts/save-slots-install-20261031-r1"
im.BASE = "51b7e65b0bd930bfe7ede0127d56736ee43d8487310ebff6337c92e11b3e1ab1"   # main-1.0.0 (installed by its gate)
im.NEW = sums["eboot.bin"]
im.SIDE_MODS = ["hebrew", "00-console-fifty-20261031-r1", "00-0-console-fifty-20261031-r1", "000-rowlet-pilot-r1"]
im.AGENT = "claude-save-slots"
m.BASE, m.NEW, m.PACKAGE, m.AGENT = im.BASE, im.NEW, im.PACKAGE, im.AGENT

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("operation", choices=("init", "backup", "isolate", "assets", "install", "shot", "complete"))
    p.add_argument("--local", required=True, type=Path)
    p.add_argument("--handoff")
    p.add_argument("--restore", action="store_true", help="isolate: rename _NAME back to NAME")
    a = p.parse_args()
    local = a.local.resolve()
    if a.operation == "init":
        if not a.handoff:
            p.error("init needs --handoff")
        im.init(local, a.handoff)
        sys.exit(0)
    out = Path(im.read(local / "nas-location.json")["evidence"])
    ops = {"backup": m.backup, "isolate": lambda c, l, o: im.isolate(c, l, o, a.restore), "assets": im.assets,
           "install": m.install, "shot": im.shot, "complete": m.complete}
    with m.Lease(local) as lease:
        c = im.api.Console()
        try:
            ops[a.operation](c, lease, out)
        except Exception as error:
            im.write(out / ("error-" + a.operation + "-" + im.api.stamp() + ".json"),
                     {"at": im.api.utc_now(), "type": type(error).__name__, "error": str(error), "operation": a.operation})
            raise
        finally:
            c.close()
