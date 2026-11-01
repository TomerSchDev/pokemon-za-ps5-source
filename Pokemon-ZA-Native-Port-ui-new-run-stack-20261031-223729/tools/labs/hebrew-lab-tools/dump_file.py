"""Print one message file (labels + token text), local inspection only."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfmsg import *
p = sys.argv[1]
m = MsgFile(open(p + '.dat', 'rb').read()); t = read_tbl(open(p + '.tbl', 'rb').read())
lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, len(m.lines))
for i in range(lo, min(hi, len(m.lines))):
    print(i, t[i][1], m.params[i], repr(decode_units(m.lines[i]))[:150])
