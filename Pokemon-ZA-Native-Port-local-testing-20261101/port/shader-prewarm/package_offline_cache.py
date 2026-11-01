"""Package only validated absent SPIR-V keys and our reproducible tooling."""
import hashlib,json,shutil,time,zipfile
from datetime import datetime
from pathlib import Path
from forecast import ROOT
from translate_all import WORK
from install_offline_cache import TITLE,EBOOT_SHA256,validate_pack,file_digest


def main():
    ev=ROOT/'evidence/offline-shaders-20261028'
    assert file_digest(ROOT/'artifacts/randomizer-r15/PPSA91762/eboot.bin')==EBOOT_SHA256,'Build identity does not match r15 artifact'
    results=json.loads((ev/'compile-validation.json').read_bytes())
    assert results['complete']
    source_keys={json.loads(line)['key'] for line in (WORK/'translation-journal.jsonl').read_text().splitlines()
                 if json.loads(line).get('key')}
    assert source_keys=={r['key'] for r in results['files']}|{r['key'] for r in results['failures']},'Incomplete compile queue'
    rows=[r for r in results['files'] if not r['previous_key']]
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    dest=ROOT/'deliverables'/('ZA-Offline-Shaders-'+stamp);dest.mkdir()
    manifest=dict(schema=1,title=TITLE,eboot_sha256=EBOOT_SHA256,raw_shaderc_results=True,
        game_build_id='b1f12fd919eae86ab8a978317677e64bce443d1f',compiler=results['compiler'],target=results['target'],
        generated=stamp,files=rows,bytes=sum(r['bytes'] for r in rows),
        note='Additive shipped cache only. Runtime adds vertex NoContraction. Driver pipelines are not included.')
    archive=dest/('ZA-r15-Offline-SPIRV-'+stamp+'.zip')
    working=WORK/(archive.name+'.building')
    last=time.monotonic()
    with zipfile.ZipFile(working,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        for i,row in enumerate(rows):
            p=WORK/'compiled'/(row['key']+'.spv');data=p.read_bytes()
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['spv_sha256']
            z.writestr('cache/spirv/'+p.name,data)
            if time.monotonic()-last>15:
                print(f'Packaged {i+1}/{len(rows)}',flush=True);last=time.monotonic()
    validate_pack(working)
    expected=file_digest(working)
    shutil.copyfile(working,archive)
    assert file_digest(archive)==expected,'Package copy mismatch'
    working.unlink()
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
    shutil.copy2(Path(__file__).with_name('install_offline_cache.py'),dest/'install_offline_cache.py')
    with zipfile.ZipFile(dest/'Offline-Shader-Tools.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(__file__).parent.iterdir()):
            if p.is_file() and (p.suffix in ('.py','.c','.h','.sh','.txt') or p.name=='CMakeLists.txt'):
                z.write(p,'port/shader-prewarm/'+p.name)
        for name in ('bnsh-scan-all.json','exefs-containers.json','translation.json','compile-validation.json',
                     'tool-verification.json','audit-merge.json','audit-coverage.json','audit-coverage.txt',
                     'audit-extra-sources.json','audit-inventory.json'):
            p=ev/name
            if p.exists():z.write(p,'evidence/'+name)
    receipt=dict(complete=True,path=str(dest),archive=str(archive),new_files=len(rows),
        validated_total=len(results['files']),uncompressed_bytes=manifest['bytes'],compressed_bytes=archive.stat().st_size,
        sha256=file_digest(archive),compiler_failures=len(results['failures']),console_uploaded=False)
    (dest/'PACKAGE-VERIFIED.json').write_text(json.dumps(receipt,indent=2))
    (ev/'package.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2),flush=True)


if __name__=='__main__':main()
