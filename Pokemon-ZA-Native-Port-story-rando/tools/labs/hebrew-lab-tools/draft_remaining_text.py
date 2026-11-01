"""Prepare local-only reading drafts; never install or count these as translated.

The machine output deliberately has no `he` field and cannot be consumed by the
translation packer. Full GFMSG sources remain bound to every record for editing.
Proper-name tables are excluded because Marian cannot reliably transliterate them.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from translation_memory import iter_tm
from translation_validate import parse_tokens

LAB = Path(__file__).resolve().parents[1]


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def reading_text(source):
    """Reading aid only. Variable descriptions never become GFMSG controls."""
    descriptions = {0x0100: '[player name]', 0x0101: '[Pokemon species]',
                    0x0102: '[Pokemon nickname]', 0x0107: '[move name]',
                    0x0109: '[item name]', 0x010A: '[item name]',
                    0x010D: '[stat name]', 0x018B: '[companion name]'}
    parts, start = [], 0
    for token in parse_tokens(source):
        parts.append(source[start:token['start']])
        code = token['code']
        parts.append(descriptions.get(code, '[number]' if 0x0200 <= code <= 0x02FF else
                                      ' [button] ' if code == 0xBD0A else
                                      ' ' if code in (0xBE00, 0xBE01) else ''))
        start = token['end']
    parts.append(source[start:])
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage-build', default='full-hebrew-20261030-r13')
    args = parser.parse_args()
    if Path(args.coverage_build).name != args.coverage_build:
        raise ValueError('Expected build name')
    os.chdir(LAB)
    os.environ.update(HF_HOME=str(LAB / 'models/hf-cache'),
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1',
                      DO_NOT_TRACK='1')
    import ctranslate2
    from transformers import AutoTokenizer
    model = json.loads((LAB / 'models/model-manifest.json').read_text(encoding='utf-8'))
    model_version = model['revision']
    tokenizer = AutoTokenizer.from_pretrained('models/opus-mt-en-he', local_files_only=True, trust_remote_code=False)
    translator = ctranslate2.Translator('models/opus-mt-en-he-ct2-int8', device='cpu',
                                      compute_type='int8', intra_threads=min(8, os.cpu_count() or 4))
    coverage = json.loads((LAB / 'build' / args.coverage_build / 'coverage.json').read_text(encoding='utf-8'))
    missing = set(coverage['missing_keys'])
    rows = [r for r in iter_tm(LAB / 'memory/english-source.jsonl') if r['key'] in missing]
    queue = [r for r in rows if r.get('context', {}).get('category') != 'names']
    texts = list(dict.fromkeys(reading_text(r['source']) for r in queue))
    output = LAB / 'translations/local-reading-drafts-20261030'
    output.mkdir(exist_ok=True)
    cache = sqlite3.connect(output / 'cache.sqlite')
    cache.execute('CREATE TABLE IF NOT EXISTS drafts (version TEXT, hash TEXT, source TEXT, target TEXT, PRIMARY KEY(version,hash))')
    existing = {row[0] for row in cache.execute('SELECT hash FROM drafts WHERE version=?', (model_version,))}
    todo = [text for text in texts if digest(text) not in existing]
    started = time.monotonic()
    report_path = output / 'progress.json'
    def report(done):
        value = dict(status='machine_reading_draft_only', model=model['model'], revision=model_version,
                     inference='local CPU; no text upload', rows_in_scope=len(queue),
                     proper_name_rows_excluded=len(rows)-len(queue), unique_reading_texts=len(texts),
                     new_texts_this_run=len(todo), completed_this_run=done,
                     elapsed_seconds=round(time.monotonic()-started, 2),
                     linguistic_approval=False, packable=False, increases_translation_coverage=False)
        report_path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(value), flush=True)
    report(0)
    for offset in range(0, len(todo), 24):
        batch = todo[offset:offset+24]
        tokens = [tokenizer.convert_ids_to_tokens(tokenizer.encode(text, truncation=True, max_length=400)) for text in batch]
        results = translator.translate_batch(tokens, beam_size=2, max_decoding_length=400, repetition_penalty=1.1)
        with cache:
            for source, result in zip(batch, results):
                target = tokenizer.decode(tokenizer.convert_tokens_to_ids(result.hypotheses[0]), skip_special_tokens=True)
                cache.execute('INSERT INTO drafts VALUES (?,?,?,?)', (model_version, digest(source), source, target))
        if offset % 240 == 0 or offset+24 >= len(todo):
            report(min(offset+24, len(todo)))
    cached = {h: target for h, target in cache.execute('SELECT hash,target FROM drafts WHERE version=?', (model_version,))}
    flags = Counter()
    with (output / 'reading-drafts.jsonl').open('w', encoding='utf-8', newline='\n') as out:
        for row in queue:
            prompt = reading_text(row['source'])
            target = cached[digest(prompt)]
            issues = []
            if not re.search('[א-ת]', target): issues.append('no_hebrew')
            if re.search('[A-Za-z]', target): issues.append('latin_residue')
            if row['source'].find('{VAR 1100') >= 0: issues.append('gender_branch_needs_reconstruction')
            if row['source'].find('{VAR 1101') >= 0: issues.append('number_branch_needs_reconstruction')
            if any(token['code'] == 0xFF00 for token in parse_tokens(row['source'])): issues.append('color_semantics_need_review')
            flags.update(issues)
            out.write(json.dumps(dict(key=row['key'], source_sha256=digest(row['source']),
                                      english_reading=prompt, machine_reading_draft=target,
                                      status='unreviewed_reading_aid_not_translation', flags=issues), ensure_ascii=False) + '\n')
    report(len(todo))
    (output / 'flags.json').write_text(json.dumps(dict(flags), indent=2) + '\n', encoding='utf-8')
    cache.close()


if __name__ == '__main__':
    main()
