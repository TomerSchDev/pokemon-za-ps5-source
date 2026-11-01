"""No console IO: cache-transfer integrity, scope and preservation regression tests."""
import ftplib, io, json, tempfile, unittest, zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import install_offline_cache as tool

DATA=b'\x03\x02\x23\x07'+b'\0'*20
KEY='0123456789abcdef'


class FakeFTP:
    def __init__(self,corrupt=False): self.files={}; self.corrupt=corrupt; self.writes=[]
    def cwd(self,path): pass
    def mlsd(self): return [(p.rsplit('/',1)[1],{'type':'file'}) for p in self.files]
    def size(self,path):
        if path not in self.files: raise ftplib.error_perm('550 Not found')
        return len(self.files[path])
    def voidcmd(self,cmd): pass
    def sendcmd(self,cmd): pass
    def storbinary(self,cmd,stream,block):
        path=cmd[5:]; assert path.startswith(tool.REMOTE+'/'); assert '.offline-' in path
        self.writes.append(path); self.files[path]=stream.read()+(b'bad' if self.corrupt else b'')
    def retrbinary(self,cmd,callback,block): callback(self.files[cmd[5:]])
    def rename(self,source,target):
        assert target not in self.files,'existing cache overwritten'
        assert target.startswith(tool.REMOTE+'/') and target.endswith('.spv')
        self.files[target]=self.files.pop(source)
    def delete(self,path): self.files.pop(path,None)
    def close(self): pass


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def pack(self,key=KEY,data=DATA,record_data=DATA,title=tool.TITLE):
        path=self.root/'pack.zip'
        manifest=dict(schema=1,title=title,eboot_sha256=tool.EBOOT_SHA256,raw_shaderc_results=True,
                      files=[dict(key=key,bytes=len(record_data),spv_sha256=tool.digest(record_data),validated=True)])
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('manifest.json',json.dumps(manifest))
            archive.writestr('cache/spirv/'+key+'.spv',data)
        return path
    def invoke(self,fake,path,pin=tool.EBOOT_SHA256):
        original=tool.remote_sha
        def sha(ftp,p): return pin if p.endswith('/eboot.bin') else original(ftp,p)
        receipt=self.root/'receipt.json'
        with patch.object(tool,'connect',return_value=fake),patch.object(tool,'remote_sha',side_effect=sha),\
             patch('sys.argv',['installer',str(path),'--install','--workers','1','--receipt',str(receipt)]),redirect_stdout(io.StringIO()):
            tool.main()
        return json.loads(receipt.read_text())
    def test_corrupt_pack_rejected(self):
        with self.assertRaises(ValueError): tool.validate_pack(self.pack(data=b'x'+DATA[1:]))
    def test_traversal_key_rejected(self):
        with self.assertRaises(ValueError): tool.validate_pack(self.pack(key='../wrong'))
    def test_wrong_title_rejected(self):
        with self.assertRaises(ValueError): tool.validate_pack(self.pack(title='PPSA91761'))
    def test_identity_matches_verified_r15_artifact(self):
        root=Path(__file__).resolve().parents[2]
        receipt=root/'evidence/vk-title-randomizer-r15-update-20261028-041058Z.json'
        if not receipt.exists(): self.skipTest('Original local deployment evidence unavailable')
        verified=json.loads(receipt.read_bytes())
        self.assertEqual(tool.EBOOT_SHA256,verified['installed_sha256_after'])
        self.assertEqual(tool.file_digest(root/'artifacts/randomizer-r15/PPSA91762/eboot.bin'),tool.EBOOT_SHA256)
    def test_wrong_installed_build_no_writes(self):
        fake=FakeFTP()
        with self.assertRaises(RuntimeError): self.invoke(fake,self.pack(),pin='wrong')
        self.assertEqual(fake.writes,[])
    def test_existing_different_key_preserved(self):
        fake=FakeFTP(); target=tool.REMOTE+'/'+KEY+'.spv'; fake.files[target]=b'old version'
        report=self.invoke(fake,self.pack())
        self.assertTrue(report['complete']);self.assertEqual(fake.files[target],b'old version');self.assertFalse(fake.writes)
    def test_absent_key_verified_and_atomic(self):
        fake=FakeFTP();report=self.invoke(fake,self.pack())
        self.assertTrue(report['complete']);self.assertEqual(fake.files,{tool.REMOTE+'/'+KEY+'.spv':DATA})
        self.assertTrue(report['uploaded'][0]['readback_verified'])
    def test_remote_corruption_never_published(self):
        fake=FakeFTP(corrupt=True)
        with self.assertRaises(RuntimeError): self.invoke(fake,self.pack())
        self.assertEqual(fake.files,{})
        report=json.loads((self.root/'receipt.json').read_text())
        self.assertFalse(report['complete']);self.assertEqual(len(report['errors']),1)


if __name__=='__main__':unittest.main()
