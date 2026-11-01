"""Extend the independent Smoliv mod with an unused Z-A Pokedex number."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'pilot/tools'))
sys.path.insert(0,str(ROOT.parents[1]/'hebrew-lab/tools'))
import za_schemas as Z
from fbcodec import Schema,same
import gfmsg


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    parser.add_argument('--index',type=int,default=365)
    args=parser.parse_args()
    if args.out.exists():raise SystemExit('Output exists: '+str(args.out))
    source=ROOT/'build/smoliv-species-r1/species-pilot'
    dest=args.out/'smoliv-independent'
    shutil.copytree(source,dest)
    romfs=dest/'romfs'
    schema=Z.personal_schema()
    old=schema.decode((romfs/Z.PERSONAL).read_bytes())
    native=schema.decode(Z.read(Z.PERSONAL))['Table']
    occupied={r.get('Dex',{}).get('Index',0) for r in native if r.get('IsPresentInGame')}
    assert args.index not in occupied and args.index>max(occupied)
    values=json.loads(json.dumps(old))
    row=next(r for r in values['Table'] if r['Info']['SpeciesInternal']==935 and r['Info'].get('Form',0)==0)
    row['Dex']={'Index':args.index,'Group':0}
    data=schema.encode(values)
    assert same(schema.decode(data),values)
    changed=[i for i,(a,b) in enumerate(zip(old['Table'],values['Table'])) if not same(a,b)]
    assert len(changed)==1
    (romfs/Z.PERSONAL).write_bytes(data)
    contents_path='world/exl/pokedex_contents_data/pokedex_contents_data/pokedex_contents_data.bin'
    contents_schema=Schema()
    contents_schema.add_table('Entry',[('id','u32'),('devNo','u32'),('book','u32')])
    contents_schema.add_table('Contents',[('entries',('vec',('table','Entry')))])
    contents_schema.root='Contents'
    contents=contents_schema.decode(Z.read(contents_path))
    original_contents=json.loads(json.dumps(contents['entries']))
    assert len(original_contents)==364 and not any(r.get('devNo',0)==935 for r in original_contents)
    contents['entries'].append({'id':max(r['id'] for r in original_contents)+1,'devNo':935})
    encoded_contents=contents_schema.encode(contents)
    assert same(contents_schema.decode(encoded_contents),contents)
    assert same(contents['entries'][:-1],original_contents)
    contents_target=romfs/contents_path
    contents_target.parent.mkdir(parents=True,exist_ok=True)
    contents_target.write_bytes(encoded_contents)
    descriptions=json.loads((ROOT/'evidence/smoliv-source-dex-text.json').read_text(encoding='utf-8'))
    inserted=[]
    for suffix,entry in descriptions.items():
        path='ik_message/dat/English/common/zukan_comment_'+suffix
        original=Z.read(path+'.dat')
        message=gfmsg.MsgFile(original)
        assert message.encode()==original
        table=gfmsg.read_tbl(Z.read(path+'.tbl'))
        label=entry['label'];key=gfmsg.fnv1a64(label)
        assert not any(h==key for h,_ in table)
        assert len(table)==len(message.lines)+1 and table[-1][1]=='msg_zukan_comment_'+suffix+'_max'
        inserted_index=len(message.lines)
        message.lines.append(gfmsg.encode_text(entry['text']))
        message.params.append(0)
        table.insert(inserted_index,(key,label))
        tbl=b'AHTB'+struct.pack('<I',len(table))
        for h,name in table:
            encoded=name.encode('utf-8')+b'\x00'
            tbl+=struct.pack('<QH',h,len(encoded))+encoded
        assert gfmsg.read_tbl(tbl)==table
        dat=message.encode()
        assert gfmsg.decode_units(gfmsg.MsgFile(dat).lines[-1])==entry['text']
        target=romfs/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.with_suffix('.dat').write_bytes(dat)
        target.with_suffix('.tbl').write_bytes(tbl)
        inserted.append(dict(label=label,text=entry['text'],index=inserted_index,source=entry))
    report=dict(national=928,internal=935,pokedex_index=args.index,native_pokedex_indices_preserved=len(occupied),
                personal_row_changed=changed,description_added=True,description_entries=inserted,
                contents_added=contents['entries'][-1],native_contents_preserved=len(original_contents),runtime_tested=False,
                files={p.relative_to(romfs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in romfs.rglob('*') if p.is_file()})
    (args.out/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))


if __name__=='__main__':main()
