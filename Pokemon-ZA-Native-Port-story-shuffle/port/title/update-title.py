"""Replace only the verified PPSA91761 executable while no title is running."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_r3 as r

def main():
    if len(sys.argv) not in {4,5}:
        raise SystemExit('update-title.py BUILD_TAG LOCAL_EBOOT EXPECTED_INSTALLED_SHA256 [OWNED_TITLE_ID]')
    tag, source, expected = sys.argv[1:4]
    title=sys.argv[4] if len(sys.argv)>4 else 'PPSA91761'
    if title not in {'PPSA91761','PPSA91762'}:raise ValueError('Not an owned native title')
    if not tag.replace('-', '').isalnum() or len(expected) != 64:
        raise ValueError('Invalid update identity')
    if r.eboot_processes(): raise RuntimeError('A title is running; refusing update')
    r.TITLE = title
    r.TITLE_DIR = '/data/homebrew/' + r.TITLE
    r.REMOTE_EBOOT = r.TITLE_DIR + '/eboot.bin'
    r.REMOTE_EBOOT_NEW = r.REMOTE_EBOOT + '.new'
    r.RUN_TAG = 'title-' + tag
    r.PERSISTENT_JSON = f'/mnt/sandbox/{r.TITLE}_000/download0/unused-update-marker.json'
    r.PERSISTENT_LOG = f'/mnt/sandbox/{r.TITLE}_000/download0/unused-update-marker.log'
    c = r.Console()
    try:
        actual = c.sha256(r.REMOTE_EBOOT)
        if actual != expected: raise RuntimeError(f'Installed image changed: {actual}')
    finally:
        c.close()
    sys.argv = ['run_r3.py', 'update', '--eboot', source]
    return r.main()

if __name__ == '__main__':
    raise SystemExit(main())
