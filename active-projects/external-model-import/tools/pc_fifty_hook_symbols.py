"""Read COFF locations of existing runtime test hooks from the exact owned executable."""
from pathlib import Path
import hashlib,os,subprocess,tempfile,json
from pc_fifty_control import EXE,EXPECTED

def main():
    assert hashlib.sha256(EXE.read_bytes()).hexdigest()==EXPECTED
    alias=Path(tempfile.gettempdir())/'codex-za-symbols-c74c9435'/EXE.name;alias.parent.mkdir(exist_ok=True)
    if not alias.exists():os.link(EXE,alias)
    assert os.path.samefile(alias,EXE)
    output=subprocess.run(['C:/msys64/ucrt64/bin/nm.exe','--defined-only',str(alias)],capture_output=True,text=True,check=True).stdout
    names={'g_test_lx','g_test_ly','g_test_buttons','g_test_buttons_until','g_test_stick_until'}
    result={parts[-1]:hex(int(parts[0],16)-0x140000000) for line in output.splitlines() if len(parts:=line.split())==3 and parts[-1] in names}
    assert set(result)==names;print(json.dumps(result),flush=True)

if __name__=='__main__':main()
