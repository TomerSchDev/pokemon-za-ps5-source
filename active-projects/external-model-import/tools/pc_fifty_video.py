"""Encode a contiguous sequence of actual runtime PNGs, then verify its NAS copy."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,subprocess

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run');p.add_argument('--first',type=int,required=True);p.add_argument('--last',type=int,required=True)
    p.add_argument('--stride',type=int,default=1);p.add_argument('--subdir',choices=('frames',''),default='frames')
    p.add_argument('--label',required=True);a=p.parse_args()
    assert re.fullmatch(r'pc-fifty-[a-z0-9-]+',a.run) and re.fullmatch(r'[a-z0-9-]+',a.label)
    assert 0<a.first<a.last and 1<=a.stride<=10 and (a.last-a.first)%a.stride==0
    lab=Path(__file__).resolve().parents[3];root=lab/'hebrew-lab/runs'/a.run
    frames=root/'build'/a.subdir;inputs=[frames/f'frame_{n:05d}.png' for n in range(a.first,a.last+1,a.stride)]
    evidence=[dict(frame=int(x.stem.split('_')[1]),sha256=sha(x)) for x in inputs]
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=lab/'pc-fifty-20261031-r1/evidence'/f'{a.label}-{stamp}';out.mkdir(parents=True,exist_ok=False)
    # An ASCII hardlink path also avoids legacy ffmpeg Unicode path handling.
    import tempfile
    staging=Path(tempfile.mkdtemp(prefix='za-actual-frames-'))
    try:
        for i,src in enumerate(inputs):(staging/f'{i:05d}.png').hardlink_to(src)
        ffmpeg=Path.home()/'AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-6.1-essentials_build/bin/ffmpeg.exe'
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-framerate',str(30/a.stride),'-i',str(staging/'%05d.png'),'-c:v','libx264','-threads','2','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(staging/'actual.mp4')],check=True)
        video=out/f'{a.label}.mp4';shutil.copyfile(staging/'actual.mp4',video)
    finally:shutil.rmtree(staging)
    manifest=dict(run=a.run,PC_only=True,source='Actual sequential Vulkan runtime captures; no interpolated frames',fps=30/a.stride,frames=evidence,video_sha256=sha(video))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1')/'Videos'/out.name
    nas.mkdir(parents=True,exist_ok=False)
    for src in out.iterdir():
        target=nas/src.name;shutil.copyfile(src,target);assert sha(target)==sha(src)
    print(json.dumps(dict(video=str(video),nas=str(nas/video.name),sha256=sha(video),sha256_verified=True)),flush=True)

if __name__=='__main__':main()
