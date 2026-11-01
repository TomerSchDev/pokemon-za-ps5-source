"""Bridge a real supplied SV model to ZA's shader and animation-controller formats.

This isolated render pilot repoints Mareep's catalogue entry. It does not edit encounter/save data.
Geometry, textures, skeleton and bone animations come from Smoliv; ZA supplies controller structure and hurtbox.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
from catalog_inventory import LAB,Z
from fbcodec import Schema,same

from storage_paths import data_root
ROOT=data_root()
SRC=ROOT/'work/smoliv-source/pokemon/data/pm1039/pm1039_00_00'
DONOR=LAB/'pilot/build/step1/species-pilot/romfs/ik_pokemon/data/pm0935/pm0935_00_00'
SOURCE='pm1039'
TARGET='pm0935'
STEM=TARGET+'_00_00'
REL=f'ik_pokemon/data/{TARGET}/{STEM}'


def schema(ext,kind='SV/Flatbuffers/model'):
    return Schema.from_bfbs((ROOT/f'ref/{kind}/{ext}.bfbs').read_bytes())


def encode_checked(s,value):
    data=s.encode(value)
    if not same(s.decode(data),value):
        raise ValueError('FlatBuffers round-trip changed fields')
    return data


def rename(data):
    return data.replace(SOURCE.encode(),TARGET.encode())


def material_bridge(source,templates,source_pm=SOURCE,target_pm=TARGET,stem=STEM):
    result=[]
    report=[]
    for material in source['materials']:
        key=material['name']
        transparent=any('transparent' in s['shader_name'].lower() for s in material['shaders']) or 'Blend' in material.get('alpha_type','')
        if transparent:
            # An opaque body template can cover a transparent shell's entire
            # face. Use an existing native shader permutation and blend state.
            native=json.loads((ROOT/'ref/ZA/material-templates/transparency-native.json').read_text(encoding='utf-8'))
            blend=material.get('alpha_type','BlendPreMultiAlpha')
            template=next(m['material'] for m in native['templates'] if m['material']['alpha_type']==blend)
        else:
            template=next((m for m in templates if m['name']==key),None)
            if template is None:
                template=next(m for m in templates if ('eye' in m['name'].lower())==('eye' in key.lower()))
        out=copy.deepcopy(template)
        out['name']=key.replace(source_pm,target_pm)
        sources={t['texture_name']:t for t in material.get('textures',[])}
        if 'AOMap' in sources and 'OcclusionMap' not in sources:
            sources['OcclusionMap']=sources['AOMap']
        mapped=[]
        for texture in out['textures']:
            name=texture['texture_name']
            if name in sources:
                texture['texture_file']=sources[name]['texture_file'].replace(source_pm,target_pm)
                mapped.append(name)
            elif name=='OcclusionMap':
                texture['texture_file']=stem+'_white_msk.bntx'
            elif name in ('SpecularMaskMap','RimLightMaskMap','ShadowingColorMaskMap','HighlightMaskMap','ParallaxMap'):
                texture['texture_file']=stem+'_black_msk.bntx'
            elif name=='ShadowingColorMap':
                texture['texture_file']=stem+'_white_msk.bntx'
            elif name=='LayerMaskMap':
                texture['texture_file']=stem+'_black_msk.bntx'
        for parameter_key,name_key in (('float_parameter','float_name'),('float4_parameter','color_name'),('int_parameter','int_name')):
            incoming={p[name_key]:p for p in material.get(parameter_key,[])}
            out[parameter_key]=[copy.deepcopy(incoming.get(p[name_key],p)) for p in out.get(parameter_key,[])]
        report.append(dict(material=key,source_shaders=[s['shader_name'] for s in material['shaders']],
                           target_shaders=[s['shader_name'] for s in out['shaders']],mapped_textures=mapped,
                           neutral_masks=True))
        result.append(out)
    return {'materials':result},report


def semantic(name):
    return re.sub(r'^\d+_','',name)


def motion_match(name,available):
    # Numeric prefixes distinguish ground, flight and swimming clips. Several
    # species have the same semantic name in more than one locomotion family.
    # Keep an exact clip before considering semantic aliases.
    if name in available:
        return name,'exact track name and locomotion family'
    family=lambda value:value.split('_',1)[0][:1]
    rank=lambda value:(family(value)!=family(name),value)
    wanted=semantic(name)
    exact=[v for v in available if semantic(v)==wanted]
    if exact:
        return min(exact,key=rank),'exact semantic name; locomotion family preferred'
    aliases={'eat02_start':'eat01_start','eat02_loop':'eat01_loop','eat02_end':'eat01_end',
             'turn_r045':'turn_r090','turn_l045':'turn_l090','dash01_loop':'run01_loop',
             'walk02_loop':'walk01_loop','wait01_loop':'defaultwait01_loop',
             'rangeattack02_start':'rangeattack01','rangeattack02_loop':'rangeattack01','rangeattack02_end':'rangeattack01'}
    alias=aliases.get(wanted)
    if alias:
        match=min((v for v in available if semantic(v)==alias),key=rank,default=None)
        if match:
            return match,'compatible source motion alias'
    category=next((word for word in ('damage','down','attack','walk','run','turn','stun','eat','idle','notice','wait') if word in wanted),'wait')
    choices=[v for v in available if category in semantic(v)]
    if not choices:
        choices=[v for v in available if 'defaultwait01_loop' in v]
    if not choices:
        raise ValueError('No animation candidate for '+name)
    # Deterministic fallback is recorded and not described as an exact animation match.
    return min(choices,key=lambda v:(family(v)!=family(name),abs(len(semantic(v))-len(wanted)),v)),'source animation fallback; visual QA required'


def main():
    out=Path(sys.argv[1])
    if out.exists():
        raise SystemExit('Output exists: '+str(out))
    romfs=out/'mods/smoliv-real-model/romfs'
    dest=romfs/REL
    dest.mkdir(parents=True)
    report=dict(source_model='Pokémon Violet 3.0.1 Smoliv',source_internal=935,national_species=928,
                target_slot_for_render_pilot=179,source_folder=str(SRC),notes=[
                    'ZA neutral white/black shading masks are used where SV has no corresponding shader texture.',
                    'ZA controller layout and hurtbox are provisional donor data; this is a render pilot, not a species release.'])
    copied=[]
    # Real geometry, skeleton, textures and animation payloads. Material/config/controller data are built below.
    for file in SRC.rglob('*'):
        if file.is_file() and file.suffix in ('.trmbf','.trmsh','.trskl','.bntx','.tranm','.tracm'):
            target=dest/str(file.relative_to(SRC)).replace(SOURCE,TARGET)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(rename(file.read_bytes()))
            copied.append(str(target.relative_to(romfs)).replace('\\','/'))
    for suffix in ('_white_msk.bntx','_black_msk.bntx','_defence.hkx','.trpokecfg',
                   '_base.tracn','_base.tracl','_base.tracp','_base.tracs','_base.tralk','_base.trssp',
                   '_base.trmdt','_base.trslp','_base_motion_detector.trmdd'):
        source=DONOR/(STEM+suffix)
        if source.exists():
            shutil.copy2(source,dest/source.name)
    # ZA's five-layer shader reads layer 4 from alpha. A typical black R8 mask samples alpha=1,
    # which makes that layer replace the entire albedo with black. A zero swizzle makes all four
    # mask components zero while retaining an existing, valid ZA shader permutation.
    black_path=dest/(STEM+'_black_msk.bntx')
    black=bytearray((dest/(STEM+'_white_msk.bntx')).read_bytes().replace(b'white_msk',b'black_msk'))
    texture_count=struct.unpack_from('<I',black,0x24)[0]
    texture_info=struct.unpack_from('<Q',black,0x28)[0]
    for i in range(texture_count):
        at=struct.unpack_from('<Q',black,texture_info+i*8)[0]
        if black[at:at+4]!=b'BRTI':
            raise ValueError('Invalid neutral-mask BNTX texture descriptor')
        if struct.unpack_from('<I',black,at+0x1c)[0]!=0x2006:
            raise ValueError('Expected native BC7 neutral texture')
        size=struct.unpack_from('<I',black,at+0x50)[0]
        mip_offsets=struct.unpack_from('<Q',black,at+0x70)[0]
        pixels=struct.unpack_from('<Q',black,mip_offsets)[0]
        # BC7 mode 6, zero endpoints and indices: transparent black RGBA, including alpha.
        if size%16 or pixels+size>len(black):
            raise ValueError('Invalid native BC7 storage range')
        black[pixels:pixels+size]=(b'\x40'+b'\x00'*15)*(size//16)
    black_path.write_bytes(black)
    (dest/'locators').mkdir(exist_ok=True)
    for file in (DONOR/'locators').glob('*'):
        shutil.copy2(file,dest/'locators'/file.name)
    model_schema=schema('trmdl')
    model=model_schema.decode((SRC/'pm1039_00_00.trmdl').read_bytes())
    model=json.loads(json.dumps(model).replace(SOURCE,TARGET))
    model['unk9']=3
    (dest/(STEM+'.trmdl')).write_bytes(encode_checked(model_schema,model))
    (dest/(STEM+'.trmmt')).write_bytes(rename((SRC/'pm1039_00_00.trmmt').read_bytes()))
    material_schema=schema('trmtr')
    template=material_schema.decode((DONOR/(STEM+'.trmtr')).read_bytes())['materials']
    report['materials']={}
    for suffix in ('.trmtr','_rare.trmtr'):
        source=material_schema.decode((SRC/('pm1039_00_00'+suffix)).read_bytes())
        converted,mapping=material_bridge(source,template)
        (dest/(STEM+suffix)).write_bytes(encode_checked(material_schema,converted))
        report['materials'][suffix]=mapping
    tracks_schema=schema('tracr','ZA/Flatbuffers')
    tracks=tracks_schema.decode((DONOR/(STEM+'_base.tracr')).read_bytes())
    # Supplied SV 3.0.1 already includes turn_groups; the later ZA schema describes those fields.
    source_tracks=tracks_schema.decode((SRC/'pm1039_00_00_base.tracr').read_bytes())
    available={track['track_name']:track for track in source_tracks['track_list']['list']}
    mappings=[]
    for track in tracks['track_list']['list']:
        choice,method=motion_match(track['track_name'],available)
        target_resources=track['track_resource']
        source_resources=available[choice]['track_resource']
        for key in ('animation','material'):
            if key in source_resources:
                target_resources[key]=json.loads(json.dumps(source_resources[key]).replace(SOURCE,TARGET))
            else:
                target_resources.pop(key,None)
        # ZA's effects, curves and state names are retained, so engine callbacks keep their native format.
        for key in ('effect','curve'):
            if key in target_resources:
                filename=target_resources[key]['filename']
                source=DONOR/filename
                if not source.is_file():
                    raise ValueError('ZA controller payload absent: '+filename)
                shutil.copy2(source,dest/filename)
        mappings.append(dict(target=track['track_name'],source=choice,method=method))
    (dest/(STEM+'_base.tracr')).write_bytes(encode_checked(tracks_schema,tracks))
    report['animation_mapping']=mappings
    # Same catalogue entry as the previous new-path proof, now backed by real Smoliv geometry/animations.
    cat_schema=Z.catalog_schema()
    cat=cat_schema.decode((LAB/'pilot/build/step1/species-pilot/romfs'/Z.CATALOG).read_bytes())
    target=romfs/Z.CATALOG
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(encode_checked(cat_schema,cat))
    # Check every material texture, model dependency and animation payload before a runtime is launched.
    missing=[]
    for suffix in ('.trmtr','_rare.trmtr'):
        mats=material_schema.decode((dest/(STEM+suffix)).read_bytes())['materials']
        for material in mats:
            for texture in material.get('textures',[]):
                if not texture['texture_file'].startswith('../') and not (dest/texture['texture_file']).exists():
                    missing.append(texture['texture_file'])
    for track in tracks['track_list']['list']:
        for resource in track['track_resource'].values():
            if not (dest/resource['filename']).is_file():
                missing.append(resource['filename'])
    if missing:
        raise ValueError('Missing converted dependencies: '+str(sorted(set(missing))))
    report['file_count']=sum(p.is_file() for p in romfs.rglob('*'))
    report['sha256']={str(p.relative_to(romfs)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in romfs.rglob('*') if p.is_file()}
    (out/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(files=report['file_count'],source_animations=len(available),target_tracks=len(mappings),
                          fallbacks=sum('fallback' in m['method'] for m in mappings),output=str(out)),indent=2),flush=True)


if __name__=='__main__':
    main()
