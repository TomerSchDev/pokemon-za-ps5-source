import importlib.util
from pathlib import Path
import tempfile
import json
from client import text_command,issue,status,collect,BASE,COMMAND

session='1234567890abcdef'
class FTP:
    def __init__(self):self.files={BASE+'/session.json':json.dumps({'protocol':17,'title':'PPSA91762','session':session}).encode()}
    def retrbinary(self,cmd,callback,blocksize):callback(self.files[cmd.removeprefix('RETR ')])
    def storbinary(self,cmd,stream):self.files[cmd.removeprefix('STOR ')]=stream.read()
    def rename(self,a,b):self.files[b]=self.files.pop(a)
ftp=FTP();assert status(ftp)['session']==session
assert issue(ftp,session,1,'snapshot')==ftp.files[COMMAND]
assert issue(ftp,session,2,'measure',30).endswith(b'measure 30\n')
assert issue(ftp,session,3,'input','A',3).endswith(b'input A 3\n')
for op,arg,frames in [('measure',0,None),('measure',121,None),('input','A',121),('input','arbitrary',1),('continue','../save',None),('fps',2,None)]:
    try:text_command(session,4,op,arg,frames)
    except AssertionError:pass
    else:raise AssertionError((op,arg,frames))
try:issue(ftp,'0000000000000000',5,'snapshot')
except RuntimeError:pass
else:raise AssertionError('foreign session accepted')
with tempfile.TemporaryDirectory() as temp:
    ack=BASE+'/session_'+session+'/ack_9.json'
    ftp.files[ack]=json.dumps({'session':session,'seq':9,'op':'snapshot','result':'saved','file':'../../x'}).encode()
    try:collect(ftp,session,9,Path(temp))
    except ValueError:pass
    else:raise AssertionError('unsafe output path accepted')
print('Client session, bounds, fixed paths, atomic mailbox and output traversal checks passed; no console contacted.')
