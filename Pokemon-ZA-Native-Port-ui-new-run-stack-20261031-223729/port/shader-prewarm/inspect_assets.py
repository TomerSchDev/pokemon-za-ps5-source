"""Bounded, read-only model/shader catalogue audit. Names are candidates, not proven bindings."""
from pathlib import Path
import argparse, collections, hashlib, json, re, sys
from forecast import DEFAULT_PC

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pc', type=Path, default=DEFAULT_PC)
p.add_argument('--out', type=Path, required=True)
args = p.parse_args()
sys.path.insert(0, str(args.pc/'randomizer-lab'))
from inspect_game import Game
g = Game(args.pc/'update-2.0.2-20261025/game/romfs.bin', args.pc/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
forecast = json.loads((args.out/'area-forecast.json').read_bytes())
first = next(x for x in forecast['groups'] if x['id']=='a0102_w01')
candidate_models = []
for species in first['species_forms']:
    tokens = {f'pm{n:04}' for n in (species['species'], species['national'])}
    packs = [n for n in g.names if any(t in n for t in tokens)]
    candidate_models.append(dict(species=species['species'], national=species['national'],
        name=species['name'], form=species['form'], candidates=packs,
        qualification='Filename candidates only; internal/national/model/form mapping not yet verified.'))
shader_pattern = re.compile(r'shader|\.bnsh|\.bfsha|\.sharc|\.sharcfb|\.nvsd', re.I)
loose = [dict(path=n, bytes=size) for n, (_, size) in g.entries.items() if shader_pattern.search(n)]
packs = [n for n in g.names if shader_pattern.search(n)]
samples = []
# Goodra is the verified seed's early rock provider. Limit work explicitly.
for pack in [p for p in g.packs if 'pm0706' in p['name']][:8]:
    for record in pack['files'][:8]:
        if record['size'] > 2 << 20:
            continue
        data = g.unpack(record)
        strings = sorted({m.group().decode() for m in re.finditer(rb'[ -~]{5,}', data)
            if re.search(rb'trmdl|trmtr|trmdt|shader|material|\.bnsh|\.bfsha|\.bntx', m.group(), re.I)})
        samples.append(dict(pack=pack['name'], file_hash=record['hash'], bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), candidate_strings=strings[:100]))
result = dict(build_id=forecast['build_id'], romfs_file_count=len(g.entries), pack_count=len(g.names),
    first_zone_models=candidate_models, loose_shader_candidates=loose, packed_shader_candidates=packs,
    goodra_samples=samples, limits=['No model-to-material-to-Maxwell binding has been proved by this name/string audit.',
        'No game files are changed or exported; this output contains identifiers, sizes and hashes only.'])
(args.out/'asset-audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(dict(packs=len(g.names), loose_shader_candidates=loose[:20], packed_shader_candidates=packs[:12],
    models=[dict(name=x['name'], candidates=len(x['candidates'])) for x in candidate_models], goodra_samples=samples[:8]), indent=2))
