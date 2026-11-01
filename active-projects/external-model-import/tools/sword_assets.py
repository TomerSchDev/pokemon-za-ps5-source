"""Sword material/animation extraction around the geometry converter."""
from pathlib import Path
from source_archives import FB,Gfpak
from sword_animation import convert_bone_animation


def normalize_materials(model):
    out=[]
    samplers={'Col0Tex':'BaseColorMap','NormalMapTex':'NormalMap','AmbientTex':'AOMap','LyCol0Tex':'LayerMaskMap'}
    for material in model['materials']:
        textures=[]
        for texture in material.get('textures',[]):
            name=texture['sampler_name']
            if name in samplers:
                filename=model['textureFiles'][texture.get('texture_index',0)]
                if not filename.endswith('.bntx'):
                    filename+='.bntx'
                textures.append(dict(texture_name=samplers[name],texture_file=filename))
        colors=[]
        color_mapping={'ConstantColor0':'BaseColor','ConstantColorSd0':'ShadowingColor',
                       'L1ConstantColor0':'BaseColorLayer1','L2ConstantColor0':'BaseColorLayer2'}
        for color in material.get('colors',[]):
            name=color['color_name']
            if name in color_mapping:
                colors.append(dict(color_name=color_mapping[name],color_value={**color['color'],'a':1.0}))
        # Old Layer1Enable controls whether LyCol0Tex is a true layered color mask.
        enabled=any(f['flag_name']=='Layer1Enable' and f.get('flag_enable') for f in material.get('flags',[]))
        if not enabled:
            textures=[t for t in textures if t['texture_name']!='LayerMaskMap']
        out.append(dict(name=material['name'],shaders=[dict(shader_name=material['shader'],shader_values=[])],
                        textures=textures,float4_parameter=colors))
    return {'materials':out}


def animations(archive,row):
    names={}
    for cfg in row['animations']:
        d=archive.read_name(cfg['path'])
        fb=FB(d)
        root=fb.table(fb.u32(0))
        resources=fb.table(root[6]+fb.u32(root[6]))
        count,pointer=fb.vec(resources[0])
        for i in range(count):
            at=pointer+i*4
            fields=fb.table(at+fb.u32(at))
            names[fb.string(fields[0])]=fb.string(fields[1])
    files,tracks,report={},{},{}
    for name,filename in names.items():
        data,info=convert_bone_animation(archive.read_name(filename))
        if data is None:
            report[name]=info
            continue
        target=Path(filename).stem+'.tranm'
        files[target]=data
        tracks[name]=dict(animation=dict(filename=target))
        report[name]=info
    return files,tracks,report


def choose_motion(name,available):
    tail=name.lower()
    categories=[('battlewait','ba10_wait'),('defaultwait','ba10_wait'),('walk','fi20_walk'),('run','fi21_run'),
                ('damage','ba30_damage'),('down','ba41_down'),('roar','ba02_roar'),('hate','kw30_hate'),
                ('attack','ba21_'),('eat','kw10_'),('drowse','kw20_')]
    prefix=next((prefix for category,prefix in categories if category in tail),'ba10_wait')
    matches=[n for n in available if n.lower().startswith(prefix)]
    if not matches:
        matches=[n for n in available if n.lower().startswith('ba10_wait')]
    if not matches:
        raise ValueError('Source archive has no idle animation')
    return sorted(matches)[0]
