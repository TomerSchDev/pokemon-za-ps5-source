from pathlib import Path
import argparse,importlib.util,shutil
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('nso',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location('patcher',Path(__file__).parents[1]/'prepare-money-hooks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a.out.mkdir(parents=True,exist_ok=False);src=a.out/'source';src.mkdir()
for name in m.EXPECTED:shutil.copy2(a.source/name,src/name)
report=m.prepare(src,a.nso,a.out/'positive');assert m.prepare(src,a.nso,a.out/'positive')==report
for name in m.EXPECTED:assert m.sha((src/name).read_bytes())==m.EXPECTED[name]
def rejects(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('unapproved input/output accepted')
rejects(lambda:m.prepare(src,a.nso,src))
first=next(iter(m.EXPECTED));(src/first).write_bytes((src/first).read_bytes()+b'\n')
rejects(lambda:m.prepare(src,a.nso,a.out/'bad-source'));assert not (a.out/'bad-source').exists()
shutil.copy2(a.source/first,src/first)
bad=a.out/'bad.nso';bad.write_bytes(b'NSO0'+b'\0'*128)
rejects(lambda:m.prepare(src,bad,a.out/'bad-id'));assert not (a.out/'bad-id').exists()
(a.out/'positive'/first).write_bytes(b'keep me')
rejects(lambda:m.prepare(src,a.nso,a.out/'positive'));assert (a.out/'positive'/first).read_bytes()==b'keep me'
print('PASS: exact hashes/build ID; idempotence; baseline unchanged; alias/corrupt/unknown build/nonidentical output rejected')
