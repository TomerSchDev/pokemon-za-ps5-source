"""Native BC1/BC3/BC7 color labels; untouched blocks and tiling padding are exact.

Encoder: ispc_texcomp 1.0.1 (MIT), https://github.com/K0lb3/ispc_texcomp_py.
No texture metadata, dimensions, mip layout or archive tables are rewritten.
"""
import numpy as np
from PIL import Image
import ispc_texcomp as ispc
from ui_header_codec import deswizzle,reswizzle

FORMATS={0x1a01:(1,8),0x1c01:(3,16),0x2001:(7,16)}

def guard_color(meta,payload):
    fmt=int(meta['format'],16)
    if fmt not in FORMATS:raise ValueError('Unsupported color format')
    if any(meta.get(k)!=1 for k in ('mips','layers','depth')) or meta.get('tile_mode')!=0:
        raise ValueError('Only single mip/layer/depth, block-linear textures')
    if len(payload)!=meta['payload_size']:raise ValueError('Native payload size mismatch')
    return meta['width'],meta['height'],meta['block_height_log2'],*FORMATS[fmt]

def decode_color(meta,payload):
    w,h,bhl,bcn,bs=guard_color(meta,payload);bw,bh=(w+3)//4,(h+3)//4
    linear=deswizzle(payload,bw,bh,bs,bhl)
    return np.asarray(Image.frombytes('RGBA',(bw*4,bh*4),linear,'bcn',(bcn,)).crop((0,0,w,h))).copy()

def encode_color(meta,rgba,template):
    w,h,bhl,bcn,bs=guard_color(meta,template);bw,bh=(w+3)//4,(h+3)//4
    if rgba.shape!=(h,w,4) or rgba.dtype!=np.uint8:raise ValueError('Expected native uint8 RGBA geometry')
    old=decode_color(meta,template)
    if np.array_equal(old,rgba):return template
    padded=np.pad(rgba,((0,bh*4-h),(0,bw*4-w),(0,0)),mode='edge')
    surface=ispc.RGBASurface(padded.tobytes(),bw*4,bh*4)
    if bcn==7:encoded=ispc.compress_blocks_bc7(surface,ispc.BC7EncSettings.from_profile('alpha_slow'))
    elif bcn==3:encoded=ispc.compress_blocks_bc3(surface)
    else:encoded=ispc.compress_blocks_bc1(surface)
    linear=bytearray(deswizzle(template,bw,bh,bs,bhl))
    for y in range(bh):
        for x in range(bw):
            if not np.array_equal(old[y*4:(y+1)*4,x*4:(x+1)*4],rgba[y*4:(y+1)*4,x*4:(x+1)*4]):
                p=(y*bw+x)*bs;linear[p:p+bs]=encoded[p:p+bs]
    return reswizzle(linear,bw,bh,bs,bhl,template)
