"""Read-only scan of decompressed NSOs for embedded BNSH archives."""
import hashlib, json, sys
from forecast import ROOT, DEFAULT_PC
from extract_bnsh import bnsh_headers
from parse_bnsh import parse


def main():
    sys.path.insert(0, str(DEFAULT_PC.parent/'pokeza-recomp/tools'))
    from nso import Nso
    private = ROOT/'private-data/offline-shaders-20261028'
    evidence = ROOT/'evidence/offline-shaders-20261028'
    known = {p.stem for p in (private/'bnsh').glob('*.bnsh')}
    report = []; records = []
    for name in ('main', 'sdk', 'rtld'):
        path = DEFAULT_PC/'update-2.0.2-20261025/game/exefs'/name
        nso = Nso(path)
        for offset, size, count in bnsh_headers(nso.image):
            blob = nso.image[offset:offset+size]
            digest = hashlib.sha256(blob).hexdigest()
            item = dict(nso=name, nso_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        offset=offset, bytes=size, variations=count, sha256=digest,
                        already_in_romfs=digest in known)
            report.append(item)
            dest = private/'bnsh'/(digest+'.bnsh')
            if dest.exists():
                assert hashlib.sha256(dest.read_bytes()).hexdigest() == digest
            else:
                dest.write_bytes(blob)
            if digest in known:
                continue
            for variation in parse(blob):
                for stage in variation['stages'].values():
                    for key, suffix in (('code','bin'), ('control','ctl')):
                        dest = private/'programs'/(stage[key+'_sha256']+'.'+suffix)
                        if dest.exists():
                            assert hashlib.sha256(dest.read_bytes()).hexdigest() == stage[key+'_sha256']
                        else:
                            dest.write_bytes(stage[key])
                        del stage[key]
                records.append(dict(bnsh_sha256=digest, **variation))
            known.add(digest)
    (evidence/'exefs-containers.json').write_text(json.dumps(report,indent=2))
    (evidence/'programs-exefs.json').write_text(json.dumps(dict(schema=1,variations=records),indent=2))
    print(json.dumps(dict(containers=report,new_variations=len(records)),indent=2))


if __name__ == '__main__':
    main()
