"""Read-only native SARC/BNTX extraction of the requested English UI heading candidates.

No asset is edited or installed. Output stays in hebrew-lab/headers/extract. BC4/BC5
mask decoding and Tegra block-linear addressing follow the local prompt_textures.py
reference; native BC payloads and every exact source offset are retained for patching.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct

import numpy as np
from PIL import Image
from za_romfs import Game,fnv1a64

LAB=Path(__file__).resolve().parents[1]
ROMFS=Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc\update-2.0.2-20261025\game\romfs.bin')
ARCHIVES=(
 'ui/data/main_menu/main_menu_top_00_eng.arc',
 'ui/data/main_menu/main_menu_report_00_eng.arc',
 'ui/data/player_select/player_select_00_eng.arc',
 'ui/data/player_select/player_select_confirm_00_eng.arc',
)
SELECT=re.compile(r'^grptext_(?:cmn_opguide_title|main_menu_report_title|player_select_title)')
MASK64=(1<<64)-1


def sha(data):return hashlib.sha256(data).hexdigest()
def rel(path):return str(Path(path).relative_to(LAB)).replace('\\','/')


def save_exact(path,data):
    path=Path(path).resolve()
    if not any(path.is_relative_to((LAB/'headers'/name).resolve()) for name in ('extract','extract-base')):
        raise ValueError('Extraction escaped the owned extraction directories')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise FileExistsError('Different extraction already exists: '+str(path))
    else:path.write_bytes(data)
    assert path.read_bytes()==data


def sarc_members(data):
    if data[:4]!=b'SARC':raise ValueError('Not a native SARC archive')
    sfat=struct.unpack_from('<H',data,4)[0]
    offset=struct.unpack_from('<I',data,0x0C)[0]
    count=struct.unpack_from('<H',data,sfat+6)[0]
    names=sfat+0x0C+16*count+8
    for index in range(count):
        namehash,attr,start,end=struct.unpack_from('<4I',data,sfat+0x0C+16*index)
        if not attr&0x01000000:raise ValueError('Unnamed SARC member')
        pos=names+(attr&0x00FFFFFF)*4
        name=data[pos:data.index(b'\0',pos)].decode('utf-8')
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:raise ValueError('Unsafe SARC member')
        yield dict(name=name,index=index,offset=offset+start,size=end-start,
                   sfat_node_offset=sfat+0x0C+16*index,name_hash=f'{namehash:08x}'),data[offset+start:offset+end]


def textures(data):
    if data[:4]!=b'BNTX':raise ValueError('Not BNTX')
    count=struct.unpack_from('<I',data,0x24)[0]
    infos=struct.unpack_from('<Q',data,0x28)[0]
    for index in range(count):
        header=struct.unpack_from('<Q',data,infos+8*index)[0]
        if data[header:header+4]!=b'BRTI':raise ValueError('Unexpected BNTX info magic')
        fmt=struct.unpack_from('<I',data,header+0x1C)[0]
        width,height,depth,layers=struct.unpack_from('<4I',data,header+0x24)
        size=struct.unpack_from('<I',data,header+0x50)[0]
        nameptr=struct.unpack_from('<Q',data,header+0x60)[0]
        name=data[nameptr+2:nameptr+2+struct.unpack_from('<H',data,nameptr)[0]].decode('utf-8')
        mip_count=struct.unpack_from('<H',data,header+0x16)[0]
        mip_table=struct.unpack_from('<Q',data,header+0x70)[0]
        mip_offsets=list(struct.unpack_from('<'+'Q'*mip_count,data,mip_table))
        start=mip_offsets[0]
        record=dict(name=name,index=index,width=width,height=height,depth=depth,layers=layers,
            format=f'0x{fmt:04x}',format_name={0x1D01:'BC4_UNORM',0x1E01:'BC5_UNORM',0x1C01:'BC3_UNORM'}.get(fmt,'other'),
            tile_mode=struct.unpack_from('<H',data,header+0x12)[0],
            block_height_log2=struct.unpack_from('<I',data,header+0x34)[0]&7,
            mips=mip_count,component_selectors=list(data[header+0x58:header+0x5C]),
            brti_offset=header,payload_offset_in_bntx=start,payload_size=size,mip_offsets_in_bntx=mip_offsets,
            alignment=struct.unpack_from('<I',data,header+0x54)[0])
        yield record,data[start:start+size]


def runtime_hash(data):
    length=len(data);h=[0x9E3779B97F4A7C15^length,0xC2B2AE3D27D4EB4F,0x165667B19E3779F9,0x27D4EB2F165667C5];pos=0
    while pos+32<=length:
        for lane,value in enumerate(struct.unpack_from('<4Q',data,pos)):
            value=((h[lane]^value)*0x100000001B3)&MASK64;h[lane]=value^(value>>29)
        pos+=32
    value=h[0]^((h[1]*0x9E3779B97F4A7C15)&MASK64)^((h[2]*0xC2B2AE3D27D4EB4F)&MASK64)^((h[3]*0x165667B19E3779F9)&MASK64)
    while pos<length:value=((value^data[pos])*0x100000001B3)&MASK64;pos+=1
    return f'{value^(value>>31):016x}'


def deswizzle(data,blocks_w,blocks_h,block_bytes,block_height_log2):
    gob_height=8<<block_height_log2;row=blocks_w*block_bytes;gobs_x=(row+63)//64
    out=bytearray(row*blocks_h)
    for y in range(blocks_h):
        big_y,inner_y=divmod(y,gob_height);gob_y,pixel_y=divmod(inner_y,8)
        for x in range(row):
            gob_x,pixel_x=divmod(x,64)
            address=(big_y*gobs_x+gob_x)*gob_height*64+gob_y*512+(pixel_x//32)*256+(pixel_y//2)*64+((pixel_x%32)//16)*32+(pixel_y%2)*16+pixel_x%16
            out[y*row+x]=data[address]
    return bytes(out)


def bc4(block):
    first,last=block[0],block[1];indices=int.from_bytes(block[2:8],'little')
    palette=[first,last]+([((7-index)*first+index*last)//7 for index in range(1,7)] if first>last else
                         [((5-index)*first+index*last)//5 for index in range(1,5)]+[0,255])
    return [palette[(indices>>(3*index))&7] for index in range(16)]


def decode_masks(meta,data):
    fmt=int(meta['format'],16)
    if fmt not in (0x1D01,0x1E01):raise ValueError('Only native BC4/BC5 mask extraction is implemented')
    if meta['mips']!=1 or meta['layers']!=1 or meta['depth']!=1 or meta['tile_mode']!=0:
        raise ValueError('Only these proven single-mip 2D block-linear headings are decoded')
    channels=1 if fmt==0x1D01 else 2
    bw,bh=(meta['width']+3)//4,(meta['height']+3)//4
    linear=deswizzle(data,bw,bh,8*channels,meta['block_height_log2'])
    image=np.zeros((bh*4,bw*4,channels),np.uint8)
    for by in range(bh):
        for bx in range(bw):
            pos=(by*bw+bx)*8*channels
            for channel in range(channels):
                image[by*4:by*4+4,bx*4:bx*4+4,channel]=np.array(bc4(linear[pos+8*channel:pos+8*channel+8]),np.uint8).reshape(4,4)
    return image[:meta['height'],:meta['width']],linear


def heading_panes(data):
    """Inspect proven FLYT pic1/txl1/mat1 fields; no layout mutation or inferred atlas slicing."""
    sections=[];pos=struct.unpack_from('<H',data,6)[0]
    while pos<len(data):
        size=struct.unpack_from('<I',data,pos+4)[0]
        if size<8 or pos+size>len(data):raise ValueError('Invalid FLYT section bounds')
        sections.append((data[pos:pos+4],pos,size));pos+=size
    by={magic:(pos,size) for magic,pos,size in sections}
    if b'txl1' not in by or b'mat1' not in by:return []
    txl=by[b'txl1'][0];count=struct.unpack_from('<I',data,txl+8)[0];names=[]
    for index in range(count):
        start=txl+12+struct.unpack_from('<I',data,txl+12+4*index)[0]
        names.append(data[start:data.index(b'\0',start)].decode('utf-8'))
    mat=by[b'mat1'][0];count=struct.unpack_from('<I',data,mat+8)[0];materials=[]
    for index in range(count):
        start=mat+struct.unpack_from('<I',data,mat+12+4*index)[0]
        flags=struct.unpack_from('<I',data,start+28)[0]
        maps=[]
        for slot in range(flags&3):
            texture,wrap_s,wrap_t=struct.unpack_from('<HBB',data,start+44+4*slot)
            maps.append(dict(slot=slot,texture_index=texture,texture=names[texture],wrap_s=wrap_s,wrap_t=wrap_t))
        materials.append(dict(index=index,name=data[start:start+28].split(b'\0')[0].decode('utf-8'),
            offset=start,flags=f'0x{flags:08x}',texture_maps=maps))
    panes=[]
    for magic,pos,size in sections:
        if magic!=b'pic1' or size<0x68:continue
        material=materials[struct.unpack_from('<H',data,pos+0x64)[0]]
        if not any(SELECT.match(ref['texture']) for ref in material['texture_maps']):continue
        uv_count=data[pos+0x66]
        if pos+0x68+uv_count*32>pos+size:raise ValueError('Invalid pic1 UV bounds')
        uv=[list(struct.unpack_from('<8f',data,pos+0x68+32*index)) for index in range(uv_count)]
        panes.append(dict(name=data[pos+12:pos+36].split(b'\0')[0].decode('utf-8'),section_offset=pos,
            section_bytes=size,translate=list(struct.unpack_from('<3f',data,pos+0x2C)),
            scale=list(struct.unpack_from('<2f',data,pos+0x44)),size=list(struct.unpack_from('<2f',data,pos+0x4C)),
            material=material,uv_sets=uv,all_uv_full_image=all(values==[0.,0.,1.,0.,0.,1.,1.,1.] for values in uv)))
    return panes


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--romfs',type=Path,default=ROMFS)
    parser.add_argument('--base-arcs',action='store_true',help='Extract separately the native paths without _eng suffix')
    args=parser.parse_args()
    game=Game(args.romfs)
    report=dict(source_romfs=str(args.romfs),reference_access='read_only_mmap',source_files_modified=False,
        image_assets_edited=False,bulk_glossary_approval='pending',archives=[],
        routes=dict(native_layeredfs='Replace the full uncompressed .arc at mods/hebrew/romfs/<game_path>; runtime unlists original ONEPACK entry.',
            native_payload='Keep BNTX/SARC layout and total size: replace exact BC4/BC5 block-linear payload, or edit native BFLYT with its own size/offset validation.',
            pc_hd='textures/hd/<runtime_hash>.png; tex_hd or LARECOMP_TEX_HD must be enabled, and the hash is of original native payload including padding.'),
        limitations=['Extracted mask channel images are raw-channel visualizations, not final shader-composited screenshots.',
            'No compression encoding or asset replacement is done by this tool.','UV/pane mapping belongs to native layout research.'])
    paths=tuple(path.replace('_eng.arc','.arc') for path in ARCHIVES) if args.base_arcs else ARCHIVES
    for game_path in paths:
        file_hash=fnv1a64(game_path);entry=game.files[file_hash];data=game.read(game_path)
        slug=Path(game_path).stem;folder=LAB/'headers'/('extract-base' if args.base_arcs else 'extract')/slug
        archive=folder/'archive.arc';save_exact(archive,data)
        item=dict(game_path=game_path,file_hash=f'{file_hash:016x}',pack=entry['pack'],
            archive_bytes=len(data),compressed_bytes=entry['csize'],oodle_compression=entry['comp'],sha256=sha(data),
            extracted_archive=rel(archive),members=[],textures=[],heading_layout_bindings=[])
        for member,payload in sarc_members(data):
            member['sha256']=sha(payload);item['members'].append(member)
            if payload[:4] in (b'FLYT',b'BNTX'):
                target=folder/'members'/member['name'];save_exact(target,payload);member['extracted_path']=rel(target)
            if payload[:4]==b'FLYT':
                panes=heading_panes(payload)
                if panes:item['heading_layout_bindings'].append(dict(member_name=member['name'],panes=panes))
            if payload[:4]!=b'BNTX':continue
            for texture,raw in textures(payload):
                texture.update(member_name=member['name'],member_offset_in_archive=member['offset'],
                    payload_offset_in_archive=member['offset']+texture['payload_offset_in_bntx'],
                    payload_sha256=sha(raw),runtime_hash=runtime_hash(raw),selected_header_candidate=bool(SELECT.match(texture['name'])))
                if texture['selected_header_candidate']:
                    safe=texture['name'].replace('^','_');prefix=folder/'textures'/safe
                    save_exact(prefix.with_suffix('.native.bin'),raw);texture['native_payload_path']=rel(prefix.with_suffix('.native.bin'))
                    masks,linear=decode_masks(texture,raw);save_exact(prefix.with_suffix('.linear.bin'),linear)
                    texture['linear_blocks_path']=rel(prefix.with_suffix('.linear.bin'));texture['channels']=[]
                    for channel in range(masks.shape[2]):
                        path=prefix.parent/(prefix.name+f'.channel{channel}.png')
                        # Output is an untouched decoder result, never a repainted label.
                        path.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(masks[:,:,channel]).save(path)
                        texture['channels'].append(dict(channel=channel,path=rel(path),bbox=Image.fromarray(masks[:,:,channel]).getbbox(),
                            minimum=int(masks[:,:,channel].min()),maximum=int(masks[:,:,channel].max())))
                item['textures'].append(texture)
        report['archives'].append(item)
        print(json.dumps(dict(game_path=game_path,bytes=len(data),textures=len(item['textures']),selected=sum(t['selected_header_candidate'] for t in item['textures']))),flush=True)
    reports=LAB/'headers/reports';reports.mkdir(parents=True,exist_ok=True)
    (reports/('extraction-base.json' if args.base_arcs else 'extraction.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
