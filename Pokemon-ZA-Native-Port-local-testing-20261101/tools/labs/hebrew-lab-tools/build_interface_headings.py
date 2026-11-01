"""Compile Hebrew settings headings into same-size native BC4 mask payloads."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from build_header_mod import bbox, digest, glyph_mask
from ui_header_codec import inspect_archive, decode_masks, encode_masks, patch_archive

LAB = Path(__file__).resolve().parents[1]
OUTPUT = LAB / 'headers/build/interface-headings-20261030-r2'
SPECS = [
    ('option_top', 'option_top_top_00', 'grptext_option_top_title_00^s', 'עזרה והגדרות'),
    ('option', 'option_gamesetting_00', 'grptext_option_gamesetting_title_00^s', 'הגדרות'),
    ('bag', 'bag_donut_top_00', 'grptext_bag_donut_title_00^s', 'חפצים'),
]


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve existing header revision')
    pending = []
    for directory, stem, name, hebrew in SPECS:
        for suffix in ('', '_eng'):
            source = LAB / 'headers/extract-settings' / (stem + suffix) / 'archive.arc'
            original = source.read_bytes()
            metadata = inspect_archive(original)
            texture = metadata[name]
            if texture['format'].lower() != '0x1d01':
                raise ValueError('Expected a single-channel BC4 text mask')
            start, size = texture['payload_offset_in_archive'], texture['payload_size']
            before = original[start:start + size]
            old = np.frombuffer(decode_masks(texture, before)[0], np.uint8).reshape(texture['height'], texture['width'])
            mask, typography = glyph_mask(hebrew, texture['width'], texture['height'], bbox(old))
            after = encode_masks(texture, [mask.tobytes()], before)
            decoded = np.frombuffer(decode_masks(texture, after)[0], np.uint8).reshape(mask.shape)
            error = int(np.abs(decoded.astype(np.int16) - mask.astype(np.int16)).max())
            if error > 37 or len(after) != len(before):
                raise ValueError('Native heading quantization/size changed')
            patched, verification = patch_archive(original, {name: after}, expected_sha256=digest(original))
            relative = Path('ui/data') / directory / (stem + suffix + '.arc')
            pending.append((relative, patched, decoded, dict(source=str(source.relative_to(LAB)),
                source_sha256=digest(original), file=relative.as_posix(), sha256=digest(patched),
                bytes=len(patched), texture=name, logical=hebrew, typography=typography,
                quantization_error_max=error, verification=verification)))
    OUTPUT.mkdir(parents=True)
    (OUTPUT/'previews').mkdir()
    for relative, patched, decoded, report in pending:
        target = OUTPUT/'mods/hebrew/romfs'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(patched)
        Image.fromarray(decoded).save(OUTPUT/'previews'/(relative.stem+'.png'))
    (OUTPUT/'verification.json').write_text(json.dumps([r for _, _, _, r in pending], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(archives=len(pending), native_sizes_preserved=True, visual_qa='pending')))


if __name__ == '__main__':
    main()
