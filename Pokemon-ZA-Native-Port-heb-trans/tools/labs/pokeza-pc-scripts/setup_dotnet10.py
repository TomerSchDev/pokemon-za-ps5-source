from pathlib import Path
import urllib.request,json,hashlib,zipfile
root=Path(__file__).resolve().parents[2]/'tools/dotnet10'
root.mkdir(parents=True,exist_ok=True)
metadata=json.load(urllib.request.urlopen('https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json'))
sdk=metadata['releases'][0]['sdk']
item=next(x for x in sdk['files'] if x['rid']=='win-x64' and x['name'].endswith('.zip'))
p=root/item['url'].rsplit('/',1)[-1]
if not p.exists():urllib.request.urlretrieve(item['url'],p)
with p.open('rb') as f:actual=hashlib.file_digest(f,'sha512').hexdigest()
assert actual.lower()==item['hash'].lower()
(root/'provenance.json').write_text(json.dumps(dict(version=sdk['version'],url=item['url'],sha512=actual),indent=2))
with zipfile.ZipFile(p) as z:
    for name in z.namelist():
        target=(root/name).resolve()
        if not target.is_relative_to(root.resolve()):raise ValueError('Unsafe SDK archive member')
    z.extractall(root)
print(sdk['version'],flush=True)
