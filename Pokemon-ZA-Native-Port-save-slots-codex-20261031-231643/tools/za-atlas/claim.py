#!/usr/bin/env python3
"""Package claims for the parallel za-atlas build (analysis/CODE-ATLAS-PROMPT-HE.md).

Every agent gets the same prompt and asks this script for work:
  claim.py next --agent ID                    claim a package: P1,P3,P2,P4,P5 first, P6 once all five are done
  claim.py heartbeat --agent ID --package P   keep the claim alive (at least every 15 minutes)
  claim.py done --agent ID --package P        after parts/<P>/DONE.json is written
  claim.py release --agent ID --package P     give a package back unfinished
  claim.py status                             who holds what

A claim is a directory made with mkdir, which exactly one process can win. A claim whose heartbeat is older than
--stale-min minutes and has no done.json may be taken over: one agent wins a takeover directory named after the stale
claim's id, then moves the old claim and its unfinished parts aside, so the old owner's next heartbeat reports the loss
(exit code 3) and it must stop writing. Every command prints one JSON line.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ORDER = ["P1", "P3", "P2", "P4", "P5"]  # the heavy parsers first
FINAL = "P6"
DEFAULT_ROOT = Path(r"C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\za-atlas-data")
LOST = 3


def stamp():
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def aside(path, tag):
    """Rename path to a unique sibling; False if another agent moved it first."""
    try:
        os.rename(path, path.with_name(f"{path.name}.{tag}-{stamp()}-{uuid.uuid4().hex[:6]}"))
        return True
    except OSError:
        return False


class Board:
    def __init__(self, root, stale_min):
        self.claims = Path(root) / "claims"
        self.parts = Path(root) / "parts"
        self.stale = stale_min * 60
        self.claims.mkdir(parents=True, exist_ok=True)
        self.parts.mkdir(parents=True, exist_ok=True)

    def cdir(self, p):
        return self.claims / p

    def owner(self, p):
        try:
            return json.loads((self.cdir(p) / "owner.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def done(self, p):
        return (self.cdir(p) / "done.json").exists()

    def age(self, p):
        for f in (self.cdir(p) / "heartbeat", self.cdir(p)):  # (a claim mid-creation has no heartbeat yet)
            try:
                return time.time() - f.stat().st_mtime
            except OSError:
                pass
        return None

    def write(self, path, obj):
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(obj), encoding="utf-8")
        os.replace(tmp, path)

    def try_claim(self, p, agent):
        d = self.cdir(p)
        if d.exists():
            age = self.age(p)
            if self.done(p) or age is None or age < self.stale:
                return False
            gen = self.owner(p).get("claim_id") or f"noowner-{int(d.stat().st_mtime)}"
            try:
                os.mkdir(self.claims / f"{p}.takeover-{gen}")  # one winner per stale claim
            except OSError:
                return False
            if not aside(d, "stale"):
                return False
        part = self.parts / p
        if part.exists() and not (part / "DONE.json").exists() and any(part.iterdir()):
            aside(part, "stale")  # unfinished output of an earlier owner: start clean
        try:
            os.mkdir(d)
        except OSError:
            return False
        self.write(d / "owner.json", {"agent": agent, "claim_id": uuid.uuid4().hex, "claimed_at": stamp()})
        (d / "heartbeat").write_text(stamp(), encoding="utf-8")
        part.mkdir(parents=True, exist_ok=True)
        return True

    def held(self, agent):
        return [p for p in ORDER + [FINAL] if self.cdir(p).exists() and not self.done(p)
                and self.owner(p).get("agent") == agent]

    def next(self, agent):
        mine = self.held(agent)
        if mine:
            return {"package": mine[0], "note": "you already hold this package; finish it first"}
        for p in ORDER:
            if self.try_claim(p, agent):
                return {"package": p}
        if all(self.done(p) for p in ORDER):
            if self.done(FINAL):
                return {"package": None, "reason": "all packages are done"}
            if self.try_claim(FINAL, agent):
                return {"package": FINAL}
            return {"package": None, "reason": "P6 is held by another agent; end your session"}
        busy = [p for p in ORDER if not self.done(p)]
        return {"package": None, "reason": f"nothing free ({', '.join(busy)} in progress); end your session - "
                                           "whoever finishes the last of P1-P5 runs P6"}

    def owned_or_lost(self, p, agent):
        return None if self.owner(p).get("agent") == agent else \
            {"package": p, "lost": True, "reason": "this claim is no longer yours; stop writing to it"}

    def heartbeat(self, p, agent):
        lost = self.owned_or_lost(p, agent)
        if lost:
            return lost
        (self.cdir(p) / "heartbeat").write_text(stamp(), encoding="utf-8")
        return {"package": p, "ok": True}

    def finish(self, p, agent):
        lost = self.owned_or_lost(p, agent)
        if lost:
            return lost
        if not (self.parts / p / "DONE.json").exists():
            return {"package": p, "ok": False, "reason": f"write parts/{p}/DONE.json first"}
        self.write(self.cdir(p) / "done.json", {"agent": agent, "done_at": stamp()})
        return {"package": p, "ok": True, "next": "run: claim.py next --agent " + agent}

    def release(self, p, agent):
        lost = self.owned_or_lost(p, agent)
        if lost:
            return lost
        return {"package": p, "ok": aside(self.cdir(p), "released")}

    def status(self):
        rows = []
        for p in ORDER + [FINAL]:
            if not self.cdir(p).exists():
                rows.append({"package": p, "state": "free"})
                continue
            age = self.age(p)
            state = "done" if self.done(p) else ("stale" if age is not None and age >= self.stale else "claimed")
            rows.append({"package": p, "state": state, "agent": self.owner(p).get("agent"),
                         "heartbeat_min_ago": None if age is None else round(age / 60, 1)})
        return {"packages": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["next", "heartbeat", "done", "release", "status"])
    ap.add_argument("--agent")
    ap.add_argument("--package", choices=ORDER + [FINAL])
    ap.add_argument("--root", default=os.environ.get("ZA_ATLAS_DATA", str(DEFAULT_ROOT)))
    ap.add_argument("--stale-min", type=float, default=45)
    a = ap.parse_args()
    if a.command != "status" and not a.agent:
        ap.error("--agent is required")
    if a.command in ("heartbeat", "done", "release") and not a.package:
        ap.error("--package is required")
    b = Board(a.root, a.stale_min)
    out = {"next": lambda: b.next(a.agent),
           "heartbeat": lambda: b.heartbeat(a.package, a.agent),
           "done": lambda: b.finish(a.package, a.agent),
           "release": lambda: b.release(a.package, a.agent),
           "status": b.status}[a.command]()
    print(json.dumps(out))
    return LOST if out.get("lost") else 0


if __name__ == "__main__":
    sys.exit(main())
