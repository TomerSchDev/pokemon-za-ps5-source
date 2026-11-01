"""Parent-owned r20b deployment using the audited idle-only r20 transport.
Rollback is the exact r20 binary measured with each enabled. No title is killed.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("r20_transport", ROOT / "port/submission-r20-hardware/hardware.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
transport.SOURCE = ROOT / "artifacts/randomizer-r20b-batch/PPSA91762/eboot.bin"
transport.BASE = ROOT / "artifacts/randomizer-r20-batch/PPSA91762/eboot.bin"
transport.BASE_SHA = "33e435707b787fe23391996a5063b724d1c74627f4fea6e52d7b6d637b2f3819"
transport.E = ROOT / "evidence/submission-r20b-hardware"

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("op", choices=("inspect", "deploy", "launch", "rollback", "log"))
    p.add_argument("--sha256")
    p.add_argument("--seconds", type=int, default=1800)
    a = p.parse_args()
    # The existing parser/transport gates source hash, title identity, known
    # installed binary, staging readback, idle state and final readback.
    transport.main()

if __name__ == "__main__":
    main()

