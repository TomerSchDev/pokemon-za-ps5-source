#!/usr/bin/env python3
"""Cooperative, console-wide FIFO reservations. Never contacts console hardware.

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
    if not isinstance(value, str) or not value.startswith("/") or ".." in PurePosixPath(value).parts:
        raise QueueError("remote_path must be absolute and contain no '..'")
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
    if not bases or len({r["remote_path"] for r in bases}) != len(bases):
        raise QueueError("expected_base must be nonempty with unique remote paths; unknown bases are not installable")
    dependencies = job.get("external_dependencies", [])
    if not isinstance(dependencies, list) or len(dependencies) > 20 or any(not isinstance(r, dict) for r in dependencies):
        raise QueueError("external_dependencies must be a list of at most 20 records")
    return {"console": CONSOLE, "title_id": job["title_id"], "name": job["name"],
            "artifacts": artifacts, "expected_base": bases,
            "requirements": ["external_console_handoff", "game_closed", "fresh_all_runs_save_backup_with_readback",
                             "current_base_readback_matches", "staged_readback_before_rename", "installed_readback_after_rename"],
            "external_dependencies": dependencies, "preparation_only": True,
            "notes": str(job.get("notes", ""))}


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
    def __init__(self, root=DEFAULT_ROOT, clock=time.time):
        self.root = local_path(root)
        self.path = self.root / "state.json"
        self.mutex = self.root / ".queue-mutex"
        self.clock = clock

    def load(self):
        if not self.path.exists():
            if (self.root / "state.prev.json").exists():
                raise RecoveryRequired("state.json is missing but previous state exists; reconcile manually")
            return {"schema": 1, "console": CONSOLE, "generation": 0, "next_ticket": 1, "jobs": [], "active": None}
        try:
            envelope = json.loads(self.path.read_bytes())
            payload = envelope["payload"]
            actual = hashlib.sha256(canonical(payload)).hexdigest()
            if not hmac.compare_digest(actual, envelope["sha256"]):
                raise ValueError("SHA-256 mismatch")
            if payload["schema"] != 1 or payload["console"] != CONSOLE:
                raise ValueError("unexpected schema or console")
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
                current = read_json(self.mutex / "owner.json")
                if current.get("nonce") != nonce:
                    raise RecoveryRequired("metadata mutex ownership changed; no cleanup performed")
                (self.mutex / "owner.json").unlink()
                self.mutex.rmdir()

    def expired(self, active):
        now = self.clock()
        return now < active["heartbeat_at"] - 5 or now - active["heartbeat_at"] >= active["lease_seconds"]

    def status(self):
        state = self.load()
        active = state["active"]
        public = None if active is None else {k: v for k, v in active.items() if k != "token_hash"}
        if public:
            public["expired"] = self.expired(active)
            public["blocked_reason"] = "stale_requires_reconciliation" if public["expired"] else "exclusive_reservation"
        metadata_owner = None
        if self.mutex.exists():
            try:
                metadata_owner = read_json(self.mutex / "owner.json")
            except QueueError:
                metadata_owner = {"unknown": True, "requires_reconciliation": True}
        jobs = [{k: v for k, v in row.items() if k not in ("last_token_hash",)} for row in state["jobs"]]
        return {"console": CONSOLE, "initialized": self.path.exists(), "generation": state["generation"],
                "active": public, "metadata_mutex": metadata_owner, "jobs": jobs,
                "advisory": "Only participating agents are excluded. A reservation does not prove console availability."}

    def enqueue(self, agent, request_id, job_path):
        agent, request_id = valid_id(agent), valid_id(request_id)
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
            self.save(state)
            return {"ticket": row["ticket"], "state": "queued", "job_sha256": job_hash}

    def claim(self, agent, ticket=None, lease_seconds=600):
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
                raise Busy(f"FIFO head is {head['ticket']}; cannot skip it")
            for item in head["job"]["artifacts"]:
                evidence_file(item, self.root)
            token = secrets.token_hex(32)
            now = self.clock()
            active = {"ticket": head["ticket"], "lease_id": uuid.uuid4().hex, "agent": agent,
                      "host": socket.gethostname(), "platform": sys.platform,
                      "token_hash": hashlib.sha256(token.encode()).hexdigest(), "acquired_at": now,
                      "heartbeat_at": now, "lease_seconds": lease_seconds, "phase": "reserved"}
            state["active"] = active
            head["state"] = "reserved"
            head["attempts"] += 1
            head["events"].append({"event": "reserved", "at": now, "agent": agent, "lease_id": active["lease_id"]})
            self.save(state)
            return {"ticket": head["ticket"], "lease_id": active["lease_id"], "token": token,
                    "phase": "reserved", "readiness": "waiting-console-handoff", "lease_seconds": lease_seconds,
                    "note": "Local reservation only; no console access or availability check was performed."}

    def authenticate(self, state, agent, ticket, token, allow_stale=False):
        active = state["active"]
        supplied = hashlib.sha256(token.encode()).hexdigest()
        if not active or active["ticket"] != ticket or active["agent"] != agent or not hmac.compare_digest(active["token_hash"], supplied):
            raise LostLease("lease is not yours; stop console actions immediately")
        if self.expired(active) and not allow_stale:
            raise LostLease("lease expired; stop console actions, reconcile explicitly; no automatic renewal")
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
        for name, flags in (("external_owner_handoff", ("confirmed",)), ("game_closed", ("verified",)),
                            ("save_backup", ("fresh", "all_runs", "readback_verified"))):
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
        return {"path": shared_path(path), "sha256": record_hash, "checked_at": checked}

    def heartbeat(self, agent, ticket, token, begin_install=None):
        with self.transaction(agent) as state:
            active, row = self.authenticate(state, agent, ticket, token)
            if begin_install is not None:
                if active["phase"] != "reserved":
                    raise QueueError("installation phase already began")
                proof = self.readiness(begin_install, row)
                self.authenticate(state, agent, ticket, token)
                active["readiness_record"] = proof
                active["phase"] = "installing"
                row["state"] = "installing"
                row["readiness"] = "observed-preconditions-recorded"
                row["events"].append({"event": "installing", "at": self.clock(), "agent": agent})
            active["heartbeat_at"] = self.clock()
            self.save(state)
            return {"ticket": ticket, "ok": True, "phase": active["phase"]}

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
            active, row = self.authenticate(state, agent, ticket, token)
            if active["phase"] != "installing":
                raise QueueError("reserved jobs cannot claim hardware completion; record readiness first")
            if evidence.get("console") != CONSOLE or evidence.get("ticket") != ticket or evidence.get("save_backup_still_verified") is not True or evidence.get("console_handoff_complete") is not True:
                raise QueueError("receipt must identify console/ticket and verify save backup plus console handoff")
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
            self.authenticate(state, agent, ticket, token)
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
                active, row = self.authenticate(state, agent, ticket, token or "")
            if expected_lease_id or active["phase"] == "installing":
                if resolution is None:
                    raise QueueError("installing/stale reservations require a concrete reconciliation record")
                path = local_path(resolution)
                record, record_hash = read_json_proof(path)
                if record.get("console") != CONSOLE or record.get("ticket") != ticket or record.get("lease_id") != active["lease_id"] or record.get("no_active_installation") is not True or record.get("console_handoff_confirmed") is not True:
                    raise QueueError("resolution must confirm matching lease and no active installation plus handoff")
                evidence_file(record.get("evidence"), path.parent)
                if not expected_lease_id:
                    self.authenticate(state, agent, ticket, token or "")
                row["last_reconciliation"] = {"path": shared_path(path), "sha256": record_hash}
            row.update(state="queued", readiness="waiting-console-handoff")
            row["events"].append({"event": "released", "at": self.clock(), "agent": agent, "reason": reason,
                                  "lease_id": active["lease_id"], "stale_reconciled": bool(expected_lease_id)})
            state["active"] = None
            self.save(state)
            return {"ticket": ticket, "ok": True, "state": "queued", "position_preserved": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.environ.get("CONSOLE_INSTALL_STATE", str(DEFAULT_ROOT)))
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
    for name in ("heartbeat", "complete", "release"):
        command = commands.add_parser(name)
        command.add_argument("--agent", required=True)
        command.add_argument("--ticket", required=True)
        command.add_argument("--token", help="or environment CONSOLE_INSTALL_TOKEN")
        if name == "heartbeat":
            command.add_argument("--begin-install", metavar="READINESS_JSON")
        elif name == "complete":
            command.add_argument("--receipt", required=True)
        else:
            command.add_argument("--reason", required=True)
            command.add_argument("--resolution")
            command.add_argument("--expected-lease-id", help="explicit reconciliation of this expired lease; never automatic")
            command.add_argument("--cancel-queued", action="store_true", help="submitting agent withdraws its queued job")
    args = vars(parser.parse_args())
    board = Board(args.pop("root"))
    name = args.pop("command")
    if "token" in args:
        args["token"] = args["token"] or os.environ.get("CONSOLE_INSTALL_TOKEN", "")
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
