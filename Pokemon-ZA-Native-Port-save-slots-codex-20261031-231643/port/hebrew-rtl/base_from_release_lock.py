"""Turn a za release lock (tools/za/releases/<name>.lock.json) into the base spec build-r29-hebrew.sh links on.

    python3 base_from_release_lock.py main-1.0.1 LINK_TITLE_TREE OUT.json
LINK_TITLE_TREE: a source root holding tools/ps5/link-title.sh of the release's runtime commit (the frozen folder keeps
objects only), e.g. /home/tomer/ps5-za-native/main-1.0.1-build-20261031-05/release/source. Every pinned input is
re-hashed here; the runtime objects and extra inputs keep the lock's link order.
"""
import hashlib, json, shlex, sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
native = '/home/tomer/ps5-za-native'
name, tree, out = sys.argv[1:4]
lock = json.loads((repo / 'tools/za/releases' / (name + '.lock.json')).read_text(encoding='utf-8'))
p = lock['profiles'][name]
x = lambda t: t.replace('{native}', native).replace('{repo}', str(repo))


def sha(f):
    with open(f, 'rb') as h:
        return hashlib.file_digest(h, 'sha256').hexdigest()


for token in p['inputs'] + list(p['references'].values()):
    if token.startswith('{native}'):
        assert sha(x(token)) == lock['files'][token]['sha256'], 'pinned input changed: ' + token
lt = Path(tree) / 'tools/ps5/link-title.sh'
spec = dict(release=name, eboot_sha256=lock['files'][p['references']['eboot']]['sha256'],
            pie=x(p['references']['pie']), pie_sha256=lock['files'][p['references']['pie']]['sha256'],
            runtime=[x(t) for t in p['runtime']], extra=shlex.join(x(t) for t in p['extra']),
            archive=x(p['archive']), archive_sha256=lock['files'][p['archive']]['sha256'],
            src_tree=str(tree), link_title_sha256=sha(lt), facade=True, verifiers='repo',
            source_lock=f'tools/za/releases/{name}.lock.json', source_lock_sha256=sha(repo / 'tools/za/releases' / (name + '.lock.json')))
Path(out).write_text(json.dumps(spec, indent=1) + '\n')
print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in spec.items() if k != 'extra'}, indent=1))
