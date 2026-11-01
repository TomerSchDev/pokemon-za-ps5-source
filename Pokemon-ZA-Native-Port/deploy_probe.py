"""Install a NEW native probe title with SHA-256 readback; never overwrite a title."""
from datetime import datetime, timezone
import ftplib
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "native-probe/dist/PPSA91760"
HOST = "192.168.1.135"
FINAL = "/data/homebrew/PPSA91760"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
STAGE = "/data/.za-native-probe-" + STAMP


def main():
    metadata = json.loads((SOURCE / "sce_sys/param.json").read_text(encoding="utf-8"))
    assert metadata["titleId"] == "PPSA91760"
    assert metadata["localizedParameters"]["en-US"]["titleName"] == "ZA Native Probe A0"
    with urllib.request.urlopen(f"http://{HOST}:8084/processes_list", timeout=6) as response:
        processes = json.load(response)["processes"]
    if any(p.get("name") == "eboot.bin" for p in processes):
        raise RuntimeError("Another app is running; close it before deployment/launch testing")
    ftp = ftplib.FTP()
    ftp.connect(HOST, 2121, timeout=30)
    ftp.login()
    ftp.sendcmd("SELF")  # Retrieve actual stored SELF bytes, not decrypted ELF.
    try:
        ftp.cwd("/data/homebrew")
        names = {name for name, _ in ftp.mlsd()}
        if any(name == "PPSA91760" or name.startswith("PPSA91760.") for name in names):
            raise RuntimeError("Title ID already exists; refusing to overwrite")
        ftp.mkd(STAGE)
        ftp.sendcmd("SITE CHMOD 755 " + STAGE)
        for path in sorted((p for p in SOURCE.rglob("*") if p.is_dir()), key=lambda p: len(p.parts)):
            remote = STAGE + "/" + path.relative_to(SOURCE).as_posix()
            ftp.mkd(remote)
            ftp.sendcmd("SITE CHMOD 755 " + remote)
        files = []
        for path in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
            relative = path.relative_to(SOURCE).as_posix()
            remote = STAGE + "/" + relative
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open("rb") as stream:
                ftp.storbinary("STOR " + remote, stream, 1 << 20)
            ftp.sendcmd("SITE CHMOD " + ("755" if path.suffix in (".bin", ".prx", ".elf") else "644") + " " + remote)
            received = hashlib.sha256()
            ftp.retrbinary("RETR " + remote, received.update, 1 << 20)
            if received.hexdigest() != expected:
                raise RuntimeError("Readback hash mismatch: " + relative)
            files.append({"path": relative, "bytes": path.stat().st_size, "sha256": expected})
            print("Verified", relative, flush=True)
        ftp.rename(STAGE, FINAL)
        result = {"installed_utc": STAMP, "host": HOST, "path": FINAL, "files": files,
                  "all_files_readback_verified": True, "launch_verified": False}
        output = ROOT / "evidence" / ("deployment-" + STAMP + ".json")
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("Installed", FINAL, flush=True)
        print("Evidence", output, flush=True)
    finally:
        ftp.close()


if __name__ == "__main__":
    main()
