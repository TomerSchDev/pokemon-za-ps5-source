"""Do not accept a --gc-sections title that lost runtime registrations."""
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('elfcheck',Path(__file__).resolve().parents[1]/'shader-probe-r18/verify-image.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
before,after=map(m.Elf,sys.argv[1:3])
checks=[]
for name in ('hle_impls','services','resets'):
    b,a=before.sections[name],after.sections[name]
    assert a[5]==b[5] and a[5]>0,(name,b[5],a[5])
    checks.append(dict(section=name,baseline_bytes=b[5],candidate_bytes=a[5],preserved_count=True))
print(json.dumps(checks,indent=2))
