"""Resolve Sword icons through the source species catalogue, not national IDs."""
from functools import lru_cache
from pathlib import PurePosixPath
import re
from catalog_inventory import SWORD, catalogue


@lru_cache(maxsize=1)
def source_rows():
    return catalogue((SWORD/'bin/pokemon/table/poke_resource_table.gfbpmcatalog').read_bytes(), 'sword')


def resolve(national, form=0, gender=0):
    rows = [r for r in source_rows()
            if r['info'].get('species', 0) == national
            and r['info'].get('form', 0) == form
            and not r['info'].get('shiny', 0)]
    rows.sort(key=lambda r: r['info'].get('gender', 0) != gender)
    for row in rows:
        model = PurePosixPath(row['model']).stem
        match = re.fullmatch(r'pm(\d{4})_(\d{2})(?:_\d{2})?', model)
        if not match:
            raise ValueError('Unrecognized Sword model name: '+model)
        resource, model_form = match.groups()
        # Model variants (e.g. Darmanitan's 11/12) are not icon form numbers.
        icon_form = f"{row['info'].get('form', 0):02d}"
        for letter in (('f', 's', 'm', 'n') if gender else ('s', 'm', 'n', 'f')):
            path = SWORD/f'bin/appli/icon_pokemon/poke_icon_{resource}_{icon_form}{letter}_n.bntx'
            if path.is_file():
                return path, dict(species_info=row['info'], source_model=row['model'],
                                  resource_id=int(resource), resource_form=int(icon_form), model_form=int(model_form))
    raise FileNotFoundError(f'No catalog-mapped Sword icon for {national}/{form}/{gender}')
