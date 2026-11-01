"""Native, local SARC/BNTX BC4U/BC5U mask codec. No image files or game writes.

Only same-size, single-mip/layer/depth block-linear texture payloads can be
patched. Archive tables, BFLYT, material metadata, dimensions and other textures
are preserved byte for byte. Channels are flat row-major uint8 bytes; None in
encode_masks preserves that channel's original compressed blocks exactly.
"""
from __future__ import annotations
import hashlib
from pathlib import PurePosixPath
import struct

FORMATS={0x1D01:1,0x1E01:2}


def digest(data):return hashlib.sha256(data).hexdigest()
def _bounds(data,offset,size,what):
    if offset<0 or size<0 or offset+size>len(data):raise ValueError(f'{what} outside its container')
def _read(data,fmt,offset,what):
    _bounds(data,offset,struct.calcsize(fmt),what)
    return struct.unpack_from(fmt,data,offset)


def sarc_members(data):
    if data[:4]!=b'SARC' or data[6:8]!=b'\xff\xfe':raise ValueError('Only little-endian SARC is supported')
    header,=_read(data,'<H',4,'SARC header size')
    size,doff=_read(data,'<II',8,'SARC size/data offset')
    if size!=len(data) or header<0x14 or doff>size:raise ValueError('Invalid SARC size/header/data offset')
    if data[header:header+4]!=b'SFAT':raise ValueError('Missing SFAT')
    sfat_size,count=_read(data,'<HH',header+4,'SFAT header')
    if sfat_size!=12:raise ValueError('Unexpected SFAT header size')
    nodes=header+sfat_size;sfnt=nodes+count*16
    _bounds(data,nodes,count*16,'SFAT nodes')
    if data[sfnt:sfnt+4]!=b'SFNT':raise ValueError('Missing SFNT')
    names_size,=_read(data,'<H',sfnt+4,'SFNT header size')
    names=sfnt+names_size
    if names_size!=8 or names>doff:raise ValueError('Invalid SFNT')
    result=[];seen=set()
    for index in range(count):
        namehash,attr,start,end=_read(data,'<4I',nodes+16*index,'SARC node')
        if not attr&0x01000000 or start>end:raise ValueError('Unnamed or reversed SARC member')
        pos=names+(attr&0x00FFFFFF)*4
        if not names<=pos<doff:raise ValueError('SARC name outside SFNT')
        stop=data.find(b'\0',pos,doff)
        if stop<0:raise ValueError('Unterminated SARC name')
        name=data[pos:stop].decode('utf-8')
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or '\\' in name or name in seen:
            raise ValueError('Unsafe or duplicate SARC name')
        seen.add(name);offset=doff+start;length=end-start
        _bounds(data,offset,length,'SARC member')
        result.append(dict(name=name,index=index,offset=offset,size=length,name_hash=namehash,sfat_node_offset=nodes+16*index))
    return result


def bntx_textures(data):
    if data[:4]!=b'BNTX' or data[12:14]!=b'\xff\xfe':raise ValueError('Only little-endian BNTX is supported')
    declared,=_read(data,'<I',0x1C,'BNTX file size')
    if declared!=len(data):raise ValueError('BNTX file size mismatch')
    count,=_read(data,'<I',0x24,'BNTX texture count')
    infos,=_read(data,'<Q',0x28,'BNTX info table')
    if not 0<count<=4096:raise ValueError('Invalid BNTX texture count')
    _bounds(data,infos,count*8,'BNTX info pointers')
    result=[]
    for index in range(count):
        header,=_read(data,'<Q',infos+8*index,'BRTI pointer')
        _bounds(data,header,0x78,'BRTI fields')
        if data[header:header+4]!=b'BRTI':raise ValueError('Missing BRTI')
        tile_mode,=_read(data,'<H',header+0x12,'tile mode')
        mips,=_read(data,'<H',header+0x16,'mip count')
        fmt,=_read(data,'<I',header+0x1C,'texture format')
        width,height,depth,layers,layout=_read(data,'<5I',header+0x24,'texture dimensions/layout')
        size,alignment=_read(data,'<2I',header+0x50,'payload size/alignment')
        nameptr,=_read(data,'<Q',header+0x60,'texture name pointer')
        namelen,=_read(data,'<H',nameptr,'texture name length')
        _bounds(data,nameptr+2,namelen,'texture name')
        name=data[nameptr+2:nameptr+2+namelen].decode('utf-8')
        mip_table,=_read(data,'<Q',header+0x70,'mip table pointer')
        if not 1<=mips<=32:raise ValueError('Invalid mip count')
        offsets=list(_read(data,'<'+'Q'*mips,mip_table,'mip offsets'))
        start=offsets[0];_bounds(data,start,size,'texture payload')
        if not name or not width or not height:raise ValueError('Missing texture name/dimensions')
        result.append(dict(name=name,index=index,width=width,height=height,depth=depth,layers=layers,
            format=f'0x{fmt:04x}',mips=mips,tile_mode=tile_mode,block_height_log2=layout&7,
            component_selectors=list(data[header+0x58:header+0x5C]),brti_offset=header,
            payload_offset_in_bntx=start,payload_size=size,mip_offsets_in_bntx=offsets,alignment=alignment))
    return result


def inspect_archive(data):
    result={}
    for member in sarc_members(data):
        payload=data[member['offset']:member['offset']+member['size']]
        if payload[:4]!=b'BNTX':continue
        for texture in bntx_textures(payload):
            name=texture['name']
            if name in result:raise ValueError('Ambiguous texture name across archive members')
            result[name]={**texture,'member_name':member['name'],'member_offset_in_archive':member['offset'],
                          'member_size':member['size'],'payload_offset_in_archive':member['offset']+texture['payload_offset_in_bntx']}
    return result


def _tiling_dimensions(blocks_w,blocks_h,block_bytes,block_height_log2):
    if min(blocks_w,blocks_h)<=0 or block_bytes not in (8,16) or not 0<=block_height_log2<=5:
        raise ValueError('Unsupported block dimensions/bytes/height')
    row=blocks_w*block_bytes;gob_height=8<<block_height_log2;gobs_x=(row+63)//64
    return row,gob_height,gobs_x


def _address(x,y,gob_height,gobs_x):
    by,inner_y=divmod(y,gob_height);gy,py=divmod(inner_y,8);gx,px=divmod(x,64)
    return (by*gobs_x+gx)*gob_height*64+gy*512+(px//32)*256+(py//2)*64+((px%32)//16)*32+(py%2)*16+px%16


def deswizzle(data,blocks_w,blocks_h,block_bytes,block_height_log2):
    row,gob_height,gobs_x=_tiling_dimensions(blocks_w,blocks_h,block_bytes,block_height_log2)
    out=bytearray(row*blocks_h)
    for y in range(blocks_h):
        for x in range(row):
            address=_address(x,y,gob_height,gobs_x)
            if address>=len(data):raise ValueError('Block-linear payload too short for addressed tile')
            out[y*row+x]=data[address]
    return bytes(out)


def reswizzle(linear,blocks_w,blocks_h,block_bytes,block_height_log2,template=None):
    row,gob_height,gobs_x=_tiling_dimensions(blocks_w,blocks_h,block_bytes,block_height_log2)
    if len(linear)!=row*blocks_h:raise ValueError('Linear block payload size mismatch')
    size=((blocks_h+gob_height-1)//gob_height)*gobs_x*gob_height*64
    out=bytearray(template) if template is not None else bytearray(size)
    for y in range(blocks_h):
        for x in range(row):
            address=_address(x,y,gob_height,gobs_x)
            if address>=len(out):raise ValueError('Template too short for addressed tile')
            out[address]=linear[y*row+x]
    return bytes(out)


def bc4_palette(first,last):
    if not 0<=first<=255 or not 0<=last<=255:raise ValueError('BC4U endpoint out of range')
    return ([first,last]+([((7-i)*first+i*last)//7 for i in range(1,7)] if first>last else
                         [((5-i)*first+i*last)//5 for i in range(1,5)]+[0,255]))


def decode_bc4_block(block):
    if len(block)!=8:raise ValueError('BC4 block must be eight bytes')
    palette=bc4_palette(block[0],block[1]);indices=int.from_bytes(block[2:],'little')
    return bytes(palette[(indices>>(3*i))&7] for i in range(16))


def encode_bc4_block(samples):
    samples=bytes(samples)
    if len(samples)!=16:raise ValueError('BC4 input must contain sixteen uint8 samples')
    low,high=min(samples),max(samples)
    if low==high:return bytes((high,low))+bytes(6)
    candidates=[]
    endpoints=[(high,low),(low,high)]
    interior=[v for v in samples if v not in (0,255)]
    if interior:endpoints.append((min(interior),max(interior)))
    for first,last in dict.fromkeys(endpoints):
        palette=bc4_palette(first,last);bits=0;error=0
        for index,value in enumerate(samples):
            choice=min(range(8),key=lambda n:(palette[n]-value)**2)
            error+=(palette[choice]-value)**2;bits|=choice<<(3*index)
        candidates.append((error,bytes((first,last))+bits.to_bytes(6,'little')))
    return min(enumerate(candidates),key=lambda pair:(pair[1][0],pair[0]))[1][1]


def decode_bc5_block(block):
    if len(block)!=16:raise ValueError('BC5 block must be sixteen bytes')
    return decode_bc4_block(block[:8]),decode_bc4_block(block[8:])


def encode_bc5_block(red,green):return encode_bc4_block(red)+encode_bc4_block(green)


def _guard(meta,payload):
    fmt=int(meta['format'],16) if isinstance(meta['format'],str) else meta['format']
    if fmt not in FORMATS:raise ValueError('Only BC4_UNORM/BC5_UNORM headings may be patched')
    if any(meta.get(k)!=1 for k in ('mips','layers','depth')) or meta.get('tile_mode')!=0:
        raise ValueError('Only single-mip single-layer 2D block-linear headings may be patched')
    width,height=meta['width'],meta['height'];bh=meta['block_height_log2'];channels=FORMATS[fmt]
    if len(payload)!=meta['payload_size']:raise ValueError('Native texture payload size mismatch')
    _tiling_dimensions((width+3)//4,(height+3)//4,channels*8,bh)
    return width,height,bh,channels


def decode_masks(meta,payload):
    width,height,bh,channels=_guard(meta,payload);bw,blocks_h=(width+3)//4,(height+3)//4
    linear=deswizzle(payload,bw,blocks_h,channels*8,bh);out=[bytearray(width*height) for _ in range(channels)]
    for by in range(blocks_h):
        for bx in range(bw):
            start=(by*bw+bx)*channels*8
            for channel in range(channels):
                values=decode_bc4_block(linear[start+channel*8:start+channel*8+8])
                for py in range(min(4,height-by*4)):
                    for px in range(min(4,width-bx*4)):
                        out[channel][(by*4+py)*width+bx*4+px]=values[py*4+px]
    return tuple(bytes(c) for c in out)


def encode_masks(meta,channel_data,template):
    width,height,bh,channels=_guard(meta,template)
    if len(channel_data)!=channels:raise ValueError('Channel count mismatch')
    arrays=[None if c is None else bytes(c) for c in channel_data]
    if any(c is not None and len(c)!=width*height for c in arrays):raise ValueError('Mask dimensions mismatch')
    bw,blocks_h=(width+3)//4,(height+3)//4;linear=bytearray(deswizzle(template,bw,blocks_h,channels*8,bh))
    for by in range(blocks_h):
        for bx in range(bw):
            for channel,array in enumerate(arrays):
                if array is None:continue
                pos=((by*bw+bx)*channels+channel)*8;old=decode_bc4_block(linear[pos:pos+8])
                same=all(old[y*4+x]==array[(by*4+y)*width+bx*4+x]
                         for y in range(min(4,height-by*4)) for x in range(min(4,width-bx*4)))
                if same:continue  # unchanged visible block: preserve its exact original encoding
                samples=bytes(array[min(height-1,by*4+y)*width+min(width-1,bx*4+x)] for y in range(4) for x in range(4))
                linear[pos:pos+8]=encode_bc4_block(samples)
    return reswizzle(linear,bw,blocks_h,channels*8,bh,template)


def patch_archive(data,replacements,*,expected_sha256,allow_color=False):
    if digest(data)!=expected_sha256:raise ValueError('Source archive SHA256 mismatch')
    if not replacements:raise ValueError('No texture replacements supplied')
    textures=inspect_archive(data);spans=[];details=[]
    for name,replacement in replacements.items():
        if name not in textures:raise ValueError('Requested texture is absent: '+name)
        meta=textures[name];start=meta['payload_offset_in_archive'];end=start+meta['payload_size']
        original=data[start:end]
        if allow_color and int(meta['format'],16) in (0x1a01,0x1c01,0x2001):
            from ui_color_codec import guard_color
            guard_color(meta,original)
        else:_guard(meta,original)
        if len(replacement)!=len(original):raise ValueError('Replacement would resize native texture payload')
        for other_name,other in textures.items():
            a=other['payload_offset_in_archive'];b=a+other['payload_size']
            if other_name!=name and max(a,start)<min(b,end):raise ValueError('Selected texture payload aliases another texture')
        spans.append((start,end,name,bytes(replacement)))
        details.append(dict(name=name,offset=start,bytes=len(original),old_sha256=digest(original),new_sha256=digest(replacement),
                            changed_bytes=sum(a!=b for a,b in zip(original,replacement)),metadata_unchanged=True))
    spans.sort()
    for a,b in zip(spans,spans[1:]):
        if a[1]>b[0]:raise ValueError('Texture replacement spans overlap')
    out=bytearray(data)
    for start,end,name,replacement in spans:out[start:end]=replacement
    result=bytes(out);cursor=0
    for start,end,_,_ in spans:
        if data[cursor:start]!=result[cursor:start]:raise AssertionError('Nonselected archive bytes changed')
        cursor=end
    if data[cursor:]!=result[cursor:] or len(result)!=len(data):raise AssertionError('Archive tail/length changed')
    if inspect_archive(result)!=textures:raise AssertionError('SARC/BNTX metadata changed')
    report=dict(source_sha256=digest(data),output_sha256=digest(result),bytes=len(result),
                replacements=details,outside_selected_payloads_byte_identical=True,metadata_byte_identical=True,
                scope='Only selected native compressed texture payload bytes; no BFLYT/pane/material/table edits')
    return result,report
