"""Turn a pinned BUILD-INFO (input_pins in link order) into the base spec build-r29-hebrew.sh links on.

    python3 base_from_build_info.py BUILD-INFO.json PIE ARCHIVE_SHA256 FLAGS_FROM_LINK_INPUTS OUT.json
The link flags are not files: they come from an earlier link-inputs.txt of the same line, its paths replaced in order.
"""
import hashlib,json,sys
from pathlib import Path
info,pie,archive_sha,flags_from,out=sys.argv[1:6]
b=json.loads(Path(info).read_text())
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
pins=b['input_pins']
for p in pins:
    assert sha(p['path'])==p['sha256'],'input changed since its build: '+p['path']
paths=[p['path'] for p in pins]
archive=paths[-1]; assert archive.endswith('.a') and sha(archive)==archive_sha,'last pin must be the pinned game archive'
runtime=[p for p in paths[:-1] if '/build/ps5/rt/' in p]
extras=[p for p in paths[:-1] if '/build/ps5/rt/' not in p]
assert paths[:-1]==runtime+extras,'runtime objects must precede the extra inputs'
# Flags sit between the paths (--wrap groups, --start-group ...): keep the earlier string token for token and
# substitute its paths, in order, with this build's pinned inputs (same file names required).
tokens=Path(flags_from).read_text().strip().split(' ');queue=list(extras)
for i,token in enumerate(tokens):
    if token.startswith('/'):
        new=queue.pop(0);assert Path(new).name==Path(token).name,(token,new);tokens[i]=new
assert not queue,'unplaced inputs: '+' '.join(queue)
spec=dict(eboot_sha256=b['eboot_sha256'],pie=pie,pie_sha256=b['pie_sha256'],runtime=runtime,
          extra=' '.join(tokens),archive=archive,archive_sha256=archive_sha,source_build_info=info)
assert sha(pie)==spec['pie_sha256']
Path(out).write_text(json.dumps(spec,indent=1)+'\n')
print(json.dumps({k:(v if not isinstance(v,list) else len(v)) for k,v in spec.items() if k!='extra'}))
