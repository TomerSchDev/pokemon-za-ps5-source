#!/usr/bin/env bash
# Host check of the PS5 RTL logic: the same rtl_engine.c and the same pinned FriBidi 1.0.16 tarball, built for Linux,
# run through hebrew-lab/tests/test_rtl_engine_native.py (C transform vs the independent Python bidi path).
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/hebrew-rtl/test-host.sh OUT
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab=$(cd "$here/../../../hebrew-lab" && pwd)
out=${1:?OUT required}/hosttest
tarball=$lab/deliverables/Hebrew-RTL-PC-20261031-r2/source/third-party/fribidi-1.0.16.tar.xz
[[ $(sha256sum "$tarball" | cut -d' ' -f1) == 1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c ]]
[[ ! -e $out ]] || { echo "new folder required: $out" >&2; exit 2; }
mkdir -p "$out"; tar -C "$out" -xf "$tarball"; fb=$out/fribidi-1.0.16
(cd "$fb" && ./configure --disable-docs > "$out/configure.log" 2>&1)   # headers only, as in the PS5 build
runtime=/home/tomer/ps5-za-native/r28b-dlc-dex-20261030-c01/source/runtime
/usr/bin/clang-21 -shared -fPIC -O2 -std=gnu11 -DRTL_ENGINE_TEST '-D__declspec(x)=' -include string.h -I"$runtime" -I"$fb/lib" \
  -DHAVE_CONFIG_H -I"$fb" "$here/src/rtl_engine.c" "$fb"/lib/*.c -o "$out/librtl_test.so"
python3 -m venv "$out/venv" && "$out/venv/bin/pip" install -q python-bidi==0.6.12   # = hebrew-lab/requirements-lock.txt
RTL_TEST_DLL=$out/librtl_test.so "$out/venv/bin/python" -c "
import os,runpy,sys
os.add_dll_directory=lambda p:None          # Windows-only call in the test's setup
sys.argv=['test_rtl_engine_native','-v']
runpy.run_path('$lab/tests/test_rtl_engine_native.py',run_name='__main__')" 2>&1 | tee "$out/tests.log"
