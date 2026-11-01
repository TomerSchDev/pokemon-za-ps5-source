"""Independent inventory reconciliation; read-only inputs, audit-prefixed outputs."""
import collections, hashlib, json, struct
from pathlib import Path
from forecast import ROOT


def main():
    ev=ROOT/'evidence/offline-shaders-20261028'
    raw=ROOT/'private-data/offline-shaders-20261028/programs'
    programs=json.loads((ev/'programs-combined.json').read_bytes())['variations']
    tr=json.loads((ev/'translation.json').read_bytes())
    stages=collections.Counter();unique=collections.defaultdict(set);stage_shapes=collections.Counter()
    codes=set();stage_code_const=set();controls={};xfb={};xfb_refs=0;pair_codes=set();missing=0
    for p in programs:
        ss=p['stages'];stage_shapes[','.join(sorted(ss))]+=1
        if not ss:missing+=1
        for stage,s in ss.items():
            stages[stage]+=1;unique[stage].add(s['code_sha256']);codes.add(s['code_sha256'])
            stage_code_const.add((stage,s['code_sha256'],s['const_offset']))
        if '0' in ss and '1' in ss:
            pair_codes.add((ss['0']['code_sha256'],ss['1']['code_sha256']))
        if '0' not in ss:continue
        s=ss['0'];ctl=s['control_sha256']
        if ctl not in controls:
            blob=(raw/(ctl+'.ctl')).read_bytes()
            assert hashlib.sha256(blob).hexdigest()==ctl
            counts=[struct.unpack_from('<I',blob,0x4DC+0x80*b)[0]&255 for b in range(4)]
            strides=[struct.unpack_from('<H',blob,0x6DC+2*b)[0] for b in range(4)]
            controls[ctl]=(counts,strides)
        counts,strides=controls[ctl]
        if not any(counts):continue
        xfb_refs+=1
        key=(s['code_sha256'],s['const_offset'],*counts,*strides)
        if key not in xfb:
            xfb[key]=dict(**s,xfb_count=counts,xfb_stride=strides,bnsh=p['bnsh_sha256'],variation=p['index'])
    scan=json.loads((ev/'bnsh-scan-all.json').read_bytes())
    extras=json.loads((ev/'exefs-containers.json').read_bytes())
    result=dict(romfs_scan=dict(complete=scan['complete'],files=scan['files_checked'],bytes=scan['bytes_checked'],
        errors=scan['errors'],skipped=scan['oversize'],unique_containers=len(scan['containers']),
        container_occurrences=sum(len(x['sources']) for x in scan['containers'])),
        exefs_containers=len(extras),total_containers=len({p['bnsh_sha256'] for p in programs}),
        variation_records=len(programs),stage_references=dict(stages),stage_shapes=dict(stage_shapes),
        total_stage_references=sum(stages.values()),unique_full_code_blobs=len(codes),
        unique_code_blobs_by_stage={k:len(v) for k,v in unique.items()},
        unique_stage_code_const=len(stage_code_const),unique_vs_fs_code_pairs=len(pair_codes),
        missing_binary_variations=missing,baseline_translation=tr['counts'],translation_failures=tr['failures'],
        xfb=dict(variation_refs=xfb_refs,unique_layout_variants=len(xfb),
        distinct_layouts=len({tuple(x['xfb_count']+x['xfb_stride']) for x in xfb.values()})))
    (ev/'audit-inventory.json').write_text(json.dumps(result,indent=2))
    (ev/'audit-xfb-inputs.json').write_text(json.dumps(list(xfb.values()),indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('romfs_scan','translation_failures')},indent=2))


if __name__=='__main__':main()
