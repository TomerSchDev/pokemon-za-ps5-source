"""Create an immutable full candidate from validated text and native UI overlays."""
import argparse,json,shutil
from pathlib import Path
from pack_translation import sha256
LAB=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--headers',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    if any(Path(v).name!=v for v in (a.base,a.headers,a.out)):raise ValueError('Folder names only')
    base=LAB/'build'/a.base;headers=LAB/'headers/build'/a.headers;out=LAB/'build'/a.out
    if out.exists():raise FileExistsError(out)
    coverage=json.loads((base/'coverage.json').read_text(encoding='utf-8'))
    if not coverage['complete'] or coverage['remaining_rows']:raise ValueError('Incomplete text baseline')
    checks=json.loads((headers/'verification.json').read_text(encoding='utf-8'))
    # Verify every baseline file against its recorded hash before any copying.
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:
        if sha256(base/f['path'])!=f['sha256']:raise ValueError('Baseline changed: '+f['path'])
    for r in checks:
        rel=Path(r['file']);src=headers/'mods/hebrew/romfs'/rel;old=base/'mods/hebrew/romfs'/rel
        if rel.is_absolute() or '..' in rel.parts or rel.parts[:2]!=('ui','data'):raise ValueError('Unexpected overlay path')
        if sha256(src)!=r['sha256']:raise ValueError('Overlay hash mismatch')
        if old.exists() and sha256(old)!=r['prior_sha256']:raise ValueError('Overlay baseline hash mismatch')
    shutil.copytree(base,out)
    for r in checks:
        dest=out/'mods/hebrew/romfs'/r['file'];dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(headers/'mods/hebrew/romfs'/r['file'],dest)
    for f in manifest['files']:
        if not f['path'].startswith('mods/hebrew/romfs/ui/') and sha256(out/f['path'])!=f['sha256']:
            raise ValueError('Text/font/validation changed during UI-only build')
    for suffix in ('.jsonl','-terms.tsv'):
        source=LAB/'translations'/(a.base+suffix);dest=LAB/'translations'/(a.out+suffix)
        if dest.exists():raise FileExistsError(dest)
        shutil.copyfile(source,dest)
    shutil.copyfile(headers/'native-text-review.json',out/'native-text-review.json')
    manifest.update(native_heading_archives=checks,native_image_text_build=a.headers,
                    complete_message_translation=True,
                    ui_only_revision_of=a.base,ui_text_baseline_manifest_sha256=sha256(base/'manifest.json'),
                    original_text_font_and_validation_identical=True,
                    visual_qa='Native preview inspection; matching PC run recorded separately')
    manifest['files']=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha256(p)) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json']
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(build=a.out,native_archives=len(checks),message_rows=coverage['changed_rows_with_hebrew'],text_font_and_validation_identical=True)))

if __name__=='__main__':main()
