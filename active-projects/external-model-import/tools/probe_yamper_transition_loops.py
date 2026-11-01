"""PC diagnostic: give one-shot controller tracks non-looping copies of their source clip."""
from pathlib import Path
import argparse,hashlib,json,os,struct
from build_smoliv_model import schema,encode_checked,Z
from source_archives import FB
from integrate_model_assets import atomic


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--national',type=int,default=835)
    parser.add_argument('--inspect-only',action='store_true')
    parser.add_argument('--mods-root',type=Path)
    parser.add_argument('--only-transitions',action='store_true')
    parser.add_argument('--audit-contract',action='store_true')
    parser.add_argument('--effect-track')
    parser.add_argument('--match-native-contract',action='store_true')
    parser.add_argument('--alias-only',action='store_true')
    a=parser.parse_args()
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    selected=next(t for t in json.loads((work/'selection.json').read_text(encoding='utf-8-sig'))['targets'] if t['national']==a.national)
    relative=Path('ik_pokemon/data')/Path(selected['model']['model_path']).parent
    stem=relative.name
    base=work/'mods/all-models/romfs'/relative
    if not a.inspect_only and a.mods_root:
        destination=a.mods_root.resolve()
        assert destination.is_relative_to(work.resolve()) and not destination.exists()
        destination.mkdir()
        import _winapi
        for name in ('00-icon-identity-r2','all-models'):
            source=(work/'mods'/name).resolve()
            _winapi.CreateJunction(str(source),str(destination/name))
            assert os.path.samefile(source,destination/name)
    elif not a.inspect_only:
        assert a.national==835,'Non-Yamper staging requires isolated --mods-root'
    overlay=(a.mods_root or work/'mods')/'01-yamper-transition-probe-r1/romfs'/relative
    track_schema=schema('tracr','ZA/Flatbuffers');path=base/(stem+'_base.tracr')
    tracks=track_schema.decode(path.read_bytes());changes=[]
    if a.audit_contract or a.match_native_contract:
        import za_folder
        za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin')
        game=za_folder.game()
        donor=661 if a.national==519 else 172
        catalog=Z.catalog_schema().decode(game.read(Z.CATALOG))['table']
        entry=next(r for r in catalog if r['species_info'].get('species')==donor and not r['species_info'].get('form',0) and not r['species_info'].get('gender',0))
        native_base='ik_pokemon/data/'+str(Path(entry['model_path']).parent).replace('\\','/')+'/'
        native=track_schema.decode(game.read(native_base+Path(entry['model_path']).stem+'_base.tracr'))
        by_name={t['track_name']:t for t in native['track_list']['list']}
        def info(raw):
            fb=FB(raw);root=fb.table(fb.u32(0));values=fb.table(root[0]+fb.u32(root[0]))
            return [fb.u32(values[i]) if i<len(values) and values[i] else 0 for i in range(3)]
        if a.match_native_contract:
            assert a.national==519 and a.mods_root and not a.inspect_only
            from sword_animation_rate import replace_info
            for track in tracks['track_list']['list']:
                name=track['track_name'];resource=track.get('track_resource',{}).get('animation')
                donor_resource=by_name[name].get('track_resource',{}).get('animation')
                if not resource or not donor_resource:continue
                raw=(base/resource['filename']).read_bytes();old=info(raw)
                expected=info(game.read(native_base+donor_resource['filename']))
                if old==expected:continue
                patched=raw if a.alias_only else replace_info(raw,*expected)
                filename='pc_native_contract_'+name+'.tranm'
                atomic(overlay/filename,patched);resource['filename']=filename
                changes.append(dict(track=name,previous_info=old,native_info=expected,
                                    original_sha256=hashlib.sha256(raw).hexdigest(),patched_sha256=hashlib.sha256(patched).hexdigest()))
            assert changes
            atomic(overlay/path.name,encode_checked(track_schema,tracks))
            atomic(a.mods_root/'native-contract-probe.json',json.dumps(dict(PC_only=True,diagnostic_only=True,
                   QA_pass_allowed=False,alias_only=a.alias_only,source_unchanged=True,bone_curves_unchanged=True,changes=changes,
                   caveat='Header-only ablation; clips may hold/cut their source pose. Not a finished animation fix.'),indent=1).encode())
            print(json.dumps(dict(national=a.national,changed_tracks=len(changes),QA_pass_allowed=False)),flush=True)
            return
        audit=[]
        for track in tracks['track_list']['list']:
            name=track['track_name']
            if 'attack' not in name.lower():continue
            target=track.get('track_resource',{});old=by_name[name].get('track_resource',{})
            record=dict(track=name,imported_resources=target,native_resources=old)
            if 'animation' in target:record['imported_info']=info((base/target['animation']['filename']).read_bytes())
            if 'animation' in old:record['native_info']=info(game.read(native_base+old['animation']['filename']))
            if a.effect_track:
                if name!=a.effect_track:continue
                effect_raw=(base/target['effect']['filename']).read_bytes()
                ef=FB(effect_raw);ef_root=ef.table(ef.u32(0));count,vec=ef.vec(ef_root[0]);events=[]
                for i in range(count):
                    ptr=vec+i*4;fields=ef.table(ptr+ef.u32(ptr))
                    events.append(dict(start=ef.u32(fields[2]) if len(fields)>2 and fields[2] else 0,
                                       duration=ef.u32(fields[3]) if len(fields)>3 and fields[3] else 0))
                record['effect_events']=events
            audit.append(record)
        print(json.dumps(dict(read_only=True,national=a.national,donor=donor,attacks=audit)),flush=True)
        return
    for track in tracks['track_list']['list']:
        name=track['track_name'];resource=track.get('track_resource',{}).get('animation')
        if not resource or '_loop' in name:continue
        if a.only_transitions and not any(token in name for token in ('turn','stepin','stepout','jumpup','land')):continue
        raw=(base/resource['filename']).read_bytes();fb=FB(raw);root=fb.table(fb.u32(0))
        info=fb.table(root[0]+fb.u32(root[0]))
        values=[fb.u32(info[i]) if i<len(info) and info[i] else 0 for i in range(3)]
        if not values[0]:continue
        assert len(info)==3 and values[1]>0 and values[2] in (30,60),values
        data=bytearray(raw);struct.pack_into('<I',data,info[0],0)
        target='pc_oneshot_'+name+'.tranm'
        if not a.inspect_only:atomic(overlay/target,data)
        previous=resource['filename'];resource['filename']=target
        changes.append(dict(track=name,previous=previous,clip=target,previous_loop=values[0],frames=values[1],rate=values[2],
                            original_sha256=hashlib.sha256(raw).hexdigest(),patched_sha256=hashlib.sha256(data).hexdigest()))
    assert changes,'No looping one-shot mappings found'
    if a.inspect_only:
        print(json.dumps(dict(read_only=True,national=a.national,looping_oneshots=len(changes),changes=changes)),flush=True)
        return
    atomic(overlay/path.name,encode_checked(track_schema,tracks))
    report=dict(diagnostic_only=True,PC_only=True,national=a.national,changes=changes,verified_in_game=False,
                source_controller_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                caveat='Idle fallback pose is retained; this tests completion of transition states, not correct attack motion mapping')
    report_path=a.mods_root/'transition-probe.json' if a.mods_root else work/'yamper-transition-probe-r1.json'
    atomic(report_path,json.dumps(report,indent=1).encode())
    print(json.dumps(dict(changed_tracks=len(changes),examples=changes[:5])),flush=True)


if __name__=='__main__':main()
