"""Gate an existing zw command until the parent has armed process-tree containment."""
import json
import os
import subprocess
import sys

if sys.stdin.buffer.readline() != b'GO\n':
    sys.exit(125)
payload = json.loads(sys.stdin.buffer.readline())
# stdout/stderr are inherited. No shell and no global input injection.
sys.exit(subprocess.call([sys.executable, '-I', '-B', payload['zw'], 'pc', 'run', *payload['args']],
                         cwd=payload['canonical']))
