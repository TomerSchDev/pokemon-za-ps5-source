"""Local-only draft terminology generation. No game strings are sent to a translation service."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import time

LAB=Path(__file__).resolve().parents[1]
os.environ['HF_HOME']=str(LAB/'models/hf-cache')
os.environ['TORCH_HOME']=str(LAB/'models/torch-cache')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['DO_NOT_TRACK']='1'
MODEL='Helsinki-NLP/opus-mt-en-he'
SOURCE=LAB/'models/opus-mt-en-he'
CT2=LAB/'models/opus-mt-en-he-ct2-int8'
PROPER={'pokemon','character','place','pokemon_nickname','berry'}

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def prepare():
    # Native SentencePiece/CTranslate2 Windows wheels need ASCII relative paths;
    # keep all files in the existing Unicode-named lab without relocating them.
    os.chdir(LAB)
    from huggingface_hub import HfApi,snapshot_download
    from ctranslate2.converters import TransformersConverter
    import importlib.metadata
    info=HfApi(token=False).model_info(MODEL,token=False)
    SOURCE.parent.mkdir(parents=True,exist_ok=True)
    print(json.dumps({'stage':'downloading public model only','revision':info.sha}),flush=True)
    snapshot_download(MODEL,revision=info.sha,token=False,local_dir=SOURCE,
        allow_patterns=['config.json','generation_config.json','tokenizer_config.json','special_tokens_map.json',
                        'vocab.json','source.spm','target.spm','pytorch_model.bin','README.md'])
    if not (CT2/'model.bin').exists():
        print(json.dumps({'stage':'converting local model to CPU int8'}),flush=True)
        TransformersConverter(str(SOURCE.relative_to(LAB)),trust_remote_code=False).convert(str(CT2.relative_to(LAB)),quantization='int8')
    files=[]
    for folder in (SOURCE,CT2):
        for p in sorted(folder.iterdir()):
            if p.is_file():files.append({'path':str(p.relative_to(LAB)), 'bytes':p.stat().st_size,'sha256':sha(p)})
    manifest=dict(model=MODEL,revision=info.sha,license='Apache-2.0',inference='local CPU int8; no text upload',
        source_url='https://huggingface.co/'+MODEL,conversion_docs='https://opennmt.net/CTranslate2/guides/transformers.html#marianmt',
        versions={p:importlib.metadata.version(p) for p in ('torch','transformers','ctranslate2','sentencepiece')},files=files)
    write_json(LAB/'models/model-manifest.json',manifest)
    print(json.dumps({'stage':'local model prepared','files':len(files)}),flush=True)

def glossary(limit=None,contextual=False,missing_only=False):
    os.chdir(LAB)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import ctranslate2
    from transformers import AutoTokenizer
    manifest=json.loads((LAB/'models/model-manifest.json').read_text(encoding='utf-8'))
    tokenizer=AutoTokenizer.from_pretrained(str(SOURCE.relative_to(LAB)),local_files_only=True,trust_remote_code=False)
    translator=ctranslate2.Translator(str(CT2.relative_to(LAB)),device='cpu',compute_type='int8',intra_threads=min(8,os.cpu_count() or 4))
    rows=[json.loads(x) for x in (LAB/'terminology/inventory.jsonl').read_text(encoding='utf-8').splitlines() if x]
    with (LAB/'terminology/seed.tsv').open(encoding='utf-8',newline='') as f:
        locked={r['english']:r['hebrew'] for r in csv.DictReader(f,delimiter='\t')}
    queue=[r for r in rows if r['category'] not in PROPER and r['english'] not in locked]
    if missing_only:
        missing=json.loads((LAB/'terminology/review/missing.json').read_text(encoding='utf-8'))
        keys={(r['english'],r['category']) for r in missing}
        queue=[r for r in queue if (r['english'],r['category']) in keys]
    if limit is not None:queue=queue[:limit]
    output=LAB/('terminology/proposals/local-marian-contextual.jsonl' if contextual else 'terminology/proposals/local-marian.jsonl');output.parent.mkdir(parents=True,exist_ok=True)
    done={}
    if output.exists():
        for line in output.read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if r.get('revision')!=manifest['revision']:raise ValueError('Existing proposals use a different model revision')
            done[(r['english'],r['category'])]=r
    todo=[r for r in queue if (r['english'],r['category']) not in done]
    def cache_key(r):return (r['english'],r['category']=='item_plural' if contextual else False)
    cache={cache_key(r):r['hebrew'] for r in done.values()};start=time.monotonic()
    with output.open('a',encoding='utf-8',newline='\n') as f:
        for offset in range(0,len(todo),32):
            batch=todo[offset:offset+32]
            unique=list(dict.fromkeys(cache_key(r) for r in batch if cache_key(r) not in cache))
            prompts=[(('These are ' if plural else 'This is ')+text+'.') if contextual else text for text,plural in unique]
            tokens=[tokenizer.convert_ids_to_tokens(tokenizer.encode(text)) for text in prompts]
            if tokens:
                results=translator.translate_batch(tokens,beam_size=2,max_decoding_length=64,repetition_penalty=1.1)
                for key,result in zip(unique,results):
                    value=tokenizer.decode(tokenizer.convert_tokens_to_ids(result.hypotheses[0]),skip_special_tokens=True)
                    value=re.sub(r'\s+',' ',value).strip()
                    if contextual:value=re.sub(r'^(?:זהו|זוהי|זאת|זה|זו|אלה|אלו|הנה)\s+','',value).rstrip('. ')
                    cache[key]=value
            for r in batch:
                value=cache[cache_key(r)];flags=[]
                if not re.search('[א-ת]',value):flags.append('no_hebrew')
                if re.search('[A-Za-z]',value):flags.append('latin_residue')
                if re.search('[\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]',value):flags.append('niqqud_or_marks')
                if value.casefold()==r['english'].casefold():flags.append('untranslated')
                if len(value)>max(60,len(r['english'])*3):flags.append('length_outlier')
                result=dict(english=r['english'],hebrew=value,category=r['category'],flags=flags,
                    note='מועמד מתרגום מקומי אוטומטי; דורש ביקורת; '+(', '.join(flags) if flags else 'לא אושר'),
                    status='machine_candidate_needs_review',model=MODEL,revision=manifest['revision'],framing='contextual-phrase-v1' if contextual else 'bare-term')
                f.write(json.dumps(result,ensure_ascii=False)+'\n');done[(r['english'],r['category'])]=result
            f.flush()
            print(json.dumps({'stage':'local terminology draft','done':min(offset+32,len(todo)),'total':len(todo)}),flush=True)
    selected=[done[(r['english'],r['category'])] for r in queue]
    report=dict(model=MODEL,revision=manifest['revision'],inference='local-only',queue_terms=len(queue),
        generated_this_run=len(todo),elapsed_seconds=round(time.monotonic()-start,2),
        needs_review=len(selected),flagged_terms=sum(bool(r['flags']) for r in selected),
        excluded_proper_noun_categories=sorted(PROPER),inventory_sha256=sha(LAB/'terminology/inventory.jsonl'),
        proposals_sha256=sha(output),approved=False)
    write_json(LAB/('reports/local-mt-contextual-glossary.json' if contextual else 'reports/local-mt-glossary.json'),report)
    print(json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('op',choices=('prepare','glossary'));p.add_argument('--limit',type=int)
    p.add_argument('--contextual',action='store_true');p.add_argument('--missing-only',action='store_true')
    a=p.parse_args()
    if a.op=='prepare':prepare()
    else:glossary(a.limit,a.contextual,a.missing_only)
