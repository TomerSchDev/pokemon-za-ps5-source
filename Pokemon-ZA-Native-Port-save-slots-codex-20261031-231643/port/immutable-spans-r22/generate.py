"""Create a reviewable r22 patch and exact target snippets; never edit --source."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REL = Path('runtime/nvn/vulkan/exec.c')

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected exactly one source anchor: '+old[:120])
    return text.replace(old,new,1)

def extract_function(text,name):
    match=re.search(r'^static [^\n]+\b'+re.escape(name)+r'\([^\n]*\) \{',text,re.M)
    if not match:raise ValueError('Missing function '+name)
    begin=match.start(); brace=text.index('{',begin); depth=1; end=brace+1
    while depth:
        depth += (text[end]=='{')-(text[end]=='}'); end+=1
    return text[begin:end]

def extract_sites(text,prefix):
    zero_decl=re.search(r'    static const uint8_t zeros\[0x10000\];',text)
    ubo=re.search(r'    if \(!r\.addr\) return ubo_span\([^\n]+',text)
    default=re.search(r'            static const float zero\[4\] = \{0, 0, 0, 1\};\n            sp = [^\n]+',text)
    vertex=re.search(r'            if \(!v\.addr\) \{ static const uint8_t zero\[256\]; sp = [^\n]+',text)
    if not all((zero_decl,ubo,default,vertex)):raise ValueError('Missing immutable target fragment')
    return (f'static VkDescriptorBufferInfo {prefix}_ubo(uint64_t size) {{\n    Range r={{0}};\n'+
            zero_decl[0]+'\n'+ubo[0]+'\n    abort();\n}\n'+
            f'static VkSpan {prefix}_default(void) {{ VkSpan sp;\n'+default[0]+'\n    return sp;\n}\n'+
            f'static VkSpan {prefix}_vertex_zero(void) {{ Range v={{0}}; VkSpan sp={{0}};\n'+vertex[0]+'\n    return sp;\n}\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    source=args.source.resolve(); out=args.out.resolve()
    if out==source or source in out.parents:raise ValueError('Output must be outside runtime source')
    if out.exists():raise ValueError('Output already exists; use a fresh evidence directory')
    original=(source/REL).read_bytes(); text=original.decode('utf-8')
    if 'za_immutable_span' in text:raise ValueError('r22 already applied')
    modified=once(text,'// Per-draw constants that usually repeat the previous draw',
                  '#include "za_immutable_spans_r22.inc"\n\n// Per-draw constants that usually repeat the previous draw')
    modified=once(modified,'    za_submission_report();',
                  '    za_submission_report();\n    za_immutable_spans_report();')
    modified=once(modified,'void vk_exec_reset(void) {',
                  'void vk_exec_reset(void) {\n    za_immutable_spans_reset();')
    modified=once(modified,'if (!r.addr) return ubo_span(vk_transient_copy(zeros, size, 256), size);',
                  'if (!r.addr) return ubo_span(za_immutable_span_copy(ZA_IMM_UBO_ZERO, zeros, size, 256), size);')
    modified=once(modified,'sp = vk_transient_copy(zero, 16, 16);',
                  'sp = za_immutable_span_copy(ZA_IMM_VERTEX_DEFAULT, zero, 16, 16);')
    modified=once(modified,'if (!v.addr) { static const uint8_t zero[256]; sp = vk_transient_copy(zero, 256, 16); }',
                  'if (!v.addr) { static const uint8_t zero[256]; sp = za_immutable_span_copy(ZA_IMM_VERTEX_ZERO, zero, 256, 16); }')
    helper=(HERE/'immutable-spans.inc').read_text(encoding='utf-8')
    (out/REL.parent).mkdir(parents=True)
    (out/REL).write_text(modified,encoding='utf-8',newline='\n')
    inc_rel=REL.parent/'za_immutable_spans_r22.inc'
    (out/inc_rel).write_text(helper,encoding='utf-8',newline='\n')
    header=(HERE/'immutable-spans.h').read_text(encoding='utf-8')
    header_rel=REL.parent/'za_immutable_spans_r22.h'
    (out/header_rel).write_text(header,encoding='utf-8',newline='\n')
    patch=''.join(difflib.unified_diff(text.splitlines(True),modified.splitlines(True),
                                     fromfile='a/'+REL.as_posix(),tofile='b/'+REL.as_posix()))
    patch+=''.join(difflib.unified_diff([],helper.splitlines(True),fromfile='/dev/null',tofile='b/'+inc_rel.as_posix()))
    patch+=''.join(difflib.unified_diff([],header.splitlines(True),fromfile='/dev/null',tofile='b/'+header_rel.as_posix()))
    (out/'candidate.patch').write_text(patch,encoding='utf-8',newline='\n')
    snippets=extract_function(text,'ubo_span')+'\n'+extract_sites(text,'original')+extract_sites(modified,'candidate')
    (out/'extracted-sites.inc').write_text(snippets,encoding='utf-8',newline='\n')
    # Also test the original copy helper verbatim with the host transient stub.
    start=text.index('VkSpan vk_transient_copy('); end=text.index('\n}',start)+2
    (out/'extracted-copy.inc').write_text(text[start:end]+'\n',encoding='utf-8',newline='\n')
    manifest={'source':str(source/REL),'source_sha256':hashlib.sha256(original).hexdigest(),
              'source_unchanged':(source/REL).read_bytes()==original,'baseline_default':True,
              'scope':['unbound UBO zeros','ZERO_BINDING default w=1','unbound vertex zeros'],
              'generated':{str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()
                           for f in out.rglob('*') if f.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
