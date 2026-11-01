#!/usr/bin/env bash
# Run the pinned historical RADV recipe against a PRIVATE facade, never its shared ROOT.
set -euo pipefail
[[ $# == 4 ]] || exit 2
source "$1/tools/radv-link.sh"
radv_link_recipe "$1" "$2" "$3"
python3 - "$4" "${#radv_linker_script[@]}" "${#radv_link_flags[@]}" \
    "${radv_linker_script[@]}" "${radv_link_flags[@]}" "${radv_link_inputs[@]}" <<'PY'
import json, sys
path, ns, nf, *args = sys.argv[1:]
ns, nf = int(ns), int(nf)
with open(path, 'x') as f:
    json.dump(dict(radv_linker_script=args[:ns], radv_link_flags=args[ns:ns+nf],
                   radv_link_inputs=args[ns+nf:]), f, indent=2)
    f.write('\n')
PY
