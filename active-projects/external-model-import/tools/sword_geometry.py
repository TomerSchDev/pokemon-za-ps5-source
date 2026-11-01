"""Translate real Sword GFBMDL geometry to ZA's TRMDL/TRMSH/TRMBF/TRSKL containers.

Source centimetres become metres. Compact skin indices and original weights are retained.
The converter rejects unsupported vertex layouts instead of substituting another Pokémon's geometry.
"""
import math
from pathlib import Path
import struct
from build_smoliv_model import schema,encode_checked
from source_archives import Gfpak


def identity():
    return [[float(i==j) for j in range(4)] for i in range(4)]


def multiply(a,b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def inverse(matrix):
    m=[row[:]+eye for row,eye in zip(matrix,identity())]
    for col in range(4):
        pivot=max(range(col,4),key=lambda r:abs(m[r][col]))
        if abs(m[pivot][col])<1e-12:
            raise ValueError('Singular source bone transform')
        m[col],m[pivot]=m[pivot],m[col]
        divisor=m[col][col]
        m[col]=[v/divisor for v in m[col]]
        for row in range(4):
            if row!=col:
                divisor=m[row][col]
                m[row]=[a-divisor*b for a,b in zip(m[row],m[col])]
    return [row[4:] for row in m]


def vec(value,default=0,scale=1):
    return {key:float(value.get(key,default))*scale for key in ('x','y','z')}


def canonical(value):
    if isinstance(value,float):
        return struct.unpack('<f',struct.pack('<f',value))[0]
    if isinstance(value,dict):
        return {key:canonical(v) for key,v in value.items()}
    if isinstance(value,list):
        return [canonical(v) for v in value]
    return value


def transform(bone):
    scale=vec(bone.get('VecScale',{}),1)
    rotate=vec(bone.get('VecRot',{}))
    translate=vec(bone.get('VecTranslate',{}),scale=.01)
    x,y,z=(rotate[k] for k in ('x','y','z'))
    cx,sx,cy,sy,cz,sz=math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    rx=[[1,0,0,0],[0,cx,-sx,0],[0,sx,cx,0],[0,0,0,1]]
    ry=[[cy,0,sy,0],[0,1,0,0],[-sy,0,cy,0],[0,0,0,1]]
    rz=[[cz,-sz,0,0],[sz,cz,0,0],[0,0,1,0],[0,0,0,1]]
    matrix=multiply(rz,multiply(ry,rx))
    for i,key in enumerate(('x','y','z')):
        for row in range(3):
            matrix[row][i]*=scale[key]
        matrix[i][3]=translate[key]
    return matrix,dict(VecScale=scale,VecRot=rotate,VecTranslate=translate)


def skeleton(model):
    bones=model['skeleton']
    skin=[i for i,b in enumerate(bones) if b.get('is_skin',1)]
    # Rigid meshes may be parented to a non-skin transform node.
    for mesh in model['mesh']:
        shape=model['shapes'][mesh.get('shapeID',0)]
        if not any(a.get('type',0)==11 for a in shape['attributes']) and mesh.get('boneID',0) not in skin:
            skin.append(mesh.get('boneID',0))
    index={bone:i for i,bone in enumerate(skin)}
    nodes,world=[],[]
    for i,bone in enumerate(bones):
        local,trs=transform(bone)
        parent=bone.get('parent',0)
        if parent>=i or parent < -1:
            raise ValueError('Invalid source bone hierarchy')
        world.append(multiply(world[parent],local) if parent>=0 else local)
        node=dict(name=bone['name'].lower(),transform=trs,parent_idx=parent,
                  scalePivot=vec(bone.get('VecScalePivot',{}),scale=.01),
                  rotatePivot=vec(bone.get('VecRotatePivot',{}),scale=.01))
        if i in index:
            node['rig_idx']=index[i]
        nodes.append(node)
    matrices=[]
    for i in skin:
        inv=inverse(world[i])
        matrix={key:{axis:inv[row][col] for row,axis in enumerate(('x','y','z'))} for col,key in enumerate(('x','y','z','w'))}
        matrices.append(dict(inherit_position=1,unk_bool_2=1,matrix=matrix))
    ground_offset=max(0.0,-model['boundingBox']['b1'].get('y',0.0)*.01)
    if ground_offset>1e-5:
        # Old game configuration applies this model-placement offset outside the animation rig.
        # A separate, unanimated parent preserves the original bind matrices and all source curves.
        for node in nodes:
            node['parent_idx']=node['parent_idx']+1 if node['parent_idx']>=0 else 0
        nodes.insert(0,dict(name='za_import_origin',parent_idx=-1,transform=dict(
            VecScale=dict(x=1.,y=1.,z=1.),VecRot=dict(x=0.,y=0.,z=0.),
            VecTranslate=dict(x=0.,y=ground_offset,z=0.))))
    return dict(transform_nodes=nodes,bones=matrices,rig_offset=0),index


def bounds(box):
    return dict(min=vec(box['b1'],scale=.01),max=vec(box['b2'],scale=.01))


SOURCE_FORMAT={0:('f',4),1:('e',2),2:('b',1),3:('B',1),4:('h',2),5:('H',2),6:('i',4),7:('I',4),8:('B',1)}


def mesh_buffers(model,rig_index,stem):
    meshes,buffers=[],[]
    for mesh_no,mesh in enumerate(model['mesh']):
        source=model['shapes'][mesh.get('shapeID',0)]
        attrs=source['attributes']
        layouts=[]
        stride=0
        for a in attrs:
            fmt,size=SOURCE_FORMAT[a.get('format',0)]
            count=a['count']
            layouts.append((a.get('type',0),a.get('format',0),fmt,count,stride))
            stride+=count*size
        raw=bytes(source['vertices'])
        if len(raw)%stride:
            raise ValueError('Source vertex buffer does not match its declared stride')
        target_attrs=[]
        target_stride=0
        formats=[]
        for kind,source_type,fmt,count,offset in layouts:
            # Native IkCharacter's verified layout is POSITION/NORMAL/TANGENT/UV0/JOINTS/WEIGHTS.
            # Old GFBMDL vertex colors encode legacy shader masks; exposing them as extra bindings
            # shifts skinning inputs in ZA's existing shader permutation.
            if 4<=kind<=10:
                continue
            if kind==0:
                target_kind,layer,target_type,output_fmt=1,0,51,'3f'
            elif kind in (1,2):
                target_kind,layer,target_type,output_fmt=(2 if kind==1 else 3),0,43,'4e'
            elif 3<=kind<=6:
                target_kind,layer,target_type,output_fmt=6,kind-3,48,'2f'
            elif 7<=kind<=10:
                target_kind,layer,target_type,output_fmt=5,kind-7,20,'4B'
            elif kind==11:
                target_kind,layer,target_type,output_fmt=7,0,22,'4B'
            elif kind==12:
                target_kind,layer,target_type,output_fmt=8,0,39,'4H'
            else:
                raise ValueError('Unsupported source attribute '+str(kind))
            target_attrs.append(dict(attr_0=0,attribute=target_kind,attribute_layer=layer,type=target_type,position=target_stride))
            target_stride+=struct.calcsize('<'+output_fmt)
            formats.append((kind,source_type,fmt,count,offset,output_fmt))
        rigid=not any(kind==11 for kind,*_ in layouts)
        if rigid:
            target_attrs.extend([dict(attr_0=0,attribute=7,type=22,position=target_stride),dict(attr_0=0,attribute=8,type=39,position=target_stride+4)])
            target_stride+=12
        vertices=bytearray()
        influences={}
        for at in range(0,len(raw),stride):
            joint_ids=[];joint_weights=[]
            for kind,source_type,fmt,count,offset,output_fmt in formats:
                values=list(struct.unpack_from('<'+str(count)+fmt,raw,at+offset))
                if kind==0:
                    values=[v*.01 for v in values[:3]]
                elif kind in (1,2):
                    values=(values+[0,0,0,1])[:4]
                elif 3<=kind<=6:
                    values=values[:2]
                elif 7<=kind<=11:
                    values=(values+[0,0,0,0])[:4]
                    if kind==11:joint_ids=values[:]
                elif kind==12:
                    divisor=255 if source_type==8 else 1
                    values=[max(0,min(65535,round(v/divisor*65535))) for v in (values+[0,0,0,0])[:4]]
                    joint_weights=[v/65535 for v in values]
                vertices.extend(struct.pack('<'+output_fmt,*values))
            if rigid:
                bone=rig_index[mesh.get('boneID',0)]
                if bone>255:
                    raise ValueError('Rigid bone exceeds RGBA8 joint index range')
                vertices.extend(struct.pack('<4B4H',bone,0,0,0,65535,0,0,0))
                joint_ids,joint_weights=[bone],[1.0]
            for bone,weight in zip(joint_ids,joint_weights):
                if weight:
                    influences[bone]=influences.get(bone,0.0)+weight
        indexes=bytearray()
        materials=[]
        for polygon in source['polygons']:
            tris=polygon['tris']
            if tris and max(tris)>=len(raw)//stride:
                raise ValueError('Source polygon index exceeds vertex count')
            materials.append(dict(poly_count=len(tris),poly_offset=len(indexes)//2,
                                  material_name=model['materials'][polygon.get('materialId',0)]['name'],sh_unk4=0))
            indexes.extend(struct.pack('<'+str(len(tris))+'H',*tris))
        bb=bounds(mesh.get('box',model['boundingBox']))
        center={k:(bb['min'][k]+bb['max'][k])/2 for k in ('x','y','z')}
        radius=math.sqrt(sum((bb['max'][k]-center[k])**2 for k in center))
        name=f'{stem}_mesh_{mesh_no}'
        meshes.append(dict(mesh_shape_name=name+'_shape',bounds=bb,polygon_type=1,
                           attributes=[dict(attrs=target_attrs,size=[dict(size=target_stride)])],materials=materials,
                           clip_sphere={**center,'radius':radius},mesh_name=name,
                           influence=[dict(index=bone,scale=weight) for bone,weight in sorted(influences.items(),key=lambda pair:-pair[1])]))
        buffers.append(dict(index_buffer=[dict(buffer=list(indexes))],vertex_buffer=[dict(buffer=list(vertices))]))
    return dict(meshes=meshes,buffer_name=stem+'.trmbf'),dict(buffers=buffers)


def convert_sword_model(archive_path,row):
    archive=Gfpak(archive_path)
    model=schema('gfbmdl','SWSH/Flatbuffers/Model').decode(archive.read_name(row['model']))
    stem=Path(row['model']).stem
    skl,rig=skeleton(model)
    msh,mbf=mesh_buffers(model,rig,stem)
    bb=bounds(model['boundingBox'])
    ground_offset=max(0.0,-bb['min']['y'])
    if ground_offset>1e-5:
        bb['min']['y']+=ground_offset;bb['max']['y']+=ground_offset
    center={k:(bb['min'][k]+bb['max'][k])/2 for k in ('x','y','z')}
    radius=math.sqrt(sum((bb['max'][k]-center[k])**2 for k in center))
    mdl=dict(meshes=[dict(filename=stem+'.trmsh')],skeleton=dict(filename=stem+'.trskl'),
             materials=[stem+'.trmtr'],lods=[dict(index=[{}],lod_type='Custom')],bounds=bb,
             tex_spc_loc={**center,'w':radius},unk9=3)
    files={stem+'.'+ext:encode_checked(schema(ext),canonical(value)) for ext,value in (('trmdl',mdl),('trmsh',msh),('trmbf',mbf),('trskl',skl))}
    return files,model,dict(source_archive=str(archive_path),meshes=len(msh['meshes']),skin_bones=len(rig),
                           vertices=sum(len(b['vertex_buffer'][0]['buffer']) for b in mbf['buffers']),real_geometry=True,
                           source_centimetres_to_metres=.01)
