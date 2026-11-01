"""console.py with --client r24: port/preparation-r21-hardware/console.py, unchanged, plus the r24 observer client.

Every operation, check, path and evidence location is the original's (the original module is loaded and run as
is); only two things are added before its main() runs: "r24" among --client's choices, and load_client("r24")
returning port/perf-r24/observer/client.py (r23c's client with slot depths 8/16/32/64). Usage is the original's:

    python port/perf-r24/console.py --client r24 inspect
    python port/perf-r24/console.py --client r24 measure --session SID --pid PID --seq N 20
"""
import argparse
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "port/preparation-r21-hardware/console.py"
R24_CLIENT = ROOT / "port/perf-r24/observer"

spec = importlib.util.spec_from_file_location("za_console_r21", ORIGINAL)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

_load_client = base.load_client


def load_client(version):
    if version == "r24":
        sys.path.insert(0, str(R24_CLIENT))
        return importlib.import_module("client")
    return _load_client(version)


base.load_client = load_client

_add_argument = argparse.ArgumentParser.add_argument


def _add_argument_r24(self, *args, **kwargs):
    if args and args[0] == "--client" and "choices" in kwargs:
        kwargs["choices"] = tuple(kwargs["choices"]) + ("r24",)
    return _add_argument(self, *args, **kwargs)


argparse.ArgumentParser.add_argument = _add_argument_r24

if __name__ == "__main__":
    base.main()
