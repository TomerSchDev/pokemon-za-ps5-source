#!/usr/bin/env python3
"""Cooperative FIFO turns for PC testing and the console. Never contacts hardware.

All writers share one atomic mkdir mutex and one checksummed, atomically replaced
state file. Expired leases and abandoned metadata mutexes are never stolen.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import socket
import sys
import time
import uuid

CONSOLE = "192.168.1.135"
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "console-install-state"
PC_ROOT = DEFAULT_ROOT.with_name("pc-test-state")
YIELD_SECONDS = {"pc": 300, "console": 600}
MAIN_TITLE = "PPSA91762"
PROTECTED_TITLES = {MAIN_TITLE, "PPSA91761"}
HEX = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,120}$")


class QueueError(Exception):
    code = 2


class LostLease(QueueError):
    code = 3


class Busy(QueueError):
    code = 4


class RecoveryRequired(QueueError):
    code = 5


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def retry_sharing(operation, seconds=3):
    """Retry transient Windows readers, never ownership/ACL errors or stale locks."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return operation()
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) not in (32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def local_path(value, base=None):
    text = str(value)
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", text):
        text = "/mnt/" + text[0].lower() + "/" + text[3:].replace("\\", "/")
    elif os.name == "nt" and re.match(r"^/mnt/[a-zA-Z]/", text):
        text = text[5].upper() + ":/" + text[7:]
    path = Path(text)
    return (path if path.is_absolute() else (base or Path.cwd()) / path).resolve()


def shared_path(path):
    """Keep shared NTFS paths stable between Windows and WSL clients."""
    text = str(Path(path).resolve()).replace("\\", "/")
    if re.match(r"^/mnt/[a-zA-Z]/", text):
        return text[5].upper() + ":/" + text[7:]
    return text


def valid_hash(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise QueueError("a SHA-256 must contain exactly 64 hex digits")
    return value.lower()


def valid_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise QueueError("invalid agent/request ID")
    return value


def remote_path(value):
    if (not isinstance(value, str) or not value.startswith("/") or "\\" in value
            or any(c in value for c in ("\r", "\n", "\0"))
            or ".." in PurePosixPath(value).parts or str(PurePosixPath(value)) != value
            or value.startswith("//")):
        raise QueueError("remote_path must be a canonical absolute POSIX path")
    return value


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise QueueError(f"cannot read JSON: {path}: {exc}") from exc


def read_json_proof(path):
    """The recorded digest covers exactly the bytes whose claims were checked."""
    try:
        raw = Path(path).read_bytes()
        return json.loads(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as exc:
        raise QueueError(f"cannot read evidence JSON: {path}: {exc}") from exc


def evidence_file(record, base):
    if not isinstance(record, dict) or "path" not in record:
        raise QueueError("evidence requires path and sha256")
    path = local_path(record["path"], base)
    expected = valid_hash(record.get("sha256"))
    if not path.is_file() or digest(path) != expected:
        raise QueueError(f"evidence file missing or hash mismatch: {path}")
    return {"path": shared_path(path), "sha256": expected}


def save_backup_waiver(section, base, row):
    """Record Tomer's explicit, scoped instruction without claiming a backup exists."""
    if not isinstance(section, dict) or section.get("waived_by") != "Tomer" or not isinstance(section.get("reason"), str) or not section["reason"].strip():
        raise QueueError("save-backup waiver requires Tomer and a reason")
    if any(section.get(flag) is True for flag in ("fresh", "all_runs", "readback_verified")):
        raise QueueError("a save-backup waiver cannot claim a verified backup")
    reference = evidence_file(section.get("approval_evidence"), base)
    approval, approval_hash = read_json_proof(local_path(reference["path"], base))
    if approval_hash != reference["sha256"]:
        raise QueueError("save-backup approval changed while reading")
    if not isinstance(approval, dict) or approval.get("source") != "user_message" or approval.get("approved_by") != "Tomer" or approval.get("action") != "waive_save_backup":
        raise QueueError("save-backup waiver requires Tomer's explicit user instruction")
    if not isinstance(approval.get("quote"), str) or not approval["quote"].strip():
        raise QueueError("save-backup waiver requires the verbatim user quote")
    if approval.get("console") != CONSOLE or approval.get("ticket") != row["ticket"] or approval.get("title_id") != row["job"]["title_id"]:
        raise QueueError("save-backup approval scope differs from this console/ticket/title")
    return reference


def normalized_job(path):
    path = local_path(path)
    job = read_json(path)
    if job.get("console") != CONSOLE:
        raise QueueError(f"this queue is only for console {CONSOLE}")
    if not re.fullmatch(r"PPSA\d{5}", job.get("title_id", "")):
        raise QueueError("title_id must be PPSA plus five digits")
    if not isinstance(job.get("name"), str) or not job["name"].strip():
        raise QueueError("job name is required")
    artifacts = []
    for item in job.get("artifacts", []):
        result = evidence_file(item, path.parent)
        result["remote_path"] = remote_path(item.get("remote_path"))
        result["bytes"] = local_path(result["path"]).stat().st_size
        artifacts.append(result)
    if not artifacts or len({r["remote_path"] for r in artifacts}) != len(artifacts):
        raise QueueError("artifacts must be nonempty with unique remote paths")
    bases = [{"remote_path": remote_path(item.get("remote_path")), "sha256": valid_hash(item.get("sha256"))}
             for item in job.get("expected_base", [])]
    if (not bases and job.get("deployment", {}).get("mode") != "side_app") or len({r["remote_path"] for r in bases}) != len(bases):
        raise QueueError("expected_base must be nonempty with unique remote paths; unknown bases are not installable")
    dependencies = job.get("external_dependencies", [])
    if not isinstance(dependencies, list) or len(dependencies) > 20 or any(not isinstance(r, dict) for r in dependencies):
        raise QueueError("external_dependencies must be a list of at most 20 records")
    deployment = dict(job.get("deployment", {}))
    if "test_report" in deployment:
        deployment["test_report"] = evidence_file(deployment["test_report"], path.parent)
    return {"console": CONSOLE, "title_id": job["title_id"], "name": job["name"],
            "deployment": deployment,
            "artifacts": artifacts, "expected_base": bases,
            "requirements": ["external_console_handoff", "game_closed", "fresh_all_runs_save_backup_with_readback",
                             "current_base_readback_matches", "staged_readback_before_rename", "installed_readback_after_rename"],
            "external_dependencies": dependencies, "preparation_only": True,
            "notes": str(job.get("notes", ""))}


def candidate_hash(job):
    """Identity of every declared candidate file; deployment destinations are checked separately."""
    root = "/data/homebrew/" + job["title_id"] + "/"
    rows = []
    for item in job["artifacts"]:
        path = remote_path(item["remote_path"])
        if not path.startswith(root):
            raise QueueError("all installation artifacts must stay inside the declared application")
        rows.append({"path": path[len(root):], "sha256": valid_hash(item["sha256"])})
    return hashlib.sha256(canonical(sorted(rows, key=lambda r: r["path"]))).hexdigest()


def install_policy(job, base=None):
    """Fail closed. A passed flag or a PC waiver alone never authorizes a main update."""
    deployment = job.get("deployment", {})
    mode, title = deployment.get("mode"), job.get("title_id")
    identity = candidate_hash(job)
    for item in job["artifacts"]:
        evidence_file(item, base or Path.cwd())
    root = "/data/homebrew/" + title + "/"
    for item in job.get("expected_base", []):
        if not remote_path(item["remote_path"]).startswith(root):
            raise QueueError("baseline paths must belong to the declared application")
    if mode == "main_update":
        if title != MAIN_TITLE:
            raise QueueError("main_update can target only the registered main title")
        for item in job['artifacts']:
            if item['remote_path'] == root + 'sce_sys/param.json' and read_json(local_path(item['path'], base)).get('titleId') != title:
                raise QueueError('main update param.json must preserve the main titleId')
        reference = evidence_file(deployment.get("test_report"), base or Path.cwd())
        report, sha = read_json_proof(local_path(reference["path"]))
        if sha != reference["sha256"] or report.get("schema") != 1 or report.get("kind") != "za_candidate_tests":
            raise QueueError("invalid candidate test report")
        if report.get("candidate_sha256") != identity or report.get("result") != "passed":
            raise QueueError("main update requires passed tests for the exact bundle SHA-256")
        tests = report.get("tests", [])
        if not isinstance(tests, list) or not tests or not all(isinstance(t, dict) and t.get("result") == "passed" for t in tests):
            raise QueueError("test report must contain nonempty passed tests")
        names = [t.get("name") for t in tests]
        if any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != len(names):
            raise QueueError("test names must be nonempty and unique")
        if not {"startup", "regression"}.issubset(names):
            raise QueueError("main promotion requires startup and change-specific regression tests")
        for test in tests:
            evidence_file(test.get("evidence"), local_path(reference["path"]).parent)
        return {"mode": mode, "candidate_sha256": identity, "test_report": reference}
    if mode != "side_app" or title in PROTECTED_TITLES:
        raise QueueError("unproven candidates may install only as an isolated side_app; main/vanilla targets are protected")
    # The generic side installer derives its sandbox from this distinct title and never writes main data.
    by_path = {item["remote_path"]: item for item in job["artifacts"]}
    param = by_path.get(root + "sce_sys/param.json")
    if param is None or root + "eboot.bin" not in by_path:
        raise QueueError("side_app requires its own eboot.bin and sce_sys/param.json")
    metadata = read_json(local_path(param["path"], base))
    if metadata.get("titleId") != title:
        raise QueueError("side application param.json titleId differs from its isolated target")
    return {"mode": mode, "candidate_sha256": identity, "app_root": root.rstrip("/"),
            "data_root": "/mnt/sandbox/" + title + "_000/download0"}


def atomic_write(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


class Board:
    def __init__(self, root=None, clock=time.time, resource="console"):
        if resource not in YIELD_SECONDS:
            raise QueueError("resource must be pc or console")
        self.resource = resource
        self.root = local_path(root if root is not None else (PC_ROOT if resource == "pc" else DEFAULT_ROOT))
        self.path = self.root / "state.json"
        self.mutex = self.root / ".queue-mutex"
        self.clock = clock

    def load(self):
        if not self.path.exists():
            if (self.root / "state.prev.json").exists():
                raise RecoveryRequired("state.json is missing but previous state exists; reconcile manually")
            return {"schema": 1, "console": CONSOLE, "resource": self.resource,
                    "generation": 0, "next_ticket": 1, "jobs": [], "active": None}
        try:
            envelope = json.loads(self.path.read_bytes())
            payload = envelope["payload"]
            actual = hashlib.sha256(canonical(payload)).hexdigest()
            if not hmac.compare_digest(actual, envelope["sha256"]):
                raise ValueError("SHA-256 mismatch")
            if payload["schema"] != 1 or payload["console"] != CONSOLE:
                raise ValueError("unexpected schema or console")
            if payload.get("resource", "console") != self.resource:
                raise ValueError("wrong resource state folder")
            if not isinstance(payload["jobs"], list) or payload["next_ticket"] <= max([j["sequence"] for j in payload["jobs"]] or [0]):
                raise ValueError("invalid ticket sequence")
            return payload
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RecoveryRequired(f"state integrity failure; no automatic rollback: {exc}") from exc

    def save(self, payload):
        payload["generation"] += 1
        envelope = {"sha256": hashlib.sha256(canonical(payload)).hexdigest(), "payload": payload}
        if self.path.exists():
            atomic_write(self.root / "state.prev.json", self.path.read_bytes())
        atomic_write(self.path, canonical(envelope) + b"\n")

    @contextmanager
    def transaction(self, agent, wait_seconds=15):
        self.root.mkdir(parents=True, exist_ok=True)
        nonce = uuid.uuid4().hex
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                self.mutex.mkdir()
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise Busy("metadata mutex occupied; it is never automatically stolen; inspect status")
                time.sleep(0.02)
        owner = {"nonce": nonce, "agent": agent, "pid": os.getpid(), "host": socket.gethostname(),
                 "platform": sys.platform, "acquired_at": self.clock()}
        try:
            atomic_write(self.mutex / "owner.json", canonical(owner))
            yield self.load()
        finally:
            # A mismatching/replaced mutex is an integrity error, never a cleanup target.
            if self.mutex.exists():
                current = retry_sharing(lambda: read_json(self.mutex / "owner.json"))
                if current.get("nonce") != nonce:
                    raise RecoveryRequired("metadata mutex ownership changed; no cleanup performed")
                retry_sharing((self.mutex / "owner.json").unlink)
                retry_sharing(self.mutex.rmdir)

    def expired(self, active):
        if self.resource == "console" and active.get("offline"):
            return False  # Offline time never forfeits ownership.
        now = self.clock()
        return now < active["heartbeat_at"] - 5 or now - active["heartbeat_at"] >= active["lease_seconds"]

    def status(self):
        state = self.load()
        active = state["active"]
        public = None if active is None else {k: v for k, v in active.items() if k != "token_hash"}
        if public:
            public["expired"] = self.expired(active)
            public["blocked_reason"] = "stale_requires_reconciliation" if public["expired"] else "exclusive_reservation"
            if active.get('offline'): public['blocked_reason'] = 'console_offline_paused'
            public.update(self.turn_status(active))
        metadata_owner = None
        if self.mutex.exists():
            try:
                metadata_owner = read_json(self.mutex / "owner.json")
            except QueueError:
                metadata_owner = {"unknown": True, "requires_reconciliation": True}
        jobs = [{k: v for k, v in row.items() if k not in ("last_token_hash",)} for row in state["jobs"]]
        return {"console": CONSOLE, "resource": self.resource, "yield_seconds": YIELD_SECONDS[self.resource],
                "baselines": state.get("baselines", {}),
                "initialized": self.path.exists(), "generation": state["generation"],
                "active": public, "metadata_mutex": metadata_owner, "jobs": jobs,
                "advisory": "Only participating agents are excluded. A reservation does not prove console availability."}

    def turn_status(self, active):
        if self.resource == "console" and active.get("offline"):
            return {"yield_by": None, "seconds_to_yield": active["offline"].get("yield_remaining"),
                    "must_yield": False, "paused": True,
                    "instruction": "Console offline: keep this ticket and ownership; timers resume after observed reconnection."}
        deadline = active.get("yield_by")
        return {"yield_by": deadline,
                "paused": False,
                "seconds_to_yield": None if deadline is None else max(0, deadline - self.clock()),
                "must_yield": deadline is not None and self.clock() >= deadline,
                "instruction": "Finish and hand off, including cleanup, by yield_by; heartbeat never extends it."
                               if deadline is not None else "No waiter: continue while heartbeating."}

    def contest(self, state):
        active = state["active"]
        if active and active.get("offline") and any(r["state"] == "queued" for r in state["jobs"]):
            if active["offline"].get("yield_remaining") is None:
                active["offline"]["yield_remaining"] = YIELD_SECONDS[self.resource]
                active["contested_at"] = self.clock()
            return
        if active and active.get("yield_by") is None and any(r["state"] == "queued" for r in state["jobs"]):
            active["contested_at"] = self.clock()
            active["yield_by"] = self.clock() + YIELD_SECONDS[self.resource]

    def check_baseline(self, state, row):
        if self.resource != "console":
            return
        baseline = state.get("baselines", {}).get(row["job"]["title_id"])
        if baseline:
            expected = {r["remote_path"]: r["sha256"] for r in row["job"]["expected_base"]}
            if any(expected.get(p) != sha for p, sha in baseline["files"].items()):
                raise QueueError("queued job predates the latest baseline; preserve its features, merge/rebuild and enqueue anew")

    def finish_baseline(self, state, row, record, base):
        """Validate final readbacks and preserve the full handoff manifest, not just eboot."""
        handoff = record.get("baseline_handoff", {})
        if handoff.get("mode") not in ("restore", "promote"):
            raise QueueError("baseline_handoff.mode must be restore or promote")
        if not handoff.get("name") or not handoff.get("preserved_features") or not handoff.get("rebuild_instructions"):
            raise QueueError("baseline handoff needs name, preserved_features and rebuild_instructions")
        proof = evidence_file(handoff.get("manifest"), base)
        expected = {r["remote_path"]: r["sha256"] for r in row["job"]["expected_base"]}
        if handoff["mode"] == "promote":
            if row["job"]["title_id"] == MAIN_TITLE:
                install_policy(row["job"], base)
            expected.update({r["remote_path"]: r["sha256"] for r in row["job"]["artifacts"]})
        files = {}
        for item in handoff.get("readbacks", []):
            key = remote_path(item.get("remote_path"))
            if key in files:
                raise QueueError("duplicate final baseline readback")
            files[key] = evidence_file(item.get("evidence"), base)["sha256"]
        if files != expected:
            raise QueueError("final readbacks do not match the restored/promoted baseline")
        baseline = {"name": handoff["name"], "files": files, "manifest": proof,
                    "preserved_features": handoff["preserved_features"],
                    "rebuild_instructions": handoff["rebuild_instructions"],
                    "ticket": row["ticket"], "registered_at": self.clock(), "mode": handoff["mode"]}
        # Validation must finish before mutating the transaction's in-memory state.
        return baseline

    def enqueue(self, agent, request_id, job_path):
        agent, request_id = valid_id(agent), valid_id(request_id)
        if self.resource == "pc":
            raw = read_json(local_path(job_path))
            if not isinstance(raw.get("name"), str) or not raw["name"].strip():
                raise QueueError("PC job requires a name")
            job = {"name": raw["name"], "notes": str(raw.get("notes", "")), "artifacts": []}
        else:
            job = normalized_job(job_path)
        # Artifact identity is content + destination, not Windows/WSL spelling of
        # the local path (NTFS may return different capitalization in each OS).
        identity = {**job, "artifacts": [{k: v for k, v in row.items() if k != "path"} for row in job["artifacts"]]}
        job_hash = hashlib.sha256(canonical(identity)).hexdigest()
        with self.transaction(agent) as state:
            old = next((r for r in state["jobs"] if r["request_id"] == request_id), None)
            if old:
                if old["job_sha256"] != job_hash or old["requested_by"] != agent:
                    raise QueueError("request ID already exists with a different agent or job")
                return {"ticket": old["ticket"], "state": old["state"], "already_enqueued": True}
            sequence = state["next_ticket"]
            row = {"sequence": sequence, "ticket": f"{sequence:08d}", "request_id": request_id,
                   "requested_by": agent, "enqueued_at": self.clock(), "job": job, "job_sha256": job_hash,
                   "state": "queued", "readiness": "waiting-console-handoff", "attempts": 0, "events": []}
            state["jobs"].append(row)
            state["next_ticket"] += 1
            self.contest(state)
            self.save(state)
            return {"ticket": row["ticket"], "state": "queued", "job_sha256": job_hash}

    def claim(self, agent, ticket=None, lease_seconds=600, user_priority_approval=None):
        agent = valid_id(agent)
        if not 30 <= lease_seconds <= 3600:
            raise QueueError("lease_seconds must be 30..3600")
        with self.transaction(agent) as state:
            if state["active"]:
                reason = "expired lease requires reconciliation" if self.expired(state["active"]) else "console reservation already owned"
                raise Busy(reason)
            head = next((row for row in state["jobs"] if row["state"] == "queued"), None)
            if head is None:
                return {"ticket": None, "reason": "queue empty"}
            if ticket is not None and ticket != head["ticket"]:
                if not user_priority_approval:
                    raise Busy(f"FIFO head is {head['ticket']}; cannot skip it")
                approval_path=local_path(user_priority_approval)
                approval, approval_hash=read_json_proof(approval_path)
                selected=next((r for r in state['jobs'] if r['ticket']==ticket and r['state']=='queued'),None)
                if (self.resource!='console' or selected is None or selected['requested_by']!=agent
                    or approval.get('source')!='user_message' or approval.get('approved_by')!='Tomer'
                    or approval.get('action')!='prioritize_ready_console_ticket' or approval.get('ticket')!=ticket
                    or approval.get('console')!=CONSOLE or approval.get('ready_to_execute') is not True
                    or not isinstance(approval.get('quote'),str) or not approval['quote'].strip()):
                    raise QueueError('Priority requires Tomer\'s explicit ticket-specific approval and a ready own job')
                evidence_file(approval.get('readiness_evidence'),approval_path.parent)
                # This selects one ready request only. No pending row is removed,
                # reordered or rewritten, and an active/offline owner never yields.
                head=selected
                head['events'].append({'event':'user_priority_approved','at':self.clock(),
                    'approval':{'path':shared_path(approval_path),'sha256':approval_hash}})
            for item in head["job"]["artifacts"]:
                evidence_file(item, self.root)
            self.check_baseline(state, head)
            token = secrets.token_hex(32)
            now = self.clock()
            active = {"ticket": head["ticket"], "lease_id": uuid.uuid4().hex, "agent": agent,
                      "host": socket.gethostname(), "platform": sys.platform,
                      "token_hash": hashlib.sha256(token.encode()).hexdigest(), "acquired_at": now,
                      "heartbeat_at": now, "lease_seconds": lease_seconds, "phase": "reserved"}
            state["active"] = active
            head["state"] = "reserved"
            self.contest(state)
            head["attempts"] += 1
            head["events"].append({"event": "reserved", "at": now, "agent": agent, "lease_id": active["lease_id"]})
            self.save(state)
            return {"ticket": head["ticket"], "lease_id": active["lease_id"], "token": token,
                    "phase": "reserved", "readiness": "waiting-console-handoff", "lease_seconds": lease_seconds,
                    **self.turn_status(active),
                    "note": "Local reservation only; no console access or availability check was performed."}

    def authenticate(self, state, agent, ticket, token, allow_stale=False, cleanup=False):
        active = state["active"]
        supplied = hashlib.sha256(token.encode()).hexdigest()
        if not active or active["ticket"] != ticket or active["agent"] != agent or not hmac.compare_digest(active["token_hash"], supplied):
            raise LostLease("lease is not yours; stop console actions immediately")
        if self.expired(active) and not allow_stale:
            raise LostLease("lease expired; stop console actions, reconcile explicitly; no automatic renewal")
        if self.turn_status(active)["must_yield"] and not cleanup:
            raise LostLease("handoff deadline reached; only cleanup and release are permitted; no takeover")
        return active, next(row for row in state["jobs"] if row["ticket"] == ticket)

    def readiness(self, path, row):
        path = local_path(path)
        record, record_hash = read_json_proof(path)
        if record.get("console") != CONSOLE or record.get("ticket") != row["ticket"]:
            raise QueueError("readiness console/ticket mismatch")
        try:
            stamp = datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone is required")
            checked = stamp.timestamp()
        except (KeyError, ValueError, TypeError) as exc:
            raise QueueError("readiness requires a checked_at ISO timestamp") from exc
        if not -30 <= self.clock() - checked <= 300:
            raise QueueError("readiness older than 5 minutes or future dated; obtain fresh observed conditions")
        validation = record.get("pc_validation", {})
        if validation.get("passed") is True:
            evidence_file(validation.get("evidence"), path.parent)
        else:
            exception = record.get("pc_bypass", {})
            if exception.get("approved_by") != "Tomer" or exception.get("reason") not in ("urgent_fix", "long_pc_queue"):
                raise QueueError("PC proof required, or Tomer's recorded approval for urgent_fix/long_pc_queue")
            evidence_file(exception.get("approval_evidence"), path.parent)
        waiver = None
        backup = record.get("save_backup", {})
        if not isinstance(backup, dict):
            raise QueueError("save_backup must describe a backup or an explicit waiver")
        if isinstance(backup, dict) and "waived_by" in backup:
            waiver = save_backup_waiver(backup, path.parent, row)
        else:
            if not all(backup.get(flag) is True for flag in ("fresh", "all_runs", "readback_verified")):
                raise QueueError("precondition unsatisfied: save_backup")
            evidence_file(backup.get("evidence"), path.parent)
        for name, flags in (("external_owner_handoff", ("confirmed",)), ("game_closed", ("verified",))):
            section = record.get(name, {})
            if not all(section.get(flag) is True for flag in flags):
                raise QueueError(f"precondition unsatisfied: {name}")
            evidence_file(section.get("evidence"), path.parent)
        expected = {r["remote_path"]: r["sha256"] for r in row["job"]["expected_base"]}
        actual = {}
        for item in record.get("base_readbacks", []):
            proof = evidence_file(item.get("evidence"), path.parent)
            claimed_hash = valid_hash(item.get("sha256"))
            if proof["sha256"] != claimed_hash:
                raise QueueError("base evidence must be the actual readback file with the queued base SHA-256")
            key = remote_path(item.get("remote_path"))
            if key in actual:
                raise QueueError("duplicate base readback")
            actual[key] = claimed_hash
        if actual != expected:
            raise QueueError("current base readbacks differ from the queued expected base; merge/rebuild before installation")
        for item in row["job"]["artifacts"]:
            evidence_file(item, path.parent)
        result = {"path": shared_path(path), "sha256": record_hash, "checked_at": checked}
        if waiver is not None:
            result["save_backup_waiver"] = waiver
        return result

    def heartbeat(self, agent, ticket, token, begin_install=None):
        with self.transaction(agent) as state:
            active, row = self.authenticate(state, agent, ticket, token, cleanup=begin_install is None)
            if begin_install is not None:
                if active.get("offline"):
                    raise Busy("console offline; retain ticket and report reconnection before installation")
                if self.resource != "console":
                    raise QueueError("PC turns do not install on the console")
                self.check_baseline(state, row)
                if active["phase"] != "reserved":
                    raise QueueError("installation phase already began")
                proof = self.readiness(begin_install, row)
                proof["deployment"] = install_policy(row["job"], self.root)
                self.authenticate(state, agent, ticket, token)
                active["readiness_record"] = proof
                active["phase"] = "installing"
                row["state"] = "installing"
                row["readiness"] = "observed-preconditions-recorded"
                row["events"].append({"event": "installing", "at": self.clock(), "agent": agent})
            active["heartbeat_at"] = self.clock()
            self.save(state)
            return {"ticket": ticket, "ok": True, "phase": active["phase"], **self.turn_status(active)}

    def check(self, agent, ticket, token, cleanup=False):
        # Read-only and no hardware access; called before workbench resource operations.
        active, _ = self.authenticate(self.load(), agent, ticket, token, cleanup=cleanup)
        if active.get("offline"):
            raise Busy("console offline; queue and ownership paused, not released")
        return {"ticket": ticket, "ok": True, **self.turn_status(active)}

    def authorize_install(self, agent, ticket, token):
        state = self.load()
        active, row = self.authenticate(state, agent, ticket, token)
        if self.resource != "console" or active.get("offline"):
            raise Busy("console unavailable; retain this turn")
        self.check_baseline(state, row)
        return install_policy(row["job"], self.root)

    def connection(self, agent, ticket, token, state, evidence, user_report=False):
        if self.resource != "console" or state not in ("offline", "online"):
            raise QueueError("connection applies only to console offline/online")
        path = local_path(evidence)
        record, sha = read_json_proof(path)
        if record.get("console") != CONSOLE or record.get("state") != state or record.get("ticket") != ticket:
            raise QueueError("connection evidence must identify console, ticket and observed state")
        observed = record.get("observed_at")
        if not isinstance(observed, (int, float)) or not -5 <= self.clock() - observed <= 60:
            raise QueueError("connection observation must be fresh (epoch seconds, <=60s)")
        if not isinstance(record.get("detail"), str) or not record["detail"].strip():
            raise QueueError("connection observation requires actual error/probe detail")
        with self.transaction(agent) as board:
            if user_report:
                # An explicit owner-of-project report changes connectivity only, never lease ownership.
                if (agent != "Tomer" or token or record.get("source") != "user_message"
                        or record.get("reported_by") != "Tomer" or not isinstance(record.get("quote"), str)
                        or not record["quote"].strip()):
                    raise QueueError("user report requires Tomer's explicit quoted message, without another agent's token")
                active = board['active']
                if active is None or active['ticket'] != ticket:
                    raise LostLease("reported ticket is no longer active; refresh status")
                row = next(r for r in board['jobs'] if r['ticket'] == ticket)
            else:
                active, row = self.authenticate(board, agent, ticket, token, allow_stale=True, cleanup=True)
            if record.get("lease_id") != active["lease_id"]:
                raise QueueError("connection observation must identify the exact lease")
            if state == "offline":
                if not active.get("offline"):
                    remaining = None if active.get("yield_by") is None else max(0, active["yield_by"] - self.clock())
                    active["offline"] = {"since": self.clock(), "yield_remaining": remaining,
                                         "evidence": {"path": shared_path(path), "sha256": sha}}
            elif active.get("offline"):
                pause = active.pop("offline")
                if self.clock() < pause["since"] - 5:
                    raise RecoveryRequired("clock moved backward during outage")
                remaining = pause["yield_remaining"]
                # An outage first detected after the old deadline must not forfeit this turn.
                active["yield_by"] = None if remaining is None else self.clock() + (remaining or YIELD_SECONDS["console"])
                active["heartbeat_at"] = self.clock()
            row["events"].append({"event": "connection_" + state, "at": self.clock(),
                                  "reported_by": agent, "user_report": user_report,
                                  "evidence": {"path": shared_path(path), "sha256": sha}})
            self.save(board)
            return {"ticket": ticket, "ok": True, **self.turn_status(active)}

    def complete(self, agent, ticket, token, receipt):
        receipt_path = local_path(receipt)
        evidence, receipt_hash = read_json_proof(receipt_path)
        with self.transaction(agent) as state:
            row = next((r for r in state["jobs"] if r["ticket"] == ticket), None)
            supplied = hashlib.sha256(token.encode()).hexdigest()
            if row and row["state"] == "completed":
                if row.get("completed_by") == agent and hmac.compare_digest(row.get("last_token_hash", ""), supplied) and row["receipt"]["sha256"] == receipt_hash:
                    return {"ticket": ticket, "ok": True, "already_completed": True}
                raise LostLease("ticket completed by another lease or different receipt")
            active, row = self.authenticate(state, agent, ticket, token, cleanup=True)
            if active.get("offline"):
                raise Busy("console offline; cannot complete or advance the queue")
            if self.resource == "pc":
                if evidence.get("ticket") != ticket or evidence.get("own_processes_stopped") is not True:
                    raise QueueError("PC receipt needs ticket and own_processes_stopped=true")
                evidence_file(evidence.get("evidence"), receipt_path.parent)
                self.authenticate(state, agent, ticket, token, cleanup=True)
                row.update(state="completed", completed_by=agent, completed_at=self.clock(),
                           last_token_hash=active["token_hash"],
                           receipt={"path": shared_path(receipt_path), "sha256": receipt_hash})
                row["events"].append({"event": "completed", "at": self.clock(), "agent": agent})
                state["active"] = None
                self.save(state)
                return {"ticket": ticket, "ok": True, "state": "completed"}
            if active["phase"] != "installing":
                raise QueueError("reserved jobs cannot claim hardware completion; record readiness first")
            if evidence.get("console") != CONSOLE or evidence.get("ticket") != ticket or evidence.get("console_handoff_complete") is not True:
                raise QueueError("receipt must identify console/ticket and verify console handoff")
            waiver = active.get("readiness_record", {}).get("save_backup_waiver")
            if waiver is not None:
                repeated = save_backup_waiver(evidence.get("save_backup"), receipt_path.parent, row)
                if repeated != waiver or evidence.get("save_backup_still_verified") is True or evidence.get("all_runs_backed_up") is True:
                    raise QueueError("receipt must repeat the same waiver without claiming a save backup")
            elif evidence.get("save_backup_still_verified") is not True or (isinstance(evidence.get("save_backup"), dict) and "waived_by" in evidence["save_backup"]):
                raise QueueError("receipt must verify the normal save backup; a waiver cannot be added after readiness")
            expected = {r["remote_path"]: r["sha256"] for r in row["job"]["artifacts"]}
            actual = {}
            for item in evidence.get("readbacks", []):
                staged = evidence_file(item.get("staged"), receipt_path.parent)
                installed = evidence_file(item.get("installed"), receipt_path.parent)
                if staged["sha256"] != installed["sha256"]:
                    raise QueueError("staged/installed readback mismatch")
                key = remote_path(item.get("remote_path"))
                if key in actual:
                    raise QueueError("duplicate installed readback")
                actual[key] = installed["sha256"]
            if actual != expected:
                raise QueueError("receipt does not prove both readbacks for every artifact")
            baseline = self.finish_baseline(state, row, evidence, receipt_path.parent)
            self.authenticate(state, agent, ticket, token, cleanup=True)
            state.setdefault("baselines", {})[row["job"]["title_id"]] = baseline
            row.update(state="completed", completed_by=agent, completed_at=self.clock(), last_token_hash=active["token_hash"],
                       receipt={"path": shared_path(receipt_path), "sha256": receipt_hash})
            row["events"].append({"event": "completed", "at": self.clock(), "agent": agent})
            state["active"] = None
            self.save(state)
            return {"ticket": ticket, "ok": True, "state": "completed"}

    def release(self, agent, ticket, token=None, reason="", resolution=None, expected_lease_id=None, cancel_queued=False):
        if not reason.strip():
            raise QueueError("release requires a reason")
        with self.transaction(agent) as state:
            if cancel_queued:
                row = next((r for r in state["jobs"] if r["ticket"] == ticket), None)
                if not row or row["state"] != "queued" or row["requested_by"] != agent:
                    raise QueueError("only the submitting agent can cancel its queued, unreserved job")
                row["state"] = "cancelled"
                row["events"].append({"event": "cancelled", "at": self.clock(), "agent": agent, "reason": reason})
                self.save(state)
                return {"ticket": ticket, "ok": True, "state": "cancelled"}
            active = state["active"]
            if expected_lease_id:
                if not active or active["lease_id"] != expected_lease_id or active["ticket"] != ticket or not self.expired(active):
                    raise QueueError("stale reconciliation requires the exact current expired lease ID")
                row = next(r for r in state["jobs"] if r["ticket"] == ticket)
            else:
                active, row = self.authenticate(state, agent, ticket, token or "", cleanup=True)
            if active.get("offline"):
                raise Busy("console offline; keep this turn, do not release or requeue")
            if expected_lease_id or active["phase"] == "installing":
                if resolution is None:
                    raise QueueError("installing/stale reservations require a concrete reconciliation record")
                path = local_path(resolution)
                record, record_hash = read_json_proof(path)
                if record.get("ticket") != ticket or record.get("lease_id") != active["lease_id"]:
                    raise QueueError("resolution must identify the exact ticket and lease")
                if self.resource == "console":
                    if record.get("console") != CONSOLE or record.get("no_active_installation") is not True or record.get("console_handoff_confirmed") is not True:
                        raise QueueError("resolution must confirm console, no active installation and handoff")
                elif record.get("pc_handoff_confirmed") is not True:
                    raise QueueError("stale PC resolution requires pc_handoff_confirmed=true")
                evidence_file(record.get("evidence"), path.parent)
                if self.resource == "console" and active["phase"] == "installing":
                    baseline = self.finish_baseline(state, row, record, path.parent)
                    state.setdefault("baselines", {})[row["job"]["title_id"]] = baseline
                if self.resource == "pc" and record.get("own_processes_stopped") is not True:
                    raise QueueError("PC reconciliation requires own_processes_stopped=true")
                if not expected_lease_id:
                    self.authenticate(state, agent, ticket, token or "", cleanup=True)
                row["last_reconciliation"] = {"path": shared_path(path), "sha256": record_hash}
            if self.resource == "pc" and resolution is None:
                raise QueueError("PC release requires --resolution proving own_processes_stopped=true")
            if self.resource == "pc" and not expected_lease_id:
                path = local_path(resolution)
                record, record_hash = read_json_proof(path)
                if record.get("ticket") != ticket or record.get("own_processes_stopped") is not True:
                    raise QueueError("PC release must identify ticket and confirm own processes stopped")
                evidence_file(record.get("evidence"), path.parent)
                self.authenticate(state, agent, ticket, token or "", cleanup=True)
                row["last_reconciliation"] = {"path": shared_path(path), "sha256": record_hash}
            row.update(state="released", readiness="finished-turn-register-again-if-needed")
            row["events"].append({"event": "released", "at": self.clock(), "agent": agent, "reason": reason,
                                  "lease_id": active["lease_id"], "stale_reconciled": bool(expected_lease_id)})
            state["active"] = None
            self.save(state)
            return {"ticket": ticket, "ok": True, "state": "released", "position_preserved": False,
                    "next_step": "If unfinished, enqueue with a new request ID at the tail."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", choices=("pc", "console"), default="console")
    parser.add_argument("--root", help="isolated state override for tests; production uses the shared canonical root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--agent", required=True)
    enqueue.add_argument("--request-id", required=True)
    enqueue.add_argument("--job", required=True)
    claim = commands.add_parser("claim")
    claim.add_argument("--agent", required=True)
    claim.add_argument("--ticket")
    claim.add_argument("--lease-seconds", type=int, default=600)
    claim.add_argument("--user-priority-approval",help="explicit ticket-specific user message; preserves all other queued requests")
    for name in ("connection", "authorize-install", "check", "heartbeat", "complete", "release"):
        command = commands.add_parser(name)
        command.add_argument("--agent", required=True)
        command.add_argument("--ticket", required=True)
        command.add_argument("--token", help="or environment CONSOLE_INSTALL_TOKEN")
        if name == "connection":
            command.add_argument("--state", choices=("offline", "online"), required=True)
            command.add_argument("--evidence", required=True)
            command.add_argument("--user-report", action="store_true", help="explicit quoted report from Tomer; connectivity only, no lease takeover")
        elif name == "authorize-install":
            pass
        elif name == "check":
            command.add_argument("--cleanup", action="store_true")
        elif name == "heartbeat":
            command.add_argument("--begin-install", metavar="READINESS_JSON")
        elif name == "complete":
            command.add_argument("--receipt", required=True)
        else:
            command.add_argument("--reason", required=True)
            command.add_argument("--resolution")
            command.add_argument("--expected-lease-id", help="explicit reconciliation of this expired lease; never automatic")
            command.add_argument("--cancel-queued", action="store_true", help="submitting agent withdraws its queued job")
    args = vars(parser.parse_args())
    resource = args.pop("resource")
    root = args.pop("root") or os.environ.get("PC_TEST_STATE" if resource == "pc" else "CONSOLE_INSTALL_STATE")
    board = Board(root, resource=resource)
    name = args.pop("command")
    name = name.replace("-", "_")
    if "token" in args:
        args["token"] = args["token"] or ("" if args.get("user_report") else os.environ.get("PC_TEST_TOKEN" if resource == "pc" else "CONSOLE_INSTALL_TOKEN", ""))
    if name == "enqueue":
        args["job_path"] = args.pop("job")
    try:
        if "agent" in args:
            valid_id(args["agent"])
        result = getattr(board, name)(**args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (QueueError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "kind": type(exc).__name__}, ensure_ascii=False))
        return exc.code if isinstance(exc, QueueError) else 2


if __name__ == "__main__":
    sys.exit(main())
