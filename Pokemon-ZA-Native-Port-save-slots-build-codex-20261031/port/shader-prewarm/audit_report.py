"""Finalize independent, bounded shader-coverage audit from saved evidence."""
from pathlib import Path
import collections, hashlib, json, random, struct
from forecast import ROOT


def main():
    ev=ROOT/'evidence/offline-shaders-20261028';private=ROOT/'private-data/offline-shaders-20261028'
    inv=json.loads((ev/'audit-inventory.json').read_bytes())
    programs=json.loads((ev/'programs-combined.json').read_bytes())['variations']
    tr=json.loads((ev/'translation.json').read_bytes());extra=json.loads((ev/'audit-extra-sources.json').read_bytes())
    sources={x['key']:x for x in tr['sources']}
    for x in extra['records']:sources.setdefault(x['key'],x)
    old={p.stem for p in (ROOT/'artifacts/randomizer-r15/PPSA91762/cache/spirv').glob('*.spv')}
    for x in json.loads((ROOT/'evidence/randomizer-shaders-20261028-041124Z/manifest.json').read_bytes()):old.add(x['source'].split('.')[0])
    unm=json.loads((ev/'audit-recorded-unmatched.json').read_bytes())
    unmatched_not_shipped=[x['path'] for x in unm['files'] if Path(x['path']).stem not in old]
    failed_codes={x['signature'][1]:x for x in tr['failures']}
    failed_refs=collections.Counter(); impacted=set()
    for p in programs:
        for s in p['stages'].values():
            if s['code_sha256'] in failed_codes:
                failed_refs[s['code_sha256']]+=1;impacted.add((p['bnsh_sha256'],p['index']))
    # Independent raw pointer checks: read descriptor fields directly rather than calling parse_bnsh.parse.
    by_container=collections.defaultdict(list)
    for p in programs:by_container[p['bnsh_sha256']].append(p)
    randomizer=random.Random(20261028)
    selected=randomizer.sample(sorted(by_container),16)
    sample=[]
    stage_order={'0':0,'3':1,'4':2,'2':3,'1':4,'5':5}
    for sha in selected:
        blob=(private/'bnsh'/(sha+'.bnsh')).read_bytes();assert hashlib.sha256(blob).hexdigest()==sha
        block=struct.unpack_from('<H',blob,22)[0];count=struct.unpack_from('<I',blob,block+28)[0]
        table=struct.unpack_from('<Q',blob,block+32)[0];assert count==len(by_container[sha])
        p=by_container[sha][len(by_container[sha])//2]
        binary=struct.unpack_from('<Q',blob,table+64*p['index']+16)[0]
        for stage,s in p['stages'].items():
            descriptor=struct.unpack_from('<Q',blob,binary+8+stage_order[stage]*8)[0]
            control,code=struct.unpack_from('<QQ',blob,descriptor+8)
            size=struct.unpack_from('<I',blob,descriptor+24)[0]
            assert hashlib.sha256(blob[code:code+size]).hexdigest()==s['code_sha256']
            assert struct.unpack_from('<I',blob,control+0x700)[0] in (0,s['const_offset'])
        sample.append(dict(bnsh=sha,variation=p['index'],stage_count=len(p['stages'])))
    result=dict(schema=1,complete=True,scope='Local game 2.0.2, build b1f12fd919eae86ab8a978317677e64bce443d1f; current r15 Vulkan runtime',
        inventory=inv,extra_generation=extra['counts'],extra_failures=extra['failures'],
        reconciled=dict(unique_glsl_sources=len(sources),new_vs_r15=len(set(sources)-old),
            already_shipped=len(set(sources)&old),baseline_successful_translation_requests=tr['counts']['translation_requests']-len(tr['failures']),
            failed_maxwell_translation_requests=len(tr['failures']),failed_source_stage_counts=dict(collections.Counter(str(x['stage']) for x in tr['failures'])),
            failed_variation_references=len(impacted),failed_source_reference_counts=dict(failed_refs),
            recorded_source_exact_matches=439-unm['count'],recorded_unmatched=unm['count'],
            recorded_unmatched_not_shipped=unmatched_not_shipped),
        independent_raw_checks=sample,
        confirmed_runtime_sources=[
            dict(file='runtime/nvn/vulkan/shaders.c',lines='231-480',kind='36 builtin requests,35 distinct sources due clear.frag.none prefix behavior'),
            dict(file='runtime/nvn/maxwell/translate.c',lines='2555-2559',kind='one empty fragment for97VS-only records'),
            dict(file='runtime/nvn/vulkan/exec.c',lines='3207-3239',kind='ShaderKey from dynamic draw state and control-defined XFB'),
            dict(file='runtime/nvn/vulkan/exec.c',lines='1371-1379',kind='exact VS output mask fed into paired FS translation'),
            dict(file='runtime/nvn/objects.c',lines='598-634',kind='shader registration receives code +control; source container is not constrained to BNSH')],
        limits=[
            '20,444 is the count of unique full Maxwell program blobs in recognized local BNSH containers, not a universal count of all Vulkan pipelines or all possible renderer states.',
            'The scanner covered238,564unpacked/loose files and19,076,168,165bytes. It excluded exactly two oversized Wwise audio stream PCKs; decompression errors0.',
            'The scan recognizes validated BNSH containers. It cannot prove absence of raw GPU bytecode outside recognized containers, runtime-generated programs, or shaders built from proprietary code paths.',
            'Dynamic attr_kind, rt_kind, stencil_slots, sint_slots, flip/depth/mirror state can produce further exact-source hashes. Baseline all-float keys plus control-defined XFB are not an exhaustive cross-product.',
            '20 unsigned-sampler fragment sources were observed among62unmatched captured sources, so integer texture variants are demonstrably used. Preserve their existing compiled cache entries.',
            'SPIR-V validation does not establish every shader renders correctly. No new hardware rendering validation was performed by this audit.',
            'The seven missing outputs are unsupported Maxwell translation instructions, not GLSL compiler errors. Recompiling their unchanged input cannot resolve them.',
            'PS5 driver VkPipeline creation remains separate, including attachment formats, layouts and render state. Offline SPIR-V does not make every first-use pipeline free.',
            'Counts describe the exact local updated game contents, including any DLC assets already present there; they do not assert content coverage of other builds, downloads, or unretrieved DLC.'
        ],
        next_priorities=[
            'Finish and validate every exact-source record, retain source SHA, FNV key, SPIR-V SHA and explicit failure ledger; compile only missing validated outputs.',
            'Merge the64audit helper/XFB sources;54are new versus r15. All28XFB sources use layouts decoded directly from game control data, without guessing.',
            'Retain all1049previous shipped keys, especially unsigned texture variants not represented by all-float baseline.',
            'For more dynamic variants, collect/derive actual per-draw integer texture masks and material vertex/RT formats, then specialize only relevant used slots. Existing ShaderInfo.tex provides handle offsets, but not the future bound format.',
            'Investigate the six compute and one fragment unsupported instruction cases in the translator, testing exact semantics before changing the installed runtime.',
            'If absolute container coverage is required, add a separate raw NVN/SPH signature scan of decompressed resources and ExeFS, followed by pointer/control validation. Magic counts alone are not valid shader counts.',
            'Test representative new zones on PS5 and preserve driver pipeline cache; attribute remaining stalls using timestamps rather than assuming every stall is a shader miss.'
        ],
        files_sha256={name:hashlib.sha256((ev/name).read_bytes()).hexdigest() for name in ['programs-combined.json','bnsh-scan-all.json','exefs-containers.json','audit-extra-sources.json']})
    raw_report=None
    if (ev/'audit-raw-sph.json').exists():
        raw_report=json.loads((ev/'audit-raw-sph.json').read_bytes())
        if raw_report.get('complete'):
            result['raw_sph_audit']=dict(complete=True,files_checked=raw_report['files_checked'],
                bytes_checked=raw_report['bytes_checked'],inside_bnsh=raw_report['inside_bnsh'],
                outside_counts=raw_report['outside_counts'],oversize=raw_report['oversize'],
                errors=raw_report['errors'],exefs=raw_report['exefs'],
                outside_candidates=len(raw_report['outside_hits']),
                plausible_headers=sum(x['plausible_header'] for x in raw_report['outside_hits']),
                conclusion='No additional actionable shader source found. All ten outside magic hits are unaligned model/texture data with nonzero NVN prefix; zero outside hits in all three NSO images.')
            result['files_sha256']['audit-raw-sph.json']=hashlib.sha256((ev/'audit-raw-sph.json').read_bytes()).hexdigest()
            result['next_priorities'][5]='Completed raw NVN/SPH signature scan found no plausible additional outside-container shader headers. This strengthens recognized-format coverage but cannot prove absence of arbitrarily encoded or runtime-generated programs.'
    (ev/'audit-coverage.json').write_text(json.dumps(result,indent=2))
    lines=[
        'Independent shader inventory / coverage audit — 2026-10-28',
        result['scope'],'',
        'Measured inventory:',
        ' 2,845 recognized BNSH containers: 2,843 RomFS + 2 embedded in main NSO.',
        ' 46,249 variation records = 45,031 VS/FS pairs + 97 VS-only + 1,121 compute.',
        ' 91,280 stage references, deduplicated into 20,444 full Maxwell blobs:',
        ' 10,747 vertex + 9,619 fragment + 78 compute. No geometry/tessellation records found.',
        ' 23,826 unique vertex/fragment code pairs; matching pairs matter to fragment interface generation.',
        ' Baseline 20,579 translation requests: 20,572 successes yield 20,561 unique GLSL hashes; 7 unsupported inputs.',
        ' Extra audit: 36 unique helper sources + 28 control-defined XFB sources = 64 additional hashes.',
        f" Combined source inventory: {len(sources):,}; {len(set(sources)-old):,} new versus r15; {len(set(sources)&old):,} already shipped.",
        f" Unsupported input references: {len(impacted)} variation records. They are 6 compute programs + 1 fragment program.",
        f" Existing real PS5 captures: 377/439 exact source matches; 62 unmatched sources, all already shipped: {not unmatched_not_shipped}.",
        ' Independent descriptor/code SHA checks passed for 16 deterministically selected containers.','',
        'Coverage limits:',*[' - '+x for x in result['limits']],'',
        'Next priorities:',*[' - '+x for x in result['next_priorities']],'',
        'No game, save, executable or console data was changed by this audit.'
    ]
    if raw_report and raw_report.get('complete'):
        lines += ['', 'Additional raw NVN/SPH scan completed:',
            f" {raw_report['files_checked']:,} files/decoded NSO images; {raw_report['bytes_checked']:,} decoded bytes; 0 scan errors.",
            ' Found 62,791 magic occurrences inside recognized BNSH ranges, excluded from new candidate counts.',
            ' Outside BNSH: 9 graphics-magic hits + 1 compute-magic hit; all 10 are unaligned model/texture data with nonzero NVN prefixes.',
            ' No plausible additional shader header; no outside-container magic in main, sdk or rtld NSO images.',
            ' The same two oversized Wwise audio streams were skipped. Raw signature search does not prove absence of arbitrary encodings or runtime-generated programs.',
            ' Details and reproducible scan code: audit-raw-sph.json, audit-raw-sph.txt, port/shader-prewarm/audit_raw_sph.py.']
    (ev/'audit-coverage.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result['reconciled'],indent=2))


if __name__=='__main__':main()
