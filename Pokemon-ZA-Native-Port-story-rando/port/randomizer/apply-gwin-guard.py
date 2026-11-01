"""Bound XFB copies to the imported allocation, including an import at offset 0."""
from pathlib import Path
import difflib,hashlib,json,sys
root=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1])
path=source/'runtime/nvn/vulkan/exec.c'
old='        if (gmem_lo && !GM_IN(xfb_addr[b], xfb_size[b])) {'
new='''        // A zero-offset import can also be smaller than the game's XFB arena.
        // Never enqueue a copy beyond the actual imported allocation.
        if (!GM_IN(xfb_addr[b], xfb_size[b])) {'''
before=path.read_text()
if new not in before:
    assert before.count(old)==1,'Unexpected runtime source'
    after=before.replace(old,new)
    (root/'port/randomizer/gwin-copy-bounds.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/runtime/nvn/vulkan/exec.c',tofile='b/runtime/nvn/vulkan/exec.c')))
    path.write_text(after)
else:after=before
receipt={'source':str(path),'sha256':hashlib.sha256(after.encode()).hexdigest(),'guard_present':new in after}
(root/'evidence/randomizer-r9-gwin-guard.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
