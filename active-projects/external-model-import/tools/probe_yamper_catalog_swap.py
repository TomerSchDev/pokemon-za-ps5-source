"""PC diagnostic: cross-swap only the resource catalogue entries for 706 and 835."""
from pathlib import Path
import copy,json
from build_smoliv_model import Z,encode_checked
from integrate_model_assets import atomic

def main():
    work=Path(__file__).resolve().parents[3]/'pc-fifty-20261031-r1'
    rel=Path('ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
    s=Z.catalog_schema();table=s.decode((work/'mods/00-icon-identity-r2/romfs'/rel).read_bytes())
    def idx(n):
        result=[i for i,r in enumerate(table['table']) if r['species_info'].get('species',0)==n and not r['species_info'].get('form',0) and not r['species_info'].get('gender',0)]
        assert len(result)==1;return result[0]
    a,b=idx(706),idx(835);old={706:copy.deepcopy(table['table'][a]),835:copy.deepcopy(table['table'][b])}
    for target,source,i in ((706,835,a),(835,706,b)):
        row=copy.deepcopy(old[source]);row['species_info']=old[target]['species_info'];row['icon_path']=old[target]['icon_path'];table['table'][i]=row
    overlay=work/'mods/00-ablation-yamper-goodra-r2/romfs'
    atomic(overlay/rel,encode_checked(s,table))
    atomic(work/'yamper-goodra-catalog-swap-r2.json',json.dumps(dict(PC_only=True,diagnostic_only=True,QA_pass_allowed=False,original=old,
        replacement={706:table['table'][a],835:table['table'][b]}),indent=1).encode())
    print(json.dumps(dict(overlay=str(overlay),QA_pass_allowed=False)),flush=True)

if __name__=='__main__':main()
