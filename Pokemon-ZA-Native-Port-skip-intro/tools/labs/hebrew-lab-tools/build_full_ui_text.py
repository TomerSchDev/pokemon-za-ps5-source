"""Compile reviewed English native UI image labels, preserving original geometry.

Inputs are read-only originals plus the r189 translated UI baseline. Every output
is tied to an exact original SHA256 and a preceding overlay SHA256. Color and
mask compressed blocks outside edits are preserved by their respective codecs.
"""
import argparse,json,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter,ImageDraw
from build_header_mod import glyph_mask,bbox,digest,blur
from ui_header_codec import inspect_archive,decode_masks,encode_masks,patch_archive
from ui_color_codec import decode_color,encode_color
from ui_text_terms import MASK_TERMS,COLOR_TERMS,MASK_REGIONS,PILL_IDS,OUTLINE_IDS,BLUR_IDS
from ui_nested_terms import nested_specs,nested_edit

LAB=Path(__file__).resolve().parents[1]
INVENTORY=LAB/'headers/reports/full-ui-text-inventory.json'
PREVIEWS=LAB/'headers/extract-full'
BASE=LAB/'build/full-hebrew-20261030-r189'

def mask_text(text,w,h,box):
    lines=text.split('\n');out=np.zeros((h,w),np.uint8)
    l,t,r,b=box;step=(b-t)/len(lines)
    for i,line in enumerate(lines):
        a,info=glyph_mask(line,w,h,[l,round(t+i*step),r,round(t+(i+1)*step)-1])
        # Center horizontally in the exact reviewed word box.
        ink=bbox(a);dx=(r-l-(ink[2]-ink[0]))//2
        if dx>0:a=np.roll(a,dx,axis=1)
        out=np.maximum(out,a)
    return out

def region_scaled(box,w,h,original_size):
    ow,oh=original_size
    return [round(box[0]*w/ow),round(box[1]*h/oh),round(box[2]*w/ow),round(box[3]*h/oh)]

def outline(mask,thickness):
    size=max(3,round(thickness)*2+1)
    high=np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(size))).astype(np.int16)
    low=np.asarray(Image.fromarray(mask).filter(ImageFilter.MinFilter(size))).astype(np.int16)
    return np.clip(high-low,0,255).astype(np.uint8)

def mask_edit(ch,spec,name):
    i=spec['index'];text=spec['hebrew'];h,w=ch[0].shape
    old=ch[-1];out=[a.copy() for a in ch]
    region=region_scaled(MASK_REGIONS[i],w,h,spec['size']) if i in MASK_REGIONS else None
    if i in (223,299):
        cols=np.any(old>32,axis=0);active=np.flatnonzero(cols)
        gaps=np.flatnonzero(np.diff(active)>2)
        if not len(gaps):raise ValueError('Missing preserved check icon gap')
        start=int(active[gaps[0]]+1);measure=old.copy();measure[:,:start]=0
        box=bbox(measure,32);out[-1][:,start:]=mask_text(text,w,h,box)[:,start:]
        return out,box
    if i==292 and not spec.get('english',True):
        box=bbox(old,120);new=mask_text('לחיצה על כפתור',w,h,box)
        return [np.full_like(new,255),new],box
    if i==88:
        boxes=[(72,39,112,59),(48,59,112,78)]
        for line,box in zip(text.split('\n'),boxes):
            box=region_scaled(box,w,h,spec['size']);l,t,r,b=box
            new=mask_text(line,w,h,box);out[0][t:b,l:r]=new[t:b,l:r]
        return out,region
    if i in PILL_IDS:
        # Black letter cutout inside an unchanged rounded badge alpha.
        black=(255-ch[0]).astype(np.uint8);black[old<100]=0
        box=bbox(black,100);new=mask_text(text,w,h,box)
        l,t,r,b=box;out[0][t:b,l:r]=255
        out[0]=np.minimum(out[0],255-new)
        return out,box
    if region:
        l,t,r,b=region;measure=np.zeros_like(old);measure[t:b,l:r]=old[t:b,l:r]
    else:measure=old
    if i==72:
        # The source has the word over a faint donut watermark. The watermark
        # channel is kept; restore its underlying low alpha before new text.
        l,t,r,b=region;new=mask_text(text,w,h,region)
        out[-1][:]=0
        # Exact source color channel isolates the donut inside its native box.
        dl,dt,dr,db=region_scaled((199,23,329,128),w,h,spec['size'])
        out[-1][dt:db,dl:dr]=(ch[0][dt:db,dl:dr].astype(np.float32)*(10/255)).astype(np.uint8)
        out[-1]=np.maximum(out[-1],(new.astype(np.float32)*.10).astype(np.uint8))
        return out,region
    if len(ch)==2:
        # Derive the sharp glyph from color where available, otherwise alpha.
        opaque=(measure>max(12,float(measure.max())*.65))
        values=ch[0][opaque]
        black_text=len(values)>0 and float(np.median(values))<90
        sharp=np.minimum(255-ch[0] if black_text else ch[0],measure)
        # Constant-color channels store all shape information in alpha.
        if np.count_nonzero(sharp>120)<5:sharp=measure
    else:sharp=measure;black_text=False
    threshold=max(2,min(160,int(sharp.max()*.65)))
    box=region or spec.get('reference_box') or bbox(sharp,threshold)
    new=mask_text(text,w,h,box)
    if i==89:
        # The source wraps around the upper-left radar chart edge. Rotate the
        # Hebrew word along that same diagonal instead of crossing the chart.
        ink=Image.fromarray(new).crop(bbox(new)).rotate(48,expand=True,resample=Image.Resampling.BICUBIC)
        ink.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS)
        new[:]=0;new[box[1]:box[1]+ink.height,box[0]:box[0]+ink.width]=np.asarray(ink)
    if i in OUTLINE_IDS:new=outline(new,max(1,(box[3]-box[1])*.025))
    if i in BLUR_IDS:new=np.clip(blur(new,max(2,(box[3]-box[1])*.09))*1.25,0,255).astype(np.uint8)
    if len(ch)==1:
        if region:
            l,t,r,b=region;out[0][t:b,l:r]=new[t:b,l:r]
        else:out[0]=new
        return out,box
    if region:
        l,t,r,b=region
        out[-1][t:b,l:r]=new[t:b,l:r]
        out[0][t:b,l:r]=(255-new if black_text else np.full_like(new,255))[t:b,l:r]
        return out,box
    # Retain the source's color backing box and recreate soft alpha. A single
    # sharp shape is shared across normal/drop-shadow/glow variants.
    if black_text:
        out[0][:]=255;out[0]=255-new
    elif np.min(ch[0])<90:
        active=old>2
        l,t,r,b=bbox(active.astype(np.uint8));out[0][t:b,l:r]=0
        out[0]=np.maximum(out[0],new)
    else:out[0][:]=255
    radius=2 if ('glow' in name or 'blur' in name) else 1.2
    # Dark letter layers have a sharp alpha, neon white ones a soft halo.
    alpha=new if black_text else np.clip(new.astype(np.float32)+blur(new,radius)*.65,0,255).astype(np.uint8)
    if name.endswith('_ds_00^t'):alpha=np.clip(blur(new,2),0,255).astype(np.uint8)
    out[-1]=alpha
    return out,box

def over(rgba,color,alpha):
    a=alpha.astype(np.float32)/255
    out=rgba.copy();out[:,:,:3]=np.rint(out[:,:,:3]*(1-a[:,:,None])+np.array(color)[None,None,:]*a[:,:,None]).astype(np.uint8)
    out[:,:,3]=np.maximum(out[:,:,3],alpha)
    return out

def neon(mask):
    halo=np.clip(blur(mask,8)*3+blur(mask,20)*1.8,0,255)
    h,w=mask.shape;stripe=np.where(np.arange(h)%6<2,.68,1)[:,None]
    alpha=np.clip((halo+mask)*stripe,0,255).astype(np.uint8)
    core=mask.astype(np.float32)/255
    out=np.empty((h,w,4),np.uint8);out[:,:,:3]=np.array([245,92,214])
    out[:,:,:3]=np.rint(out[:,:,:3]*(1-core[:,:,None])+255*core[:,:,None]).astype(np.uint8)
    out[:,:,3]=alpha
    return out

def color_edit(old,spec):
    i=spec['index'];text=spec['hebrew'];h,w=old.shape[:2];out=old.copy()
    if 53<=i<=75:
        sharp=np.where((old[:,:,0]>200)&(old[:,:,1]>190)&(old[:,:,3]>100),255,0).astype(np.uint8)
        if i<=63:
            # Render a continuous glow envelope; a hard cut through the source
            # halo leaves a visible seam. Rank characters remain semantically
            # identical, with their original small-word/large-letter hierarchy.
            letter='ABCDEFGWXYZ'[i-53]
            if letter=='G':letter='???' if spec.get('english',True) else '***'
            box=[round(w*.14),round(h*.64),round(w*.48),round(h*.80)]
            new=mask_text(text,w,h,box)
            big=mask_text(letter,w,h,[round(w*.51),round(h*.23),round(w*.91),round(h*.80)])
            out=neon(np.maximum(new,big))
        else:
            box=bbox(sharp);out=neon(mask_text(text,w,h,box))
        return out,box
    if 100<=i<=106:
        box=[56,5,w-4,h-5];l,t,r,b=box
        # Original background row at x=54 is clear of status icon and letters.
        out[t:b,l:r]=old[t:b,54:55]
        return over(out,(255,255,255),mask_text(text,w,h,[56,7,w-8,h-7])),box
    if i==108:
        box=[340,128,1068,198];l,t,r,b=box
        # Restore the unobstructed banner gradient from strips above/below.
        for y in range(t,b):
            ratio=(y-t)/max(1,b-t-1)
            out[y,l:r]=np.rint(old[123,l:r]*(1-ratio)+old[203,l:r]*ratio).astype(np.uint8)
        new=mask_text(text,w,h,[350,140,1058,182])
        out=over(out,(242,236,230),np.clip(blur(new,5)*.6,0,255).astype(np.uint8))
        return over(out,(255,255,255),new),box
    if i==139:
        letters=(old[:,:,0]>110)&(old[:,:,1]>215)&(old[:,:,2]>200)&(old[:,:,3]>100)
        box=bbox(letters.astype(np.uint8));l,t,r,b=box
        for y in range(t,b):
            bg=(old[y,:,0]<90)&(old[y,:,1]>150)&(old[y,:,3]>220)
            color=np.median(old[y,bg],axis=0).astype(np.uint8) if np.any(bg) else np.array([34,211,183,255],np.uint8)
            out[y,l:r]=color
        return over(out,(255,255,255),mask_text(text,w,h,box)),box
    if i==110:
        box=bbox(old[:,:,3],150);new=mask_text(text,w,h,box)
        # Blue gradient fill sampled row-wise from the opaque source letters.
        out[:]=0
        for y in range(h):
            p=old[y,old[y,:,3]>160,:3]
            out[y,:,:3]=np.median(p,axis=0).astype(np.uint8) if len(p) else [50,140,230]
        out[:,:,3]=new
        return out,box
    if i in (98,99):
        # Fictional shop headings: keep the cream ribbon tails at the extreme
        # left/right, replacing letter artwork inside the reviewed center.
        box=[44,36,w-48,h-35] if i==98 else [24,55,w-24,h-45]
        if i==98:
            out[:]=0
            ribbon=Image.fromarray(out)
            ImageDraw.Draw(ribbon).polygon([(35,140),(90,103),(w-70,105),(w-35,140),(w-90,130),(90,145)],fill=(255,255,240,255))
            out=np.asarray(ribbon).copy()
        else:out[:]=0
        new=mask_text(text,w,h,box)
        edge=np.asarray(Image.fromarray(new).filter(ImageFilter.MaxFilter(13 if i==98 else 11)))
        out=over(out,(255,255,240) if i==98 else (215,242,234),edge)
        return over(out,(244,115,147) if i==98 else (29,54,72),new),box
    raise ValueError(('Unreviewed color label',i))

def extra_specs(inv):
    result={}
    for entry in inv:
        if 'pokedex_top' in entry['path']:
            for name,m in entry['textures'].items():
                if name.startswith('grptext_pokedex_title_'):
                    result[name]=dict(index=310,hebrew='פוקידקס',color=False,extra=True)
                elif name.startswith('grptext_pokedex_subtitle_') and '_line_' not in name:
                    result[name]=dict(index=311,hebrew='לומיוז' if name=='grptext_pokedex_subtitle_00^q' else 'מרחב-על',color=m['format']=='0x1c01',extra=True)
        if 'btl_app_finish' in entry['path']:
            for name,m in entry['textures'].items():
                result[name]=dict(index=312,hebrew='ניצחון',color=m['format']=='0x1c01',extra=True)
    return result

def extra_edit(old,spec,name):
    color=spec['color'];h,w=old.shape[:2] if color else old[0].shape
    text=spec['hebrew'];i=spec['index'];region=None
    if i==310:box=[round(w*.04),round(h*.36),round(w*.96),round(h*.70)]
    elif i==311:
        box=[round(w*.33),round(h*.24),round(w*.67),round(h*.74)]
        if name=='grptext_pokedex_subtitle_00^q':region=[round(w*.375),0,round(w*.625),h];box=[region[0],round(h*.24),region[2],round(h*.74)]
    else:
        text='ניצחון' if spec.get('english',True) else 'הסתיים'
        if '_text_' in name:
            index=int(name.split('_text_')[1][:2]);letters=list('ןוחצינ' if spec.get('english',True) else 'םייתסה')
            text=letters[index] if index<len(letters) else ''
            box=[round(w*.08),round(h*.04),round(w*.92),round(h*.93)]
        else:box=[round(w*.18),round(h*.35),round(w*.82),round(h*.65)] if ('blur' in name or 'effect' in name) else [round(w*.18),round(h*.14),round(w*.82),round(h*.86)]
    core=mask_text(text,w,h,box) if text else np.zeros((h,w),np.uint8)
    if i==310:
        core=outline(core,2)
        if '_line_' not in name:core=np.clip(core.astype(float)+blur(core,8)*2,0,255).astype(np.uint8)
    elif 'blur' in name or '_ef_' in name or 'effect' in name:core=np.clip(blur(core,12)*1.5,0,255).astype(np.uint8)
    elif 'glow' in name:core=np.clip(core.astype(float)+blur(core,4)*1.2,0,255).astype(np.uint8)
    if 'blur_line' in name or 'effect' in name:core=(core*np.where(np.arange(h)%6<2,.3,1)[:,None]).astype(np.uint8)
    if not color:return ([np.full_like(core,255),core] if len(old)==2 else [core]),box
    out=old.copy() if region else np.zeros_like(old)
    if region:
        l,t,r,b=region;out[t:b,l:r]=0
    if '_text_' in name:
        out[:,:,:3]=[47,79,87];out[:,:,3]=core
        return out,box
    if i==311:
        out=over(out,(57,151,173),np.clip(blur(core,5)*1.6,0,255).astype(np.uint8))
    return over(out,(255,255,255),core),box

def specs_from_inventory(inv):
    unique=json.loads((PREVIEWS/'unique-previews.json').read_text(encoding='utf-8'))
    colors=json.loads((PREVIEWS/'color-previews.json').read_text(encoding='utf-8'))
    by_stem={Path(a['path']).stem:a for a in inv};specs={}
    for i,he in MASK_TERMS.items():
        entry=unique[i]
        for file in [entry['file'],*entry['copies']]:
            stem,preview=file.replace('\\','/').split('/')
            arc=by_stem[stem]
            matches=[n for n in arc['textures'] if n.replace('^','_')+'.png'==preview]
            if len(matches)!=1:raise ValueError(file)
            name=matches[0];m=arc['textures'][name]
            specs[name]=dict(index=i,hebrew=he,size=(m['width'],m['height']),color=False)
    # Additional native effect layers are independently present in the archive.
    for name in ('donut_select_text_ds_00^t','donut_select_text_glow_00^t'):
        specs[name]=dict(specs['donut_select_text_00^t'])
    for i,he in COLOR_TERMS.items():
        entry=colors[i]
        if entry['format'] not in ('0x1c01','0x2001'):raise ValueError(entry)
        specs[entry['texture']]=dict(index=i,hebrew=he,color=True)
    return specs

def effect_reference_box(native,raw,name,index):
    primary={66:'grptext_transition_title_text_00^s',67:'grptext_transition_title_text_00^s',293:'grptext_transition_title_text_00^s',
        117:'grptext_hud_ryl_start_00^t',118:'grptext_hud_ryl_start_00^t',119:'grptext_hud_ryl_title_00^t',120:'grptext_hud_ryl_title_00^t',
        73:'donut_select_text_00^t',246:'grptext_quest_info_dim_00^t',247:'grptext_quest_info_main_00^s',
        248:'grptext_quest_info_main_e_00^s',249:'grptext_quest_info_sub_00^s',250:'grptext_quest_info_sub_e_00^s',
        251:'grptext_quest_info_dim_00^t',252:'grptext_quest_info_main_00^s',253:'grptext_quest_info_main_e_00^s',254:'grptext_quest_info_sub_00^s',255:'grptext_quest_info_sub_e_00^s'}.get(index)
    if not primary:return None
    def measure(n):
        m=native[n];p=m['payload_offset_in_archive'];ch=decode_masks(m,raw[p:p+m['payload_size']])
        alpha=np.frombuffer(ch[-1],np.uint8).reshape(m['height'],m['width'])
        return bbox(alpha,max(1,round(alpha.max()*.65)))
    p=measure(primary);q=measure(name);cx=(q[0]+q[2])/2;cy=(q[1]+q[3])/2
    width=p[2]-p[0];height=p[3]-p[1]
    return [round(cx-width/2),round(cy-height/2),round(cx+width/2),round(cy+height/2)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--reuse');p.add_argument('--redo-prefix',action='append',default=[]);args=p.parse_args()
    out=LAB/'headers/build'/args.out
    if out.exists():raise FileExistsError(out)
    inv=json.loads(INVENTORY.read_text(encoding='utf-8'));specs=specs_from_inventory(inv)
    extra=json.loads((LAB/'headers/extract-common-extra/inventory.json').read_text())+json.loads((LAB/'headers/extract-common-extra/inventory-extra-english.json').read_text())
    extra=[r for r in extra if 'pokedex_top' in r['path'] or 'btl_app_finish' in r['path']]
    for r in extra:r['source']=str(Path('headers/extract-common-extra')/Path(r['path']).stem/'archive.arc')
    inv+=extra;specs.update(extra_specs(extra))
    nested=json.loads((LAB/'headers/extract-nested/inventory.json').read_text(encoding='utf-8'))
    by_path={r['path']:r for r in inv}
    for r in nested:
        if r['path'] in by_path:
            if (LAB/r['source']).read_bytes()!=(LAB/by_path[r['path']]['source']).read_bytes():raise ValueError('Duplicate inventory source differs')
        else:by_path[r['path']]=r
    inv=list(by_path.values());specs.update(nested_specs(nested))
    prior=LAB/'headers/build'/args.reuse if args.reuse else None
    prior_rows=json.loads((prior/'native-text-review.json').read_text(encoding='utf-8')) if prior else []
    prior_map={(r['archive'],r['texture']):r for r in prior_rows}
    prior_by_content={(r['texture'],r['source_payload_sha256'],r['width'],r['height'],r['format']):r for r in prior_rows}
    prior_previews={(r['texture'],r['source_payload_sha256']):r['preview'] for r in prior_rows if 'preview' in r}
    redo_mask=set();redo_color=set()
    if args.reuse and args.reuse.endswith(('-r1','-r2')):redo_mask.update({66,67,73,117,118,119,120,*range(246,256),293})
    # r1 -> r2 fixes are retained when this pass aligns effect typography.
    if args.reuse and args.reuse.endswith('-r1'):
        redo_mask.update({72,88,223,292,299});redo_color.update({*range(53,64),98,*range(100,107),139})
    out.mkdir(parents=True);(out/'previews').mkdir();checks=[];records=[];seen={};cache={}
    for entry in inv:
        original=(LAB/entry['source']).read_bytes();native=inspect_archive(original)
        selected={n:s for n,s in specs.items() if n in native}
        if not selected:continue
        baseline=BASE/'mods/hebrew/romfs'/entry['path'];before=baseline.read_bytes() if baseline.exists() else original
        if inspect_archive(before)!=native:raise ValueError('Baseline metadata changed')
        replacements={}
        for name,spec in selected.items():
            spec=dict(spec,english=entry['path'].endswith('_eng.arc'))
            m=native[name];start=m['payload_offset_in_archive'];raw=original[start:start+m['payload_size']]
            key=(name,digest(raw),m['width'],m['height'])
            prior_record=prior_map.get((entry['path'],name)) or prior_by_content.get((name,digest(raw),m['width'],m['height'],m['format']))
            reusable=prior_record is not None and spec['index'] not in (redo_color if spec['color'] else redo_mask) and not any(name.startswith(p) for p in args.redo_prefix)
            if reusable:
                record=prior_record
                reused=(prior/'mods/hebrew/romfs'/record['archive']).read_bytes();rm=inspect_archive(reused)[name];rs=rm['payload_offset_in_archive']
                patched=reused[rs:rs+rm['payload_size']]
                if digest(raw)!=record['source_payload_sha256'] or digest(patched)!=record['replacement_sha256']:raise ValueError('Reuse source mismatch')
                details={k:v for k,v in record.items() if k not in ('archive','original_archive_sha256','preview')}
                preview=Image.open(prior/'previews'/prior_previews[(name,digest(raw))]).copy()
            elif key in cache:patched,details,preview=cache[key]
            else:
                if spec['color']:
                    old=decode_color(m,raw);edited,box=nested_edit(old,spec,name,native,original) if spec.get('nested') else extra_edit(old,spec,name) if spec.get('extra') else color_edit(old,spec);patched=encode_color(m,edited,raw)
                    decoded=decode_color(m,patched);preview=Image.fromarray(decoded)
                else:
                    old=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']) for c in decode_masks(m,raw)]
                    spec['reference_box']=effect_reference_box(native,original,name,spec['index'])
                    edited,box=nested_edit(old,spec,name,native,original) if spec.get('nested') else extra_edit(old,spec,name) if spec.get('extra') else mask_edit(old,spec,name);patched=encode_masks(m,[a.tobytes() for a in edited],raw)
                    dec=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']) for c in decode_masks(m,patched)]
                    decoded=dec[-1]
                    if len(dec)==2:
                        rgba=np.dstack((dec[0],dec[0],dec[0],dec[-1]));preview=Image.fromarray(rgba)
                    else:
                        rgba=np.full((*decoded.shape,4),255,np.uint8);rgba[:,:,3]=decoded;preview=Image.fromarray(rgba)
                details=dict(texture=name,logical=spec['hebrew'],source_payload_sha256=digest(raw),replacement_sha256=digest(patched),format=m['format'],width=m['width'],height=m['height'],text_box=box)
                cache[key]=(patched,details,preview)
            replacements[name]=patched
            rec=dict(details,archive=entry['path'],original_archive_sha256=digest(original))
            visual_key=(name,digest(raw))
            if visual_key not in seen:
                idx=len(seen);seen[visual_key]=idx
                file=f'{idx:03d}-{Path(entry["path"]).stem}-{name.replace("^","_")}.png'
                preview.save(out/'previews'/file);rec['preview']=file
            records.append(rec)
        result,verify=patch_archive(before,replacements,expected_sha256=digest(before),allow_color=True)
        target=out/'mods/hebrew/romfs'/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(result)
        checks.append(dict(file=entry['path'],sha256=digest(result),source_sha256=digest(original),prior_sha256=digest(before) if baseline.exists() else None,verification=verify))
        print(json.dumps(dict(archive=entry['path'],textures=len(replacements))),flush=True)
    # Include existing native headings that did not need further image text.
    for src in (BASE/'mods/hebrew/romfs/ui').rglob('*.arc'):
        rel=src.relative_to(BASE/'mods/hebrew/romfs');dest=out/'mods/hebrew/romfs'/rel
        if dest.exists():continue
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        checks.append(dict(file=rel.as_posix(),sha256=digest(src.read_bytes()),prior_sha256=digest(src.read_bytes()),retained_previously_translated=True))
    (out/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'native-text-review.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Full-size transparent previews and compact contact sheets for visual review.
    unique=[r for r in records if 'preview' in r]
    for page in range((len(unique)+9)//10):
        sheet=Image.new('RGB',(1100,1400),(34,34,34));draw=ImageDraw.Draw(sheet)
        for row,r in enumerate(unique[page*10:(page+1)*10]):
            draw.text((8,row*140+5),r['preview'],fill='orange')
            im=Image.open(out/'previews'/r['preview']);im.thumbnail((1000,108))
            sheet.paste(im,(20,row*140+28),im)
        sheet.save(out/'previews'/f'contact-{page:02d}.png')
    print(json.dumps(dict(output=str(out),archives=len(checks),textures=len(records),unique_previews=len(unique))),flush=True)

if __name__=='__main__':main()
