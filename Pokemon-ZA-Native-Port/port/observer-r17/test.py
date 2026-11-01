"""Host tests; use existing compiler, sanitizers and independent PNG decoder."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import importlib.util
import zlib
import struct
from PIL import Image

here=Path(__file__).resolve().parent
root=here.parents[1]
shim=Path('/home/tomer/ps5-za-native/perf-r16-20261028/port/sdl3-shim/include')
sdk=Path('/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk')
spec=importlib.util.spec_from_file_location('analyze',here/'analyze.py');analyzer=importlib.util.module_from_spec(spec);spec.loader.exec_module(analyzer)
flags=['clang-21','-std=c11','-O2','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
with tempfile.TemporaryDirectory(prefix='za-observer-r17-') as tmp:
    tmp=Path(tmp);store=tmp/'store'
    subprocess.run(flags+[str(here/'test-observer.c'),'-o',str(tmp/'observer'),'-DZA_OBSERVER_HOST_TEST=1',
        f'-DZA_OBSERVER_ROOT="{store}"',f'-DZA_OBSERVER_ENABLE="{tmp}/enable.txt"'],check=True)
    subprocess.run([str(tmp/'observer')],check=True)
    session=next(store.glob('session_*'))
    report=analyzer.analyze(session/'measure_10.csv')
    assert 29.99<report['all_intervals']['interval_rate_fps']<30.01
    assert report['all_intervals']['intervals']==31
    assert report['shader_affected_intervals']>=1
    assert json.loads((session/'ack_10.json').read_text())['result']=='complete'
    assert json.loads((session/'ack_12.json').read_text())['result']=='clock_or_frame_reset'
    assert json.loads((session/'ack_13.json').read_text())['result']=='buffer_full'
    subprocess.run(flags+['-I'+str(shim),str(here/'title_png.c'),str(here/'test-title-png.c'),
        '-Wl,--wrap=fwrite','-Wl,--wrap=fclose','-o',str(tmp/'png')],check=True)
    png_result=subprocess.run([str(tmp/'png'),str(tmp)],check=True,capture_output=True,text=True)
    sizes=[(1,1),(5,7),(16383,1),(16384,1),(257,257)]
    for fmt in range(2):
        for negative in range(2):
            for index,(w,h) in enumerate(sizes):
                path=tmp/f'fmt{fmt}_neg{negative}_case{index}.png';data=path.read_bytes();at=8;compressed=b''
                while at<len(data):
                    n=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8];payload=data[at+8:at+8+n]
                    assert zlib.crc32(kind+payload)==struct.unpack_from('>I',data,at+8+n)[0]
                    if kind==b'IDAT':compressed+=payload
                    at+=12+n
                assert len(zlib.decompress(compressed))==(w*4+1)*h
                expected=bytes(v&255 for y in range(h) for x in range(w) for v in (x*31+y*7,x*3+y*41,x*19+y*11,x*17+y*23))
                with Image.open(path) as im:assert im.convert('RGBA').tobytes()==expected
    for name in ['title_png','observer']:
        subprocess.run([str(sdk/'bin/prospero-clang'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(shim),
            '-c',str(here/f'{name}.c'),'-o',str(tmp/f'{name}.o')],check=True)
    evidence={'host_observer_tests':'passed','png':json.loads(png_result.stdout),'png_exact_decodes':20,
              'sanitizers':['ASan','UBSan'],'ps5_cross_compile':'passed','console_measured':False,
              'png_source_sha256':hashlib.sha256((here/'title_png.c').read_bytes()).hexdigest(),
              'synthetic_measurement':report}
    (root/'evidence/observer-r17/host-tests.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
