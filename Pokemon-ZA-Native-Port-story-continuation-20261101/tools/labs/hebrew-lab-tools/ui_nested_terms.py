"""Reviewed labels in UI archives stored after a pack's first member."""
import re
import numpy as np
from PIL import Image,ImageFilter
from build_header_mod import bbox,glyph_mask,blur,make_layers
from ui_header_codec import decode_masks

TYPE_TERMS=['רגיל','לחימה','מעופף','רעל','אדמה','סלע','חרק','רוח','פלדה','אש','מים','עשב','חשמל','על-חושי','קרח','דרקון','אופל','פיה']
DIM_TERMS=['אזור פרא במרחב-על','אזור קרב במרחב-על','לא ידוע','זירת מגה משתוללת במרחב-על']

def nested_specs(inv):
    result={}
    def add(n,he,kind='simple',**kw):
        result[n]=dict(index=1000,hebrew=he,nested=True,kind=kind,**kw)
    for a in inv:
        for n,m in a['textures'].items():
            if n=='grptext_option_controlsetting_title_00^s':add(n,'בקרות')
            elif n=='grptext_box_search_dialog_title_00^s':add(n,'חיפוש')
            elif n.startswith('grptext_box_title_'):
                key=n.removeprefix('grptext_box_title_').split('^')[0].removesuffix('_00').removesuffix('_glow').removesuffix('_scanline')
                he={'link_trade':'החלפה מקושרת','box_viewer':'כל הקופסאות','battle_team':'צוותי קרב','box':'קופסאות','items':'חפצים מוחזקים'}.get(key)
                if he:add(n,he,'heading',primary=f'grptext_box_title_{key}_00^s',keep=0)
            elif n=='grptext_cmn_new_00^q':add(n,'חדש','pill')
            elif n=='grptext_dress_up_complete_00^s':add(n,'הכול נאסף','region',region=[28,14,202,46],fixed_box=[36,17,195,42])
            elif n in ('grptext_shop_buy_00^s','grptext_shop_sell_00^s'):
                buy='buy' in n;add(n,'קנייה' if buy else 'מכירה','region',region=[12,0,152,42] if buy else [208,0,340,42])
            elif re.match(r'grptext_cmn_opguide_title_(?:glow_|scanline_)?(09|10|12)\^',n):
                idx=n.split('^')[0][-2:];he={'09':'לבוש','10':'מראה','12':'צבע שיער'}[idx]
                add(n,he,'heading',primary=f'grptext_cmn_opguide_title_{idx}^s',keep=0)
            elif n.startswith('grptxt_icon_type_text_'):
                add(n,TYPE_TERMS[int(n.split('_text_')[1][:2])],'type')
            elif n in ('grptext_pokedex_title_01^t','grptext_pokedex_title_02^q'):add(n,'פוקידקס','pokedex',keep=72)
            elif re.match(r'grptext_map_title_(?:glow_|scanline_)?00\^',n):
                add(n,'מפה','heading',primary='grptext_map_title_00^s',keep=140)
            elif re.match(r'grptext_map_dim_title_(?:glow_|scanline_)?0[0-3]\^',n):
                idx=int(n.split('^')[0][-2:]);add(n,DIM_TERMS[idx],'heading',primary=f'grptext_map_dim_title_{idx:02}^s',keep=140)
            elif n.startswith('cmn_dim_zone_text_'):
                idx=int(n.split('^')[0][-2:]);he=['אזור פרא\nבמרחב-על','אזור קרב\nבמרחב-על','לא ידוע','זירת מגה משתוללת\nבמרחב-על','זירת מגה משתוללת\nבמרחב-על'][idx]
                add(n,he,'dimzone',zone=min(idx,3))
            elif n=='cmn_dim_zone_info_text_00^t':add(n,'זוהתה אנרגיה אדירה!','diminfo')
            elif n=='cmn_dim_zone_lv_text_00^t':add(n,'רמה','region',region=[8,0,150,70])
            elif n=='grptext_map_zone_battle_00^s':add(n,'אזור קרב')
            elif n=='grptext_map_zone_comp^s':add(n,'הושלם')
            elif n.startswith('grptext_map_zone_wild_'):add(n,'אזור פרא','wild')
            elif n.startswith('grptext_btl_net_finish_'):add(n,'הסתיים','finish')
            elif n=='grptext_btl_net_stage_rank_00^q':add(n,'קרב מדורג','marquee')
            elif n=='grptext_btl_net_stage_private_00^t':add(n,'קרב פרטי','marquee')
            elif n=='grptext_donut_shop_title_02^u':add(n,'דונאט חדש!','donut')
            elif n=='grptext_donut_shop_result_radarchart_00^s':add(n,'פרופיל טעם','diagonal')
            elif n.startswith('grptext_hud_ryl_chance_'):
                sentence='_text_' in n;add(n,'זו ההזדמנות שלך!' if sentence else 'יתרון','effect',primary='grptext_hud_ryl_chance_text_00^t' if sentence else 'grptext_hud_ryl_chance_00^t')
            elif n.startswith('grptext_hud_ryl_vs_'):
                sentence='_text_' in n;add(n,'קיבלת אתגר לקרב!' if sentence else 'קרב','effect',primary='grptext_hud_ryl_vs_text_00^t' if sentence else 'grptext_hud_ryl_vs_00^t')
            elif re.match(r'grptext_hud_ryl_(max|win|wins|medal|point|rank_rank|rank_up|end|gekiha|medal_text|money|ticket_text)_',n):
                key=n.removeprefix('grptext_hud_ryl_').split('^')[0].removesuffix('_00').removesuffix('_01').removesuffix('_blur').removesuffix('_line')
                he={'max':'מרבי','win':'ניצחון','wins':'ניצחונות','medal':'מדליות','point':'נקודות','rank_rank':'דרגה','rank_up':'עלייה!','end':'הושבת','gekiha':'מאמנים שהובסו','medal_text':'מדליות שהושגו','money':'סך כספי הפרס','ticket_text':'הושג כרטיס מתמודד!'}[key]
                add(n,he,'effect')
            elif n=='grptext_hud_ryl_rewards_00^t':add(n,'פרסים','side_lines')
            elif n=='grptext_main_menu_mresearch_complete_00^t':add(n,'הושלם','effect')
            elif n=='grptext_main_menu_mresearch_lv_00^s':add(n,'רמה')
            elif n=='grptext_main_menu_mresearch_nextlv_00^t':add(n,'הפרס הבא','side_lines')
            elif n=='grptext_main_menu_mresearch_receive_00^s':add(n,'מוכן לקבלה!')
            elif n=='grptext_main_menu_mresearch_title_00^q':add(n,'המחקר של מייבל','mable')
            elif n=='grptext_quest_info_complete_00^s':add(n,'הושלם')
            elif n=='grptext_quest_info_compbase_00^s':add(n,'הושלם','effect',primary='grptext_quest_info_complete_00^s',soft=True)
            if n in result:
                result[n]['color']=m['format'] in ('0x1c01','0x2001')
                result[n]['size']=(m['width'],m['height'])
    return result

def text_mask(text,w,h,box):
    result=np.zeros((h,w),np.uint8);lines=text.split('\n');l,t,r,b=box;step=(b-t)/len(lines)
    for i,line in enumerate(lines):
        mask,_=glyph_mask(line,w,h,[l,round(t+i*step),r,round(t+(i+1)*step)-1]);ink=bbox(mask)
        dx=(r-l-(ink[2]-ink[0]))//2
        if dx>0:mask=np.roll(mask,dx,axis=1)
        result=np.maximum(result,mask)
    return result

def edge(mask):
    hi=np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(3))).astype(np.int16)
    lo=np.asarray(Image.fromarray(mask).filter(ImageFilter.MinFilter(3))).astype(np.int16)
    return np.clip(hi-lo,0,255).astype(np.uint8)

def nested_edit(old,spec,name,native,raw):
    color=spec['color'];kind=spec['kind'];text=spec['hebrew'];h,w=old.shape[:2] if color else old[0].shape
    def channels(n):
        m=native[n];p=m['payload_offset_in_archive']
        return [np.frombuffer(c,np.uint8).reshape(m['height'],m['width']) for c in decode_masks(m,raw[p:p+m['payload_size']])]
    if kind=='heading':
        src=channels(spec['primary'])[0];measure=src.copy();keep=spec['keep'];measure[:,:keep]=0;box=bbox(measure,120)
        box[2]=w-24
        mask,_=glyph_mask(text,w,h,box);role='glow' if 'glow' in name else 'scan' if 'scanline' in name else 'primary'
        if not color:
            layers=make_layers(mask,role,old,keep,src,7)
            if role=='glow' and name.startswith('grptext_box_title_'):
                # Extend the native dark backing by the added Hebrew width.
                # Its old right edge must not bisect the translated word halo.
                growth=max(0,bbox(mask)[2]-bbox(src)[2]);tone=old[0].copy()
                for y in range(h):
                    dark=np.flatnonzero(old[0][y]<128)
                    if len(dark):tone[y,dark[0]:min(w,int(dark[-1])+1+growth)]=0
                layers[0]=np.maximum(tone,mask)
            return layers,box
        out=old.copy();out[:,keep:,:]=0;out[:,keep:,:3]=[185,231,248]
        out[:,keep:,3]=np.clip(mask+blur(mask,8)*1.4,0,255).astype(np.uint8)[:,keep:]
        core=mask.astype(float)/255
        out[:,keep:,:3]=np.rint(out[:,keep:,:3]*(1-core[:,keep:,None])+255*core[:,keep:,None]).astype(np.uint8)
        for dx in range(min(40,w-keep)):
            weight=(dx+1)/41;out[:,keep+dx,3]=np.rint(old[:,keep-1,3]*(1-weight)+out[:,keep+dx,3]*weight).astype(np.uint8)
        return out,box
    if kind=='effect':
        alpha=old[:,:,3] if color else old[-1]
        if spec.get('primary'):
            p=channels(spec['primary'])[-1];pb=bbox(p,max(10,int(p.max()*.7)));qb=bbox(alpha,max(10,int(alpha.max()*.7)))
            cx=(qb[0]+qb[2])/2;cy=(qb[1]+qb[3])/2;pw=pb[2]-pb[0];ph=pb[3]-pb[1];box=[round(cx-pw/2),round(cy-ph/2),round(cx+pw/2),round(cy+ph/2)]
        else:box=bbox(alpha,max(20,int(alpha.max()*.75)))
        core=text_mask(text,w,h,box)
        if '_line_' in name or name=='grptext_hud_ryl_end_01^s':core=edge(core)
        if spec.get('soft') or '_blur_' in name:core=np.clip(blur(core,3)*1.5,0,255).astype(np.uint8)
        elif len(old)==2 or color:core=np.clip(core.astype(float)+blur(core,2)*.55,0,255).astype(np.uint8)
        if not color:return ([np.full_like(core,255),core] if len(old)==2 else [core]),box
        out=np.zeros_like(old);out[:,:,:3]=255;out[:,:,3]=core;return out,box
    if kind=='side_lines':
        alpha=old[-1];box=bbox(alpha,200);l,t,r,b=box;new=text_mask(text,w,h,box);out=[c.copy() for c in old]
        left=max(0,l-16);right=min(w,r+16);out[-1][:,left:right]=np.clip(new.astype(float)+blur(new,2)*.6,0,255).astype(np.uint8)[:,left:right]
        if len(out)==2:out[0][:,left:right]=255
        return out,box
    if kind=='diagonal':
        box=bbox(old[-1],120);core=text_mask(text,w,h,box);ink=Image.fromarray(core).crop(bbox(core)).rotate(48,expand=True,resample=Image.Resampling.BICUBIC);ink.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS);core[:]=0;core[box[1]:box[1]+ink.height,box[0]:box[0]+ink.width]=np.asarray(ink)
        return [core],box
    if kind=='mable':
        rgb=old[:,:,:3].astype(int);white=(rgb.min(2)>140)&((rgb.max(2)-rgb.min(2))<40)
        box=bbox((white*old[:,:,3]).astype(np.uint8),100);keep=box[0]-4;box[0]=keep+8
        core=text_mask(text,w,h,box);out=old.copy();out[:,keep:]=0;out[:,keep:,:3]=255;out[:,keep:,3]=core[:,keep:];return out,box
    if kind=='donut':
        box=bbox(old[:,:,3],180);core=text_mask(text,w,h,box);border=np.asarray(Image.fromarray(core).filter(ImageFilter.MaxFilter(9)));out=np.zeros_like(old);out[:,:,:3]=[248,222,206];out[:,:,3]=border;a=core.astype(float)/255;out[:,:,:3]=np.rint(out[:,:,:3]*(1-a[:,:,None])+np.array([42,66,89])*a[:,:,None]).astype(np.uint8);return out,box
    if kind in ('region','wild'):
        if kind=='wild':
            number_left=int(np.flatnonzero(np.any(old[-1][:40]>100,axis=0))[0]);l,t,r,b=0,40,number_left-8,h
        else:l,t,r,b=spec['region']
        measure=np.zeros_like(old[-1]);measure[t:b,l:r]=old[-1][t:b,l:r]
        box=spec.get('fixed_box') or bbox(measure,100);new=text_mask(text,w,h,box);out=[c.copy() for c in old]
        out[-1][t:b,l:r]=new[t:b,l:r]
        if len(out)==2:out[0][t:b,l:r]=255
        return out,box
    if kind=='type':
        box=[44,6,144,30];out=old.copy();out[4:32,40:146]=old[4:32,38:39]
        mask=text_mask(text,w,h,box);a=mask.astype(float)/255;out[:,:,:3]=np.rint(out[:,:,:3]*(1-a[:,:,None])+255*a[:,:,None]).astype(np.uint8)
        return out,box
    if kind=='pill':
        black=(255-old[:,:,:3].min(axis=2)).astype(np.uint8);black[old[:,:,3]<200]=0;box=bbox(black,100)
        out=old.copy();l,t,r,b=box;out[t:b,l:r,:3]=255;mask=text_mask(text,w,h,box)
        out[:,:,:3]=np.minimum(out[:,:,:3],255-mask[:,:,None]);return out,box
    if kind=='pokedex':
        alpha=old[:,:,3] if color else old[-1];measure=alpha.copy();keep=spec['keep'];measure[:,:keep]=0;box=bbox(measure,170)
        core=edge(text_mask(text,w,h,box));a=np.clip(core.astype(float)+blur(core,4)*1.1,0,255).astype(np.uint8)
        if not color:
            out=[c.copy() for c in old];out[0][:,keep:]=255;out[-1][:,keep:]=a[:,keep:];return out,box
        out=old.copy();out[:,keep:,:]=0
        # Keep the source's horizontal rainbow colors while replacing its glyph alpha.
        for x in range(keep,w):
            pixels=old[:,x][old[:,x,3]>40,:3];out[:,x,:3]=np.median(pixels,axis=0).astype(np.uint8) if len(pixels) else [80,190,230]
        out[:,keep:,3]=a[:,keep:];bright=core.astype(float)/255
        out[:,keep:,:3]=np.rint(out[:,keep:,:3]*(1-bright[:,keep:,None])+255*bright[:,keep:,None]).astype(np.uint8)
        return out,box
    if kind in ('dimzone','diminfo'):
        box=[90,24,w-90,h-24] if kind=='dimzone' else [25,30,w-25,h-28]
        core=text_mask(text,w,h,box);alpha=np.clip(core.astype(float)+blur(core,2)*.5,0,255).astype(np.uint8)
        if kind=='diminfo':return [np.full_like(core,180),alpha],box
        # Retain the native faint decorative symbol outside the original word box.
        background=old[-1].copy();measure=old[-1]>100;l,t,r,b=bbox(measure.astype(np.uint8));background[max(0,t-7):min(h,b+7),max(0,l-7):min(w,r+7)]=0
        return [np.full_like(core,255),np.maximum(background,alpha)],box
    if kind=='finish':
        if '_text_' in name:
            idx=int(name.split('_text_')[1][:2]);letters=list('םייתסה');text=letters[idx] if idx<len(letters) else '';box=[round(w*.08),round(h*.04),round(w*.92),round(h*.93)]
        else:box=[round(w*.18),round(h*.35),round(w*.82),round(h*.65)] if ('blur' in name or 'effect' in name) else [round(w*.18),round(h*.14),round(w*.82),round(h*.86)]
        core=text_mask(text,w,h,box) if text else np.zeros((h,w),np.uint8)
        if 'blur' in name or 'effect' in name:core=np.clip(blur(core,12)*1.5,0,255).astype(np.uint8)
        if 'blur_line' in name or 'effect' in name:core=(core*np.where(np.arange(h)%6<2,.3,1)[:,None]).astype(np.uint8)
        if not color:return ([np.full_like(core,255),core] if len(old)==2 else [core]),box
        out=np.zeros_like(old);out[:,:,:3]=[47,79,87] if '_text_' in name else [255,255,255];out[:,:,3]=core;return out,box
    if kind=='marquee':
        core=np.zeros((h,w),np.uint8);box=[12,round(h*.2),w-12,round(h*.8)]
        for l,r in [(0,w//2),(w//2,w)]:core=np.maximum(core,text_mask(text,w,h,[l+12,box[1],r-12,box[3]]))
        if not color:
            core=edge(core);return [np.full_like(core,255),np.clip(core.astype(float)+blur(core,3),0,255).astype(np.uint8)],box
        out=np.zeros_like(old)
        out[:,:,:3]=80;out[:,:,3]=core;boundary=edge(core);out[:,:,:3]=np.maximum(out[:,:,:3],boundary[:,:,None]);return out,box
    box=bbox(old[-1],max(2,int(old[-1].max()*.65)));core=text_mask(text,w,h,box)
    return ([np.full_like(core,255),core] if len(old)==2 else [core]),box
