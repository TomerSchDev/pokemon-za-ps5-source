"""Control experiment: unchanged native ZA geometry, only material serialization round-tripped."""
from pathlib import Path
import shutil
import sys
from catalog_inventory import LAB
from build_smoliv_model import schema,encode_checked

out=Path(sys.argv[1])
shutil.copytree(LAB/'pilot/build/step1/species-pilot',out/'mods/native-material-control')
for file in (out/'mods').rglob('*.trmtr'):
    s=schema('trmtr')
    file.write_bytes(encode_checked(s,s.decode(file.read_bytes())))
print('Native geometry/material serialization control prepared',flush=True)
