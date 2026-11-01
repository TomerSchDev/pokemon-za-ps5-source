# P2: NSO metadata extractor

The extractor reads NSO files without changing them. All extracted game data
belongs under the separately held `za-atlas-data/parts/P2` directory, outside git.
It needs Python 3 and a local `llvm-cxxfilt` or `c++filt`; no Python packages or
network access are required.

From the repository root, while holding the P2 claim:

```powershell
py -3 -I tools\za-atlas\P2\extract.py --agent YOUR_CLAIM_ID
py -3 -I tools\za-atlas\P2\test_extract.py
py -3 -I tools\za-atlas\P2\test_extract.py --validate ..\za-atlas-data\parts\P2
```

`--exefs` and `--output` can override the input and output directories. The
output must retain the `<data-root>/parts/P2` structure for the ownership guard.
`--check-string TEXT` enables an exact acceptance check without embedding game
strings in tool source. The validation command expects that check to have run.

The process verifies BelowNormal priority on Windows (or requests nice +10 on
Unix), verifies decompressed NSO segment SHA-256 digests when flagged, parses
MOD0 and dynamic metadata, expands RELR bitmaps and RELA relocations, and
resolves pointers across the two modules. Output publication requires the
original claim agent and generation. Ownership is checked while streaming,
before atomic file replacement, and before publishing `DONE.json`; a heartbeat
is refreshed at least once per minute when those checks run.

`symbols.jsonl` contains defined dynamic symbols. Undefined imports are counted
in the manifest and never assigned invented addresses. Segment `end` values
are exclusive. String extraction is heuristic: printable NUL-terminated UTF-8
and UTF-16LE strings, minimum four characters; wide strings must have a coherent
Unicode script and not overlap identified UTF-8 strings. Mixed scripts can be
missed and arbitrary binary data can still appear textual.

RTTI names come from relocated Itanium class typeinfo objects with proven ABI
vptrs. One class/typeinfo can have several vtable-group rows or a null vtable if
no group was proven. `bases` is a list of class names. A vtable address is the
header containing offset-to-top; slot zero is at vtable + 16. Secondary groups
have their own vtable address and slot numbering. Slot extraction stops at the
first unresolved, null, or non-code pointer. Relative 32-bit tables, custom RTTI
and custom vtables are not inferred. Remaining limits and counts are recorded
in the generated manifest.

The four synthetic tests cover overlapping and malformed LZ4, NSO hash
corruption and RELR bitmaps, Unicode string heuristics, and claim replacement.
The output validator streams every JSONL record, checking exact schemas,
canonical addresses, counts, sizes, hashes, segment bounds, code-pointer slots,
the explicit string acceptance check, and demangled SDK function presence.
