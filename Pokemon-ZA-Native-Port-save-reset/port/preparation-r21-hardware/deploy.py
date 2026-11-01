"""Idle-only r21 deployment; preserve all installed settings including batch4."""
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("transport", ROOT / "port/submission-r20-hardware/hardware.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
t.SOURCE = ROOT / "artifacts/randomizer-r21-preparation/PPSA91762/eboot.bin"
t.BASE = ROOT / "artifacts/randomizer-r20b-batch/PPSA91762/eboot.bin"
t.BASE_SHA = "9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852"
t.E = ROOT / "evidence/preparation-r21-hardware/deployment"
def preserve_options(c, ignored, out):
    t.identity(c); t.idle()
    previous = c.read(t.APP + "/submission-options.txt", 1024)
    assert previous == b"batch4\n", previous
    (out / "previous-submission-options.txt").write_bytes(previous)
    return dict(profile="batch4", preserved=True, readback=True)
t.options = preserve_options
original_deploy = t.deploy
def checked_deploy(c, expected, out, rollback=False):
    preserve_options(c, None, out)
    return original_deploy(c, expected, out, rollback)
t.deploy = checked_deploy
if __name__ == "__main__": t.main()
