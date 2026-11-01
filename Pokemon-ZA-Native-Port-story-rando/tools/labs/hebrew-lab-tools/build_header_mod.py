"""Compile common and English UI labels into the game's native BC masks.

Only selected, same-size BNTX payloads change. Layouts/materials/animations, source
game files and the pending bulk-translation glossary remain unchanged.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from fontTools.ttLib import TTFont
from rtl import to_visual
from ui_header_codec import inspect_archive,decode_masks,encode_masks,patch_archive

LAB=Path(__file__).resolve().parents[1]
FONT=LAB/'build/ZAHebrewSans-Bold.ttf'
SPECS=[
    dict(archive='main_menu_top_00_eng',english='Menu',hebrew='תפריט',
         primary='grptext_cmn_opguide_title_00^s',glow='grptext_cmn_opguide_title_glow_00^t',
         scan='grptext_cmn_opguide_title_scanline_00^t',preserve_x=208,scan_period=7),
    dict(archive='main_menu_report_00_eng',english='Save',hebrew='שמירה',primary='grptext_main_menu_report_title_00^s'),
    dict(archive='main_menu_report_00_eng',english='Backup Data',hebrew='נתוני גיבוי',primary='grptext_main_menu_report_title_01^s'),
    dict(archive='player_select_00_eng',english='Appearance',hebrew='מראה',primary='grptext_player_select_title_00^s',
         glow='grptext_player_select_title_glow_00^t',scan='grptext_player_select_title_scanline_00^s',scan_period=5),
    dict(archive='player_select_confirm_00_eng',english='Confirm Choices',hebrew='אישור הבחירות',primary='grptext_player_select_title_01^s',
         glow='grptext_player_select_title_glow_01^t',scan='grptext_player_select_title_scanline_01^s',scan_period=5),
]

def digest(data):return hashlib.sha256(data).hexdigest()
def bbox(a,threshold=1):
    ys,xs=np.nonzero(a>=threshold)
    if len(xs)==0:raise ValueError('Empty heading mask')
    return [int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]

def glyph_mask(text,width,height,reference_box,font_bytes=None):
    """New code-native label raster, with visual-order Hebrew and fixed native geometry."""
    data=font_bytes or FONT.read_bytes();cmap=TTFont(io.BytesIO(data)).getBestCmap()
    if any(ord(ch) not in cmap for ch in text if not ch.isspace()):raise ValueError('Heading font lacks glyph')
    visual=to_visual(text)
    font=ImageFont.truetype(io.BytesIO(data),size=256,layout_engine=ImageFont.Layout.BASIC)
    x0,y0,x1,y1=font.getbbox(visual)
    big=Image.new('L',(x1-x0+16,y1-y0+16),0)
    ImageDraw.Draw(big).text((8-x0,8-y0),visual,font=font,fill=255)
    ink=big.crop(big.getbbox());left,top,right,bottom=reference_box
    scale=min((bottom-top)/ink.height,(right-left)/ink.width)
    size=(max(1,round(ink.width*scale)),max(1,round(ink.height*scale)))
    ink=ink.resize(size,Image.Resampling.LANCZOS)
    result=Image.new('L',(width,height),0)
    result.paste(ink,(left,top+(bottom-top-size[1])//2))
    a=np.asarray(result).copy()
    return a,dict(logical=text,visual=visual,source_box=reference_box,compiled_box=bbox(a),font_sha256=digest(data))

def aligned(mask,width,height):
    if mask.shape[1]!=width:raise ValueError('Effect width changed')
    out=np.zeros((height,width),np.uint8);delta=(height-mask.shape[0])//2
    if delta<0:raise ValueError('Effect canvas smaller than primary')
    out[delta:delta+mask.shape[0]]=mask
    return out

def blur(mask,radius):return np.asarray(Image.fromarray(mask).filter(ImageFilter.GaussianBlur(radius)),dtype=np.float32)

def fitted_halo(old_core,old_alpha,new_core,stripe,radii):
    """Fit the existing soft-light envelope away from sharp glyph pixels."""
    target=old_alpha.astype(np.float32)/np.maximum(stripe[:,None],.02)
    valid=(old_core==0)&(stripe[:,None]>.5)&(target<245)
    best=None
    for radius in radii:
        old_blur=blur(old_core,radius)
        select=valid&(old_blur>2)
        x=old_blur[select];y=target[select]
        if len(x)<32:continue
        gain=float(np.clip(np.dot(x,y)/max(1,np.dot(x,x)),.1,8))
        error=float(np.mean((x*gain-y)**2))
        if best is None or error<best[0]:best=(error,radius,gain)
    if best is None:raise ValueError('Cannot infer original heading halo')
    return blur(new_core,best[1])*best[2]

def make_layers(mask,role,original,preserve_x=0,source_mask=None,scan_period=5):
    h,w=original[0].shape;core=aligned(mask,w,h)
    ink_box=bbox(core);cap=ink_box[3]-ink_box[1]
    old_core=aligned(source_mask,w,h)
    effect_core=core.copy()
    if preserve_x:effect_core[:,:preserve_x]=old_core[:,:preserve_x]
    if role=='primary':layers=[core]
    elif role=='glow':
        # Keep the native large black backing region. A new tight rectangle
        # creates a visible edge when the shader samples the soft halo.
        color=original[0].copy();old_word=old_core.copy();old_word[:,:preserve_x]=0
        l,t,r,b=bbox(old_word)
        color[max(0,t-2):min(h,b+2),max(0,l-2):min(w,r+2)]=0
        color=np.maximum(color,core)
        halo=fitted_halo(old_core,original[-1],effect_core,np.ones(h,np.float32),
                         [max(1,cap*f) for f in (.15,.20,.25,.30,.40,.50)])
        alpha=np.clip(effect_core.astype(np.float32)+halo,0,255).astype(np.uint8)
        layers=[color,alpha]
    elif role=='scan':
        old_alpha=original[-1]
        # Native cadence: MENU seven pixels, player selection five. Estimate
        # each phase on rows that cross sharp source glyphs, not in the halo.
        peaks=old_alpha.max(axis=1).astype(np.float32)/255
        active=old_core.max(axis=1)>240
        profile=np.array([np.median(peaks[active&(np.arange(h)%scan_period==phase)]) for phase in range(scan_period)])
        if not np.all(np.isfinite(profile)):raise ValueError('Missing scan stripe phase')
        stripe=profile[np.arange(h)%scan_period]
        halo=fitted_halo(old_core,old_alpha,effect_core,stripe,
                         [max(1,cap*f) for f in (.30,.40,.50,.65,.80,1.0)])
        coverage=np.clip(effect_core.astype(np.float32)+halo,0,255)
        alpha=(coverage*stripe[:,None]).astype(np.uint8)
        layers=[original[0].copy(),alpha] if len(original)==2 else [alpha]
    else:raise ValueError(role)
    if role!='primary' and preserve_x:
        # Join the preserved native icon halo smoothly to the new word halo.
        alpha=layers[-1]
        for dx in range(min(48,w-preserve_x)):
            weight=(dx+1)/49
            alpha[:,preserve_x+dx]=(original[-1][:,preserve_x]*(1-weight)+alpha[:,preserve_x+dx]*weight).astype(np.uint8)
    if len(layers)!=len(original):raise ValueError('Native channel count changed')
    for index,layer in enumerate(layers):
        if preserve_x:layer[:,:preserve_x]=original[index][:,:preserve_x]
    return layers

def main(output):
    output=output.resolve()
    if not output.is_relative_to(LAB/'headers/build'):raise ValueError('Output must remain in headers/build')
    if output.exists():raise FileExistsError('Choose a new header revision')
    sources=[json.loads((LAB/'headers/reports'/name).read_text(encoding='utf-8'))
             for name in ('extraction.json','extraction-base.json')]
    archives={Path(a['game_path']).stem:a for source in sources for a in source['archives']}
    # Runtime loads the common .arc for these panes and may overlay _eng later.
    # Patch each exact source archive separately; their unrelated contents differ.
    base_terms={'Menu':('Menu','תפריט'),'Save':('Report','דוח'),
                'Backup Data':('Backup','גיבוי'),'Appearance':('Looks','מראה'),
                'Confirm Choices':('Profile','פרופיל')}
    specs=SPECS+[dict(spec,archive=spec['archive'].removesuffix('_eng'),
                     english=base_terms[spec['english']][0],hebrew=base_terms[spec['english']][1])
                 for spec in SPECS]
    records=[];texture_records=[];font_bytes=FONT.read_bytes()
    output.mkdir(parents=True);previews=output/'previews';previews.mkdir()
    for archive_name in dict.fromkeys(s['archive'] for s in specs):
        record=archives[archive_name];original=(LAB/record['extracted_archive']).read_bytes()
        if digest(original)!=record['sha256']:raise ValueError('Extracted archive changed')
        meta=inspect_archive(original);replacements={}
        archive_previews=previews/archive_name;archive_previews.mkdir()
        for spec in [s for s in specs if s['archive']==archive_name]:
            primary=meta[spec['primary']];p=primary['payload_offset_in_archive']
            raw=original[p:p+primary['payload_size']]
            old=np.frombuffer(decode_masks(primary,raw)[0],np.uint8).reshape(primary['height'],primary['width'])
            measure=old.copy();measure[:,:spec.get('preserve_x',0)]=0
            mask,info=glyph_mask(spec['hebrew'],primary['width'],primary['height'],bbox(measure),font_bytes)
            for role in ('primary','glow','scan'):
                if role not in spec:continue
                name=spec[role];m=meta[name];start=m['payload_offset_in_archive'];before=original[start:start+m['payload_size']]
                original_channels=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']).copy() for c in decode_masks(m,before)]
                layers=make_layers(mask,role,original_channels,spec.get('preserve_x',0),old,spec.get('scan_period',5))
                native=encode_masks(m,[a.tobytes() for a in layers],before)
                decoded=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']) for c in decode_masks(m,native)]
                icon_ok=all(np.array_equal(a[:,:spec.get('preserve_x',0)],b[:,:spec.get('preserve_x',0)]) for a,b in zip(original_channels,decoded))
                assert icon_ok and len(native)==len(before)
                # Quantized masks must remain close to the new font raster.
                error=max(float(np.abs(a.astype(np.int16)-b.astype(np.int16)).max()) for a,b in zip(layers,decoded))
                assert error<=37,(name,error)
                replacements[name]=native
                safe=name.replace('^','_');image=Image.fromarray(decoded[-1]);image.save(archive_previews/(safe+'.png'))
                if role=='primary':
                    transparent=Image.new('RGBA',(m['width'],m['height']),(255,255,255,0));transparent.putalpha(image)
                    transparent.save(archive_previews/(safe+'-label.png'))
                texture_records.append(dict(archive=record['game_path'],texture=name,role=role,english=spec['english'],
                    typography=info,width=m['width'],height=m['height'],format=m['format'],payload_bytes=len(native),
                    before_sha256=digest(before),after_sha256=digest(native),maximum_quantization_error=error,
                    scan_period=spec.get('scan_period') if role=='scan' else None,
                    menu_icon_preserved=icon_ok,preserved_left_columns=spec.get('preserve_x',0)))
        patched,verification=patch_archive(original,replacements,expected_sha256=record['sha256'])
        target=output/'mods/hebrew-headers/romfs'/record['game_path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(patched)
        assert target.read_bytes()==patched and len(patched)==len(original)
        records.append(dict(game_path=record['game_path'],bytes=len(patched),source_sha256=record['sha256'],
            replacement_sha256=digest(patched),file=target.relative_to(output).as_posix(),verification=verification))
    licenses=output/'mods/hebrew-headers/licenses';licenses.mkdir(parents=True)
    shutil.copyfile(LAB/'fonts-src/OFL.txt',licenses/'Noto-OFL.txt')
    (licenses/'FONT-NOTICE.txt').write_text('Headings compiled from ZA Hebrew Sans, a modified font built from Noto Sans, Noto Sans Hebrew and Noto Sans Math. SIL Open Font License 1.1.\n',encoding='utf-8')
    with (output/'heading-terms.tsv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,['english','hebrew','category','note'],delimiter='\t',lineterminator='\n');writer.writeheader()
        terms={spec['english']:spec['hebrew'] for spec in specs}
        for en,he in terms.items():writer.writerow(dict(english=en,hebrew=he,category='ui_header',note='Scoped header replacement requested by user; common and English variants use their exact source words; full glossary approval remains pending'))
    report=dict(kind='native-common-and-English-slot-header-replacements',version=output.name,game='2.0.2 + Mega Dimension',
        phrases=len(terms),heading_positions=5,archives=records,textures=texture_records,font_sha256=digest(font_bytes),source_game_modified=False,
        glossary_sha256=digest((LAB/'glossary.tsv').read_bytes()),bulk_glossary_approval='pending',
        rendering='Deterministic Hebrew glyph raster compilation, native BC4/BC5 masks, original layout/material/animation bytes preserved',
        hardware_status='PC QA pending; no PS5 installation')
    (output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(stage='native header package compiled',out=str(output),archives=len(records),textures=len(texture_records),phrases=len(terms))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=LAB/'headers/build/headings-r1');args=p.parse_args();main(args.out)
