"""Dedicated eboot-only adapter for the main-1.1.0 JSON-number fix.

plan is offline. All other operations require --console-ok and an explicit,
recorded handoff. Reuses the original queue/save/swap code; no assets/mod writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

BASE = "7d837a58acb83c5513ee3e2b3e6b3b5a5042379a92b7300ccc1e955148d2ac0f"
ROOT = Path(__file__).resolve().parents[2]
NAS = Path(r"\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\new-run-json-fix")


def load_adapter(config_path):
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if config["base_eboot_sha256"] != BASE:
        raise ValueError("Plan does not start from main-1.1.0")
    # This file is a release-specific adapter. It cannot accept an unpinned build.
    if len(config["candidate_eboot_sha256"]) != 64:
        raise ValueError("Final candidate hash is required")
    for relative, expected in config["installer_sources"].items():
        with (ROOT / relative).open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Installer dependency changed: " + relative)
    canonical_queue = Path(config["canonical_queue"])
    with canonical_queue.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != config["canonical_queue_sha256"]:
            raise ValueError("Canonical resource queue changed; inspect current rules before proceeding")
    spec = importlib.util.spec_from_file_location("newrun_existing_main_install", ROOT / "port/main-install/install-main.py")
    mm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mm)
    queue_spec = importlib.util.spec_from_file_location("newrun_canonical_queue", canonical_queue)
    queue = importlib.util.module_from_spec(queue_spec)
    queue_spec.loader.exec_module(queue)
    mm.queue = mm.m.queue = queue
    original_check = mm.m.Lease.check
    def check_turn(lease):
        original_check(lease)
        lease.board.check(mm.m.AGENT, lease.data["ticket"], lease.data["token"])
    mm.m.Lease.check = check_turn
    original_write = mm.write
    def write_with_resource_proof(path, record):
        path = Path(path)
        if path.name == "readiness.json":
            record["pc_validation"] = config["pc_validation"]
        if path.name == "receipt.json":
            record["baseline_handoff"] = mm.read(path.parent / "baseline-handoff.json")
        original_write(path, record)
    mm.write = mm.m.write = write_with_resource_proof
    package = Path(config["package"])
    target = package / "PPSA91762/eboot.bin"
    if mm.sha(target) != config["candidate_eboot_sha256"]:
        raise ValueError("Candidate executable differs from the plan")
    return config, mm


def configure(config, mm, args):
    m = mm.m
    package, base, target = Path(config["package"]), BASE, config["candidate_eboot_sha256"]
    if args.rollback_from:
        previous = Path(args.rollback_from)
        transaction = mm.read(previous / "transaction.json")
        if not transaction["installed_readback_verified"] or transaction["old_sha256"] != BASE or transaction["new_sha256"] != target:
            raise ValueError("Rollback evidence does not match this candidate")
        original = previous / "original/eboot.bin"
        if mm.sha(original) != BASE:
            raise ValueError("Original executable backup is not main-1.1.0")
        package = args.local / "rollback-package"
        destination = package / "PPSA91762/eboot.bin"
        if args.operation == "init" and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        if args.operation != "plan" and mm.sha(destination) != BASE:
            raise ValueError("Rollback package differs from the verified original")
        base, target = target, BASE
    agent = "codex-newrun-json-fix" + ("-rollback" if args.rollback_from else "")
    m.BASE, m.NEW, m.PACKAGE, m.AGENT = base, target, package, agent
    mm.BASE, mm.NEW, mm.PACKAGE, mm.AGENT = base, target, package, agent
    # R29's ready markers differ from the old native menu. Reuse its existing
    # compatibility adapter, without invoking isolate/assets/activate/shot.
    m.mount_at_menu = mm.mount
    return m


def init(args, config, mm, m):
    if (args.local / ".lease.json").exists() or (args.local / "nas-location.json").exists():
        raise FileExistsError("Use a new local state directory; never overwrite an earlier turn")
    out = NAS / ("gate-" + m.api.stamp() + ("-rollback" if args.rollback_from else ""))
    out.mkdir(parents=True, exist_ok=False)
    args.local.mkdir(parents=True, exist_ok=True)
    mm.write(args.local / "nas-location.json", {"evidence": str(out)})
    mm.write(out / "external-handoff.json", {"at": m.api.utc_now(), "from": "Tomer", "statement": args.handoff,
             "remote_close_authorized": True, "game_closed_observed": False, "save_success_not_claimed": True,
             "scope": "eboot only; launch original launcher only for fresh read-only all-runs backup; close only the verified owned menu"})
    job = {"console": m.api.HOST, "title_id": "PPSA91762", "name": "main-1.1.0 JSON-number fix, eboot only",
           "artifacts": [{"path": str(m.PACKAGE / "PPSA91762/eboot.bin"), "sha256": m.NEW, "remote_path": m.EBOOT}],
           "expected_base": [{"remote_path": m.EBOOT, "sha256": m.BASE}],
           "notes": "Preserve all assets/mods/RTL/config/saves. Backup every run by double read. Never restore a save."}
    mm.write(args.local / "job.json", job)
    board = m.queue.Board()
    result = board.enqueue(m.AGENT, "newrun-" + m.NEW[:16], args.local / "job.json")
    claim = board.claim(m.AGENT, ticket=result["ticket"])
    mm.write(args.local / ".lease.json", {"ticket": claim["ticket"], "token": claim["token"]})
    os.environ.update(CONSOLE_INSTALL_AGENT=m.AGENT, CONSOLE_INSTALL_TICKET=claim["ticket"], CONSOLE_INSTALL_TOKEN=claim["token"])
    with m.Lease(args.local) as lease:
        m.idle()
        handoff = mm.read(out / "external-handoff.json")
        handoff["game_closed_observed"] = True
        handoff["game_closed_observed_at"] = m.api.utc_now()
        mm.write(out / "external-handoff.json", handoff)
        c = m.api.Console()
        try:
            first = m.bounded_file(c, m.EBOOT, out / "original/eboot.bin", lease)
            if first["sha256"] != m.BASE or c.sha256(m.EBOOT) != m.BASE:
                raise RuntimeError("Current executable differs: stop and reconcile; do not repin")
            mm.write(out / "initial-probe.json", {"at": m.api.utc_now(), "base_sha256": m.BASE,
                     "readback_path": first["path"], "second_readback_verified": True})
        finally:
            c.close()
    mm.emit({"operation": "init", "evidence": str(out), "ticket": claim["ticket"], "token_printed": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "init", "backup", "install", "complete"))
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("CANDIDATE.json"))
    parser.add_argument("--local", type=Path, required=True)
    parser.add_argument("--handoff", help="Only after Tomer coordinates: saved/closed and owned backup-menu launch/close permitted")
    parser.add_argument("--console-ok", action="store_true")
    parser.add_argument("--rollback-from", type=Path, help="Prior installation evidence folder; new state/backup/lease required")
    parser.add_argument("--resume-menu-identity", type=Path, help="backup only: fresh user-opened original menu identity, with pinned fresh startup log")
    args = parser.parse_args()
    args.local = args.local.resolve()
    if args.operation != "plan" and not args.console_ok:
        parser.error("Console operations require --console-ok and current coordination from Tomer")
    if args.operation == "init" and not args.handoff:
        parser.error("init requires the actual user handoff; elapsed time is not authorization")
    if args.resume_menu_identity and args.operation != "backup":
        parser.error("--resume-menu-identity is only valid for backup")
    config, mm = load_adapter(args.config)
    m = configure(config, mm, args)
    if args.operation == "plan":
        print(json.dumps({"base": m.BASE, "target": m.NEW, "eboot_only": True, "console_access": False,
              "package": str(m.PACKAGE), "steps": ["init", "backup", "install", "complete"],
              "backup_launches_only_owned_menu": True, "fresh_all_runs_double_read": True,
              "rollback": "same adapter --rollback-from PRIOR_EVIDENCE --local NEW_STATE; fresh handoff and backup",
              "hardware_fix_verified": False}, indent=2))
        return
    if args.operation == "init":
        init(args, config, mm, m)
        return
    out = Path(mm.read(args.local / "nas-location.json")["evidence"])
    held = mm.read(args.local / ".lease.json")
    os.environ.update(CONSOLE_INSTALL_AGENT=m.AGENT, CONSOLE_INSTALL_TICKET=held["ticket"], CONSOLE_INSTALL_TOKEN=held["token"])
    handoff = mm.read(out / "external-handoff.json")
    if not handoff["game_closed_observed"] or not handoff["remote_close_authorized"]:
        raise RuntimeError("No coordinated game-closed handoff")
    resume = None
    if args.resume_menu_identity:
        resume = mm.read(args.resume_menu_identity)
        initial = mm.read(out / "initial-probe.json")
        observed_at = datetime.fromisoformat(resume["at"])
        age = (datetime.now(timezone.utc) - observed_at).total_seconds()
        if age < 0 or age > 300 or observed_at < datetime.fromisoformat(initial["at"]):
            raise RuntimeError("Menu identity must be fresh and observed after this installation's initial probe")
        if resume["eboot_sha256"] != m.BASE or resume.get("menu_verified") is not True or not resume.get("run"):
            raise RuntimeError("Not the identified original menu and active run")
        log_path = Path(resume["startup_log"])
        if mm.sha(log_path) != resume["startup_log_sha256"]:
            raise RuntimeError("Fresh original-menu log changed")
        log = log_path.read_text(encoding="utf-8", errors="replace")
        if not all(marker in log for marker in ("main reached", "[za-observer-r17] opt-in", "run storage ready", "[ui-v2] launcher canvas")) or "za-native-fault" in log:
            raise RuntimeError("Fresh log does not prove a healthy original launcher menu")
    if args.operation == "install":
        saved = mm.read(out / "save-backup-manifest.json")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(saved["at"])).total_seconds()
        if age < 0 or age > 300:
            raise RuntimeError("All-runs backup must have completed within the last five minutes")
    with m.Lease(args.local) as lease:
        c = m.api.Console()
        try:
            if args.operation == "backup":
                # Existing backup validates live PID/session/title/run and exact
                # executable again. No sandbox cleanup or observer command here.
                m.backup(c, lease, out, resume_identity=resume)
            else:
                {"install": m.install, "complete": m.complete}[args.operation](c, lease, out)
        except Exception as error:
            mm.write(out / ("error-" + args.operation + "-" + m.api.stamp() + ".json"),
                     {"at": m.api.utc_now(), "operation": args.operation, "error": str(error)})
            raise
        finally:
            c.close()


if __name__ == "__main__":
    main()
