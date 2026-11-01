"""ui-v2 option C: the ONE runtime change - keep the start screen on for Z-A when LARECOMP_PS5_LAUNCHER is set.

runtime/main.c boots Z-A straight into the game (skip_launcher) because the desktop start screen knows only Link's
Awakening's files. The PS5 title now supplies its own launcher_run (port/ui-v2/src/launcher_ps5.cpp), so with
LARECOMP_PS5_LAUNCHER=1 in the environment the launcher hook runs before boot(): the window, Vulkan device and
swapchain are created once and the launcher's last frame stays on screen until the game's first frame.
Three edits of main.c, applied by exact text (the file must be the pinned one: SHA-256 checked before and after) and
reversible (--revert). Usage: apply-runtime-launcher.py <runtime dir> [--revert] [--check]
"""
import hashlib
import sys
from pathlib import Path

PRISTINE_SHA256 = {
    '9f4c88c287b980f7e23d3286c63aeb86989491c4732a37318e82bfadb030db97',  # pinned r28b merge tree
    'aa318348b03242c0213ff8eef51f621a0a466565198fe1eb56f38a67a477ddd2',  # local ps5 runtime repo
}

# runtime/main.c of the r28 trees (r28b-dlc-dex-r29ui-20261031/source/runtime/main.c) and of pokeza-recomp-ps5 (ps5): the two
# differ only by a ZA_PS5 log line; both are accepted (the edits are the same text).
EDITS = [
    ("    bool skip_launcher = getenv(\"LARECOMP_NO_LAUNCHER\") || getenv(\"LARECOMP_INPUT\");  // tests boot straight in\n",
     "    // ui-v2 (port/ui-v2): LARECOMP_PS5_LAUNCHER=1 keeps the start screen on whatever else says to skip it - the\n"
     "    // title's own launcher_run runs inside this window before the game, as the desktop start screen does\n"
     "    const bool force_launcher = getenv(\"LARECOMP_PS5_LAUNCHER\") != NULL;\n"
     "    bool skip_launcher = !force_launcher && (getenv(\"LARECOMP_NO_LAUNCHER\") || getenv(\"LARECOMP_INPUT\"));  // tests boot straight in\n"),
    ("        if (!strcmp(argv[i], \"--play\")) skip_launcher = true;\n",
     "        if (!strcmp(argv[i], \"--play\")) skip_launcher = !force_launcher;\n"),
    ("            if (gamelib_present(root)) skip_launcher = true;\n",
     "            if (gamelib_present(root) && !force_launcher) skip_launcher = true;\n"),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        sys.exit(__doc__)
    revert = '--revert' in sys.argv
    check = '--check' in sys.argv
    path = Path(args[0]) / 'main.c'
    text = path.read_text(encoding='utf-8')
    before = sha(path)
    applied = all(new in text for _, new in EDITS)
    pristine = all(old in text for old, _ in EDITS) and not applied
    original = text
    if applied:
        for old, new in EDITS:
            if original.count(new) != 1:
                sys.exit('%s: ambiguous applied launcher edit' % path)
            original = original.replace(new, old)
    original_sha = hashlib.sha256(original.encode('utf-8')).hexdigest()
    if original_sha not in PRISTINE_SHA256:
        sys.exit('%s: unrecognized runtime main.c SHA-256 %s; refusing runtime drift' % (path, original_sha))
    if check:
        print({'file': str(path), 'sha256': before, 'state': 'applied' if applied else 'pristine' if pristine else 'unknown'})
        return 0 if applied or pristine else 2
    if revert:
        if not applied:
            sys.exit('%s: the edits are not applied (state %s)' % (path, 'pristine' if pristine else 'unknown'))
        for old, new in EDITS:
            assert text.count(new) == 1, new
            text = text.replace(new, old)
    else:
        if applied:
            print({'file': str(path), 'sha256': before, 'state': 'already applied'})
            return 0
        if not pristine:
            sys.exit('%s: unexpected main.c (not the pinned text); refusing to edit' % path)
        for old, new in EDITS:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
    path.write_text(text, encoding='utf-8', newline='\n')
    print({'file': str(path), 'sha256_before': before, 'sha256_after': sha(path), 'edits': len(EDITS), 'reverted': revert})
    return 0


if __name__ == '__main__':
    sys.exit(main())
