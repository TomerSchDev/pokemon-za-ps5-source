"""Record inspected contact sheets and genuine visual defects separately from pixel motion."""
import argparse,json
from run_pc_gallery import QA

p=argparse.ArgumentParser();p.add_argument('batch',type=int);p.add_argument('prefix');p.add_argument('--framing',type=int,nargs='*',default=[]);args=p.parse_args()
assert 1<=args.batch<=10
directory=QA/'wide/reviews'
assert (directory/(args.prefix+'-sources.json')).exists()
assert len(list(directory.glob(args.prefix+'-box*.jpg')))==(1 if args.batch==10 else 3)
path=QA/'wide/visual-review-r1.json';value=json.loads(path.read_text(encoding='utf-8'))
value['reviewed_import_batches']=sorted(set(value['reviewed_import_batches'])|{args.batch})
value['latest_sheets'][str(args.batch)]=args.prefix
known={x['species'] for x in value['summary_framing_needs_review']}
value['summary_framing_needs_review'] += [{'species':n,'finding':'Model extends beyond the Summary frame. World-scale behavior has not been established.'} for n in args.framing if n not in known]
if args.batch==5:
    value['unresolved_visual_model_issues']=[
        {'key':'0494-00-0','finding':'Victini appears extremely small with detached dark fragments; geometry/pose/effect visibility needs diagnosis.','run':'pc-wide-import-005-r1-s02'},
        *[{'key':'%04d-00-0'%n,'finding':'Unexpected pink fur/body palette in the normal-color capture. The initial static-layer hypothesis did not apply; no validated color repair has been published.','run':'pc-wide-import-005-r1-s02'} for n in (506,507,508)]]
    value['pending_transparency_validation']=['0442-00-0']
if args.batch==9:
    value['summary_normalizes_imported_forms']=sorted(set(value.get('summary_normalizes_imported_forms',[]))|{'0888-01-0','0889-01-0','0964-01-0'})
if args.batch==6:
    value['additional_palette_or_material_review']=[{'national':n,'finding':'Color/material fidelity needs comparison against the supplied source assets; strong pink tint or flat reflective surfaces were observed in the contact sheets.'} for n in (554,555,567,621,631,993)]
if args.batch==7:
    issues=value.setdefault('unresolved_visual_model_issues',[])
    if not any(t['key']=='0755-00-0' for t in issues):issues.append({'key':'0755-00-0','finding':'Morelull mushroom caps render as a solid black silhouette; material appearance needs repair.','run':'pc-wide-import-007-r1-s02'})
    value['additional_palette_or_material_review'] += [{'national':n,'finding':'Normal-palette mask/shell colors appear tinted; source material fidelity needs closer comparison.'} for n in (772,776)]
path.write_text(json.dumps(value,indent=1),encoding='utf-8')
print('Recorded visual review of imported batch',args.batch)
