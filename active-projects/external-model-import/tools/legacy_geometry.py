"""Convert Arceus model containers to the SV/ZA geometry layout; preserve source skeleton/animations.

No placeholder geometry is substituted. Material conversion and gameplay activation are separate stages.
"""
import copy
import json
from pathlib import Path
from build_smoliv_model import schema,encode_checked
from source_archives import Gfpak


def rename_keys(value,mapping):
    if isinstance(value,list):
        return [rename_keys(v,mapping) for v in value]
    if isinstance(value,dict):
        return {mapping.get(k,k):rename_keys(v,mapping) for k,v in value.items()}
    return value


def arceus_model(model):
    out={k:copy.deepcopy(v) for k,v in model.items() if k not in ('lods','sperical_bounds')}
    out['lods']=[dict(index=[{'unk0':entry.get('index',0)} for entry in lod.get('entries',[])],lod_type=lod.get('type','Custom')) for lod in model.get('lods',[])]
    if 'sperical_bounds' in model:
        sphere=model['sperical_bounds']
        out['tex_spc_loc']={**sphere.get('center',{}),'w':sphere.get('radius',0)}
    out['unk9']=3
    return out


def arceus_mesh(mesh):
    shapes=[]
    for old in mesh['shapes']:
        new={k:copy.deepcopy(v) for k,v in old.items() if k in ('mesh_shape_name','bounds','res0','res1','res2','res3','mesh_name')}
        if 'index_layout_format' in old:
            new['polygon_type']=old['index_layout_format']
        new['attributes']=[dict(attrs=rename_keys(layout.get('elements',[]),{'slot':'attr_0','semantic_name':'attribute','semantic_index':'attribute_layer','format':'type','offset':'position'}),size=layout.get('layout_size',[])) for layout in old.get('vertex_layout',[])]
        new['materials']=rename_keys(old.get('sub_meshes',[]),{'index_count':'poly_count','index_offset':'poly_offset','unk3':'sh_unk3','material':'material_name','unk4':'sh_unk4'})
        if 'spherical_bounds' in old:
            sphere=old['spherical_bounds']
            new['clip_sphere']={**sphere.get('center',{}),'radius':sphere.get('radius',0)}
        new['influence']=rename_keys(old.get('bone_weights',[]),{'rig_index':'index','weight':'scale'})
        shapes.append(new)
    out={'meshes':shapes,'buffer_name':mesh['buffer_file_name']}
    if 'unk0' in mesh:
        out['unk0']=mesh['unk0']
    return out


def arceus_materials(value):
    materials=[]
    for old in value['material_passes']:
        material=rename_keys(old,{'texture_parameters':'textures','float_parameters':'float_parameter',
              'float4_parameters':'float4_parameter','float4_light_parameters':'float4_light_parameter',
              'int_parameters':'int_parameter','write_mask':'byte_extra','mask':'value',
              'sampler_state_0':'SamplerState_0','sampler_state_1':'SamplerState_1','sampler_state_2':'SamplerState_2',
              'sampler_state_3':'SamplerState_3','sampler_state_4':'SamplerState_4','sampler_state_5':'SamplerState_5',
              'sampler_state_6':'SamplerState_6','sampler_state_7':'SamplerState_7','sampler_state_8':'SamplerState_8'})
        for shader in material.get('shaders',[]):
            shader['shader_values']=rename_keys(shader.get('shader_values',[]),{'property_binding':'string_name'})
        for field,key in (('textures','texture_name'),('float_parameter','float_name'),('float4_parameter','color_name'),('float4_light_parameter','color_name'),('int_parameter','int_name')):
            if field in material:
                material[field]=rename_keys(material[field],{'property_binding':key})
        for field in ('unk_5','unk_8','unk_10','unk_11','unk_12'):
            if field in material:
                if material[field]:
                    raise ValueError('Nonempty older material extension: '+field)
                material[field]=''
        materials.append(material)
    return {'materials':materials}


def convert_arceus_model(archive_path,row):
    archive=Gfpak(archive_path)
    stem=Path(row['model']).stem
    la=lambda ext:schema(ext,'LA/Flatbuffers/Model')
    model=la('trmdl').decode(archive.read_name(row['model']))
    files={stem+'.trmdl':encode_checked(schema('trmdl'),arceus_model(model))}
    meshes=[]
    for ref in model['meshes']:
        name=ref['filename']
        raw=archive.read_name(name)
        value=la('trmsh').decode(raw)
        files[name]=encode_checked(schema('trmsh'),arceus_mesh(value))
        buffer=value['buffer_file_name']
        # TRMBF vectors have identical field IDs/layout in LA and SV; retain original bytes.
        files[buffer]=archive.read_name(buffer)
        meshes.append(dict(file=name,mesh_shapes=len(value['shapes']),bytes=len(files[buffer])))
    skeleton=model['skeleton']['filename']
    files[skeleton]=archive.read_name(skeleton)
    if row.get('materials'):
        files[Path(row['materials']).name]=archive.read_name(row['materials'])
    materials={}
    for name in (stem+'.trmtr',stem+'_rare.trmtr'):
        try:
            raw=archive.read_name(name)
        except KeyError:
            continue
        materials[name]=arceus_materials(la('trmtr').decode(raw))
        for material in materials[name]['materials']:
            for texture in material.get('textures',[]):
                filename=texture['texture_file']
                if filename.startswith('../'):
                    continue
                files[filename]=archive.read_name(filename)
    return files,materials,dict(meshes=meshes,source_archive=str(archive_path),skeleton=skeleton,real_geometry=True)
