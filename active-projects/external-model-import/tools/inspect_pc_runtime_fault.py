"""Symbolize one owned PC run's recorded host offsets with its exact runtime."""
from pathlib import Path
import json,hashlib,subprocess,sys,os,tempfile

def main():
    lab=Path(__file__).resolve().parents[3]/'hebrew-lab';run=lab/'runs'/sys.argv[1];record=json.loads((run/'run.json').read_text())
    exe=lab/'runtime/lasrecomp.exe';assert hashlib.sha256(exe.read_bytes()).hexdigest()==record['runtime_sha256']
    tool=Path('C:/msys64/ucrt64/bin/addr2line.exe')
    for binary,offsets in ((exe,(0xac74,0x7c53)),(Path(record['game'])/'lasgame.dll',(0x12f0c987,0x12f0a303,0x1469c1a1,0xfba7483,0x69f617))):
        # Both PE images use 0x140000000, read from the optional header rather than guessed.
        import struct
        with binary.open('rb') as f:
            f.seek(0x3c);pe=struct.unpack('<I',f.read(4))[0];f.seek(pe+24+24);base=struct.unpack('<Q',f.read(8))[0]
        alias=Path(tempfile.gettempdir())/'codex-za-symbols-c74c9435'/binary.name;alias.parent.mkdir(exist_ok=True)
        if not alias.exists():os.link(binary,alias)
        assert os.path.samefile(binary,alias)
        result=subprocess.run([str(tool),'-f','-C','-e',str(alias),*[hex(base+x) for x in offsets]],capture_output=True,text=True,check=True)
        print(json.dumps(dict(binary=str(binary),base=hex(base),offsets=[hex(x) for x in offsets],symbolization=result.stdout)),flush=True)

if __name__=='__main__':main()
