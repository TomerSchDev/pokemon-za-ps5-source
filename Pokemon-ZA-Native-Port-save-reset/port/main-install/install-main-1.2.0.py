"""Console gate for the main-1.2.0 candidate (main-1.1.0 + save slots: slot menu, delete, slot.zrs on every save) on
PPSA91762, through the shared queue. PREPARED, NOT RUN: the coordinator runs it with Tomer (game saved and closed).

Starting point: the console as the 1.1.0 gate (ticket 9) left it: eboot 7d837a58 (main-1.1.0), mods/0-hebrew linked to
app0/hebrew-rtl-r6-e787deb75759, side-branch mods renamed _NAME.

A thin wrapper over install-main.py (lease, all-runs double-read save backup, staged .new -> readback -> rename -> readback
eboot swap keeping eboot.bin.before-r28b-<tag>, randomizer-assets staged + read back with the old folder kept as
randomizer-assets.before-<release>-<tag>, r29-ui launcher mount, observer screenshots, owned close). Differences:
  BASE   = 7d837a58 (main-1.1.0, installed now); NEW = the candidate eboot from the package's SHA256SUMS.json.
  assets = the package's randomizer-assets: 1.1.0's 174 v3 files (unchanged) + slot-names.json.
  mods   are NOT touched: no isolate step in the order; 0-hebrew is never in SIDE_MODS (asserted); `shot` requires the
         klog line "[fs] mod: 0-hebrew" (the Hebrew layer still loads) and counts the "[slot]" writer lines.
Run every step through the r29-ui gate wrapper (backup mounts the CURRENT launcher, which is r29-ui based):

  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py init --local DIR --handoff "<Tomer>"
  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py backup   --local DIR
  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py assets   --local DIR
  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py install  --local DIR
  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py shot     --local DIR
  py -3 -X utf8 port/main-install/gate_r29.py port/main-install/install-main-1.2.0.py complete --local DIR

Rollback: eboot.bin.before-r28b-<tag> (= 1.1.0, 7d837a58) back to eboot.bin; randomizer-assets.before-main-1.2.0-<tag>
back to randomizer-assets (1.1.0 ignores slot-names.json and slot.zrs anyway). Saves are never restored or written;
slot.zrs files are display data next to each run.
"""
from __future__ import annotations
import argparse, importlib.util, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("install_main", HERE / "install-main.py")
mm = importlib.util.module_from_spec(spec)   # named mm: gate_r29.py patches m.mount_at_menu -> mm.mount
spec.loader.exec_module(mm)
m = mm.m

PACKAGE_SOURCE = Path(os.environ.get("ZA_120_PACKAGE",
                      r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\main-1.2.0-candidate-pkg-20261031-01"))
sums = json.loads((PACKAGE_SOURCE / "SHA256SUMS.json").read_text(encoding="utf-8"))
assert "randomizer-assets/slot-names.json" in sums, "the package lacks slot-names.json"
EXPECTED_NEW = "@@NEW@@"
assert sums["eboot.bin"] == EXPECTED_NEW, "package eboot is not the built candidate"

mm.RELEASE = "main-1.2.0"
mm.SOURCE = PACKAGE_SOURCE
ARTIFACTS = Path(os.environ.get("ZA_ARTIFACTS", r"C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port\artifacts"))
mm.PACKAGE = ARTIFACTS / "main-1.2.0-install-r1"          # made by init from PACKAGE_SOURCE (eboot + randomizer-assets)
mm.BASE = "7d837a58acb83c5513ee3e2b3e6b3b5a5042379a92b7300ccc1e955148d2ac0f"   # main-1.1.0 (installed by its gate, ticket 9)
mm.NEW = EXPECTED_NEW
mm.SIDE_MODS = ["hebrew", "00-console-fifty-20261031-r1", "00-0-console-fifty-20261031-r1", "000-rowlet-pilot-r1"]
assert "0-hebrew" not in mm.SIDE_MODS, "the Hebrew layer must stay linked"
mm.AGENT = "claude-main-1.2.0"
m.BASE, m.NEW, m.PACKAGE, m.AGENT = mm.BASE, mm.NEW, mm.PACKAGE, mm.AGENT


def shot(c, lease, out):
    """install-main shot, then: the Hebrew layer still loaded, and what the slot writer logged."""
    mm.shot(c, lease, out)
    log = (out / "main-shot.klog.log").read_text(encoding="utf-8", errors="replace")
    slot_lines = [l for l in log.splitlines() if "[slot]" in l]
    check = {"at": mm.api.utc_now(), "hebrew_layer_loaded": "[fs] mod: 0-hebrew" in log,
             "slot_writer_lines": len(slot_lines), "slot_writer_sample": slot_lines[:10]}
    mm.write(out / "main-1.2.0-checks.json", check)
    mm.emit({"stage": "checks", **check})
    if not check["hebrew_layer_loaded"]:
        raise RuntimeError("klog has no '[fs] mod: 0-hebrew': the Hebrew layer did not load")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("operation", choices=("init", "backup", "assets", "install", "shot", "complete"))
    p.add_argument("--local", required=True, type=Path)
    p.add_argument("--handoff")
    a = p.parse_args()
    local = a.local.resolve()
    if a.operation == "init":
        if not a.handoff:
            p.error("init needs --handoff")
        mm.init(local, a.handoff)
        sys.exit(0)
    out = Path(mm.read(local / "nas-location.json")["evidence"])
    ops = {"backup": m.backup, "assets": mm.assets, "install": m.install, "shot": shot, "complete": m.complete}
    with m.Lease(local) as lease:
        c = mm.api.Console()
        try:
            ops[a.operation](c, lease, out)
        except Exception as error:
            mm.write(out / ("error-" + a.operation + "-" + mm.api.stamp() + ".json"),
                     {"at": mm.api.utc_now(), "type": type(error).__name__, "error": str(error), "operation": a.operation})
            raise
        finally:
            c.close()
