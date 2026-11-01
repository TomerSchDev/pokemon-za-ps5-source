"""Remove only missing, optional modules inherited from an unrelated native donor."""
from pathlib import Path
import json
from build_smoliv_model import encode_checked

OPTIONAL_DONOR_MODULES={'body_shape_modifier','model_attach_effect','unit_operator','spine','slot'}

def strip_missing_optional_modules(raw,existing,sc):
    value=sc.decode(raw);removed=[];unexpected=[]
    for entry in value['list']:
        filename=entry['filename'];assert Path(filename).name==filename
        if filename in existing:continue
        if entry['animation_name'] in OPTIONAL_DONOR_MODULES:removed.append(entry)
        else:unexpected.append(entry)
    if unexpected:raise ValueError('Unexpected missing native modules: '+json.dumps(unexpected))
    if not removed:return raw,[]
    value['list']=[e for e in value['list'] if e not in removed]
    return encode_checked(sc,value),removed
