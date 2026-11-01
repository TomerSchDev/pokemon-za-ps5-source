import json
from run_pc_gallery import QA
from catalog_inventory import Z
value=Z.catalog_schema().decode((QA/'form-bindings-r1/romfs'/Z.CATALOG).read_bytes())
for entry in value['table']:
    info=entry['species_info']
    if info.get('species') in (3,421) and info.get('gender',0)==0:
        print(json.dumps(entry))
