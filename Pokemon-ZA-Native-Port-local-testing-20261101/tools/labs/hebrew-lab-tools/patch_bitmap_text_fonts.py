"""Audit native bitmap-font message bindings; select an existing Hebrew-capable font.

Only font indices, runtime font-override strings and same-size font-name slots
may change. All layout sizes, messages, materials and textures stay exact.
"""
import argparse,hashlib,json,re,shutil,struct
from pathlib import Path
from za_romfs import Game,fnv1a64
from ui_header_extract import sarc_members

LAB=Path(__file__).resolve().parents[1]
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def blocks(data):
    if data[:4]!=b'FLYT':raise ValueError('Not FLYT')
    pos=struct.unpack_from('<H',data,6)[0]
    while pos<len(data):
        if pos+8>len(data):raise ValueError('Truncated section')
        size=struct.unpack_from('<I',data,pos+4)[0]
        if size<8 or pos+size>len(data):raise ValueError('Invalid section size')
        yield pos,data[pos:pos+4],data[pos:pos+size]
        pos+=size

def bindings(raw):
    for member,b in sarc_members(raw):
        if not member['name'].endswith('.bflyt'):continue
        sections=list(blocks(b));fonts=[];font_offsets=[]
        for pos,tag,c in sections:
            if tag!=b'fnl1':continue
            for i in range(struct.unpack_from('<H',c,8)[0]):
                off=12+struct.unpack_from('<I',c,12+4*i)[0]
                fonts.append(c[off:c.index(0,off)].decode())
                font_offsets.append(member['offset']+pos+off)
        for section_index,(pos,tag,c) in enumerate(sections):
            if tag!=b'txt1':continue
            if len(c)<108:raise ValueError('Short text pane')
            fi=struct.unpack_from('<H',c,90)[0]
            if fi>=len(fonts):raise ValueError('Unresolved font index')
            override=None
            if section_index+1<len(sections) and sections[section_index+1][1]==b'usd1':
                up,ut,uc=sections[section_index+1]
                for i in range(struct.unpack_from('<H',uc,8)[0]):
                    entry=12+12*i;np=entry+struct.unpack_from('<I',uc,entry)[0];dp=entry+struct.unpack_from('<I',uc,entry+4)[0]
                    name=uc[np:uc.index(0,np)].decode()
                    if name=='font':
                        if uc[entry+10]!=0:raise ValueError('Unexpected font override type')
                        value=uc[dp:uc.index(0,dp)].decode();count=struct.unpack_from('<H',uc,entry+8)[0]
                        if count!=len(value):raise ValueError('Font override count differs')
                        override=dict(value=value,offset=member['offset']+up+dp,count_offset=member['offset']+up+entry+8)
            if not fonts[fi].startswith('bmp_') and not (override and override['value'].startswith('bmp_')):continue
            match=re.search(rb'([A-Za-z0-9_]+)\.mstxt:([A-Za-z0-9_]+)',c)
            if match:
                yield dict(member=member['name'],pane=c[12:36].split(b'\0')[0].decode(),font=fonts[fi],fonts=fonts,font_name_offsets=font_offsets,font_index=fi,
                           absolute_offset=member['offset']+pos+90,font_override=override,key=match[1].decode()+':'+match[2].decode())

def main():
    p=argparse.ArgumentParser();p.add_argument('--game',required=True);p.add_argument('--base',required=True);p.add_argument('--out');a=p.parse_args()
    base=LAB/'build'/a.base
    translations={r['key'].rsplit('/',1)[-1].replace('.dat:',':'):r['he'] for r in map(json.loads,(LAB/'translations'/(a.base+'.jsonl')).read_text(encoding='utf-8').splitlines())}
    inventories=[LAB/'headers/reports/full-ui-text-inventory.json',LAB/'headers/extract-common-extra/inventory.json',LAB/'headers/extract-common-extra/inventory-extra-english.json',LAB/'headers/extract-nested/inventory.json']
    known={r['path'] for f in inventories for r in read(f)};byhash={fnv1a64(n):n for n in known};directories={str(Path(n).parent).replace('\\','/') for n in known}
    game=Game(Path(a.game)/'romfs.bin');packs=[(n,rr) for n,rr in game.packs if n.startswith('arc/uidata') and not re.search(r'_(kor|fre|ger|ita|spa|ltm|jpn|sch|tch)\.',n)]
    for name,rr in packs:
        flat=name[len('arc/uidata'):-len('.trpak')]
        for i in range(1,len(flat)):
            candidate='ui/data/'+flat[:i]+'/'+flat[i:]
            if game.has(candidate):directories.add(str(Path(candidate).parent).replace('\\','/'))
    seen=set();rows=[];originals={};scanned=0
    for pack,rr in packs:
        for r in rr:
            if r['hash'] in seen:continue
            seen.add(r['hash']);raw=game.unpack(r)
            if not raw.startswith(b'SARC'):continue
            scanned+=1;found=list(bindings(raw))
            if not found:continue
            path=byhash.get(r['hash'])
            if not path:
                stems={Path(m['name']).stem for m,b in sarc_members(raw) if m['name'].endswith('.bflyt')}
                candidates={d+'/'+s+suffix+'.arc' for d in directories for s in stems for suffix in ('','_eng')}
                matches=[x for x in candidates if fnv1a64(x)==r['hash']]
                if len(matches)!=1:raise ValueError('Ambiguous archive path')
                path=matches[0]
            for row in found:
                he=translations.get(row['key'],'');row.update(archive=path,hebrew=he,needs_hebrew_font=any('\u0590'<=c<='\u05ff' for c in he),source_archive_sha256=digest(raw))
                rows.append(row)
                if row['needs_hebrew_font']:originals[path]=raw
    report=dict(scanned_sarc_archives=scanned,bitmap_message_bindings=rows,required_fixes=sum(r['needs_hebrew_font'] for r in rows))
    write(LAB/'coordination/bitmap-font-audit.json',report)
    for r in rows:
        if r['needs_hebrew_font']:print(json.dumps(r,ensure_ascii=False),flush=True)
    print(json.dumps(dict(scanned=scanned,bindings=len(rows),fixes=report['required_fixes'])),flush=True)
    if not a.out:return
    fixes=[r for r in rows if r['needs_hebrew_font']]
    catalog=read(LAB/'translations/bitmap-font-bindings-reviewed-20261030-r1.json')
    fields=('archive','member','pane','font','font_index','absolute_offset','key','hebrew','source_archive_sha256')
    signature=lambda r:tuple(r[k] for k in fields)
    if not fixes or sorted(map(signature,fixes))!=sorted(map(signature,catalog['bindings'])):raise ValueError('Review changed bitmap-bound Hebrew labels first')
    out=LAB/'build'/a.out
    if Path(a.out).name!=a.out or out.exists():raise FileExistsError(out)
    manifest=read(base/'manifest.json')
    for f in manifest['files']:
        if digest((base/f['path']).read_bytes())!=f['sha256']:raise ValueError('Baseline changed')
    shutil.copytree(base,out);checks=[]
    for path,raw in originals.items():
        oldpath=base/'mods/hebrew/romfs'/path;before=oldpath.read_bytes() if oldpath.exists() else raw;patched=bytearray(before);allowed=set();changes=[]
        original_members={m['name']:(m,b) for m,b in sarc_members(raw)}
        current_members={m['name']:(m,b) for m,b in sarc_members(before)}
        if {n:m for n,(m,b) in current_members.items()}!={n:m for n,(m,b) in original_members.items()}:raise ValueError('Archive metadata differs')
        for r in [x for x in fixes if x['archive']==path]:
            if current_members[r['member']][1]!=original_members[r['member']][1]:raise ValueError('Layout already changed')
            nominal=int(re.search(r'bmp_din_(\d+)',r['font'])[1]);bold='bold' in r['font']
            override=r.get('font_override');max_name=len(override['value']) if override else 100
            candidates=[(i,n) for i,n in enumerate(r['fonts']) if re.fullmatch(r'system\d+(?:_bold)?_jpn\.fcpx',n) and len(n.removesuffix('.fcpx'))<=max_name]
            name_replacement=None
            if candidates:
                index,target=min(candidates,key=lambda x:(abs(int(re.search(r'system(\d+)',x[1])[1])-nominal),('bold' in x[1])!=bold))
            else:
                # Keep the native font-list offsets and total length. Numeric panes
                # sharing this slot also use the scalable font, retaining their text.
                size=min((24,26,30,32,42),key=lambda n:abs(n-nominal))
                target=f'system{size}'+('_bold' if bold else '')+'_jpn.fcpx';index=r['font_index']
                oldname=r['font'].encode();newname=target.encode()
                if len(newname)>len(oldname):raise ValueError('Font name does not fit its native slot')
                start=r['font_name_offsets'][index]
                if before[start:start+len(oldname)]!=oldname:raise ValueError('Font-name source mismatch')
                patched[start:start+len(oldname)]=newname+b'\0'*(len(oldname)-len(newname));allowed.update(range(start,start+len(oldname)))
                name_replacement=dict(offset=start,old=r['font'],new=target,slot_bytes=len(oldname))
            offset=r['absolute_offset']
            if struct.unpack_from('<H',before,offset)[0]!=r['font_index']:raise ValueError('Unexpected original font')
            override_replacement=None
            if override:
                old=override['value'].encode();new=target.removesuffix('.fcpx').encode();start=override['offset'];countpos=override['count_offset']
                if len(new)>len(old) or before[start:start+len(old)]!=old:raise ValueError('Font override cannot be replaced in place')
                patched[start:start+len(old)]=new+b'\0'*(len(old)-len(new));struct.pack_into('<H',patched,countpos,len(new))
                allowed.update(range(start,start+len(old)));allowed.update((countpos,countpos+1))
                override_replacement=dict(old=override['value'],new=new.decode(),offset=start,count_offset=countpos)
            struct.pack_into('<H',patched,offset,index);allowed.update((offset,offset+1));changes.append(dict(r,new_font=target,new_font_index=index,font_name_replacement=name_replacement,font_override_replacement=override_replacement))
        if any(x!=y and i not in allowed for i,(x,y) in enumerate(zip(before,patched))) or len(before)!=len(patched):raise ValueError('Unexpected changed bytes')
        dest=out/'mods/hebrew/romfs'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(patched)
        checks.append(dict(file=path,source_sha256=digest(before),sha256=digest(patched),only_font_selection_bytes_changed=True,unchanged_length=True,changes=changes))
    for suffix in ('.jsonl','-terms.tsv'):
        dest=LAB/'translations'/(a.out+suffix)
        if dest.exists():raise FileExistsError(dest)
        shutil.copyfile(LAB/'translations'/(a.base+suffix),dest)
    write(out/'native-font-selection.json',checks);manifest.update(native_font_selection=checks,font_selection_revision_of=a.base)
    for r in manifest['native_heading_archives']:
        matching=next((c for c in checks if c['file']==r['file']),None)
        if matching:
            r.update(native_image_stage_sha256=r['sha256'],sha256=matching['sha256'],subsequent_font_selection_patch=True)
            if 'verification' in r:r['native_image_stage_verification']=r.pop('verification')
    manifest['files']=[dict(path=f.relative_to(out).as_posix(),bytes=f.stat().st_size,sha256=digest(f.read_bytes())) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='manifest.json']
    write(out/'manifest.json',manifest);print(json.dumps(dict(build=a.out,font_archives=len(checks))),flush=True)

if __name__=='__main__':main()
