"""Build a pinned, fixed-destination copy of the existing reviewed asset installer."""
from pathlib import Path
import hashlib,json,shutil,subprocess,tarfile,urllib.request
from storage_paths import data_root
ROOT=data_root();OUT=ROOT/'qa/all-pokemon-20261030-r2/console-fifty-20261031-r1'
BASE=Path(__file__).resolve().parents[3];LOCAL=BASE/'console-qa-fifty-20261031-r1/compiler'
def linux(p):
 s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')
def main():
 LOCAL.mkdir(parents=True,exist_ok=True)
 package=json.loads((OUT/'model-package.json').read_text())
 archive=OUT/'compiler-mbedtls-3.6.0.tar.gz'
 url='https://codeload.github.com/Mbed-TLS/mbedtls/tar.gz/refs/tags/mbedtls-3.6.0'
 if not archive.exists():
  with urllib.request.urlopen(url,timeout=30) as response,archive.open('xb') as out:shutil.copyfileobj(response,out)
 vendor=LOCAL/'vendor'
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if not member.isfile():continue
   rel=Path(*Path(member.name).parts[1:])
   if not ((rel.parts[:2]==('include','mbedtls') and rel.suffix=='.h') or (rel.parts[:1]==('library',) and (rel.suffix=='.h' or rel.name=='sha256.c'))):continue
   assert '..' not in rel.parts
   p=vendor/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(member).read())
 original=BASE/'species-lab/import-all-20261030/console-install-20261030/install_models.c'
 macros={
 'PACKAGE':'/data/homebrew/PPSA91762/console-fifty-models-20261031-r1.zip',
 'MANIFEST':'/data/homebrew/PPSA91762/console-fifty-models-20261031-r1.manifest.bin',
 'STAGE':'/data/homebrew/PPSA91762/.console-fifty-20261031-r1-staging',
 'FINAL':'/data/homebrew/PPSA91762/console-fifty-20261031-r1-models',
 'LOGPATH':'/data/console-fifty-20261031-r1-extract.log',
 'REPORT':'/data/console-fifty-20261031-r1-extract.json',
 'EXPECT_ZIP':package['zip_sha256'],'EXPECT_MANIFEST':package['manifest_sha256']}
 prefix=''.join('#define %s %s\n'%(k,json.dumps(v)) for k,v in macros.items())
 prefix+='#define EXPECT_FILES %du\n#define EXPECT_BYTES UINT64_C(%d)\n'%(package['files'],package['uncompressed_bytes'])
 source=LOCAL/'install_fifty.c';source.write_text(prefix+original.read_text(encoding='utf-8'),encoding='utf-8')
 for name in ('ioapi.o','unzip.o'):shutil.copyfile(ROOT/'console-install-20261030/objects'/name,LOCAL/name)
 sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
 zlib='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/zlib/zlib-1.3.2'
 flags=['-std=gnu11','-O2','-Wall','-Wno-misleading-indentation','-DNOCRYPT','-DUSE_FILE32API','-I'+zlib,'-I'+zlib+'/contrib/minizip','-I'+linux(vendor/'include'),'-I'+linux(vendor/'library'),'-I'+linux(BASE/'Pokemon-ZA-Native-Port/port/randomizer/core'),'-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"']
 for name,p in (('sha256',vendor/'library/sha256.c'),('install_fifty',source)):
  subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang']+flags+['-c',linux(p),'-o',linux(LOCAL/(name+'.o'))],check=True)
 elf=LOCAL/'install-fifty.elf'
 subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang','-O2']+[linux(LOCAL/(n+'.o')) for n in ('install_fifty','sha256','unzip','ioapi')]+[zlib+'/libz.a','-o',linux(elf)],check=True)
 subprocess.run(['wsl.exe','-e',sdk+'/bin/llvm-nm','--dynamic','--undefined-only',linux(elf)],check=True)
 destination=OUT/'install-fifty.elf';shutil.copyfile(elf,destination)
 assert hashlib.sha256(destination.read_bytes()).digest()==hashlib.sha256(elf.read_bytes()).digest()
 (OUT/'installer-build.json').write_text(json.dumps({'source':str(original),'macros':macros,'mbedtls_source':url,'mbedtls_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'installer_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'destination':str(destination)},indent=1))
 print('Built pinned asset installer: '+str(destination),flush=True)
if __name__=='__main__':main()
