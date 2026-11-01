"""Exercise the exact fixed-title SQL transaction on an isolated host fixture."""
from pathlib import Path
import json, sqlite3, subprocess, tempfile
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='za-rename-test-') as temp:
    p=Path(temp);db=p/'app.db';backup=p/'before.db';log=p/'rename.log';exe=p/'rename'
    subprocess.run(['clang-21','-Wall','-Wextra','-Werror','-I'+str(root/'artifacts/sqlite-source'),
        '-DZA_DB_PATH="'+str(db)+'"','-DZA_DB_BACKUP="'+str(backup)+'"','-DZA_RENAME_LOG="'+str(log)+'"',
        str(root/'port/title/rename_title.c'),'-l:libsqlite3.so.0','-o',str(exe)],check=True)
    with sqlite3.connect(db) as c:
        c.execute('create table tbl_contentinfo (titleId text primary key,titleName text,AppInfoJson text)')
        c.execute('insert into tbl_contentinfo values(?,?,?)',('PPSA91761','ZA Native Title R2 (Test)',json.dumps({'TITLE':'ZA Native Title R2 (Test)','TITLE_01':'ZA Native Title R2 (Test)','other':42})))
        c.execute('insert into tbl_contentinfo values(?,?,?)',('OTHER0001','Other game','{}'))
    subprocess.run([str(exe)],check=True)
    with sqlite3.connect(db) as c:
        rows=c.execute('select * from tbl_contentinfo order by titleId').fetchall()
        assert rows[0]==('OTHER0001','Other game','{}')
        assert rows[1][1]=='Pokémon Legends: Z-A'
        data=json.loads(rows[1][2]);assert data['TITLE']==data['TITLE_01']==rows[1][1] and data['other']==42
    with sqlite3.connect(backup) as c:
        assert c.execute('select titleName from tbl_contentinfo where titleId="PPSA91761"').fetchone()[0]=='ZA Native Title R2 (Test)'
    before=db.read_bytes();oldbackup=backup.read_bytes()
    subprocess.run([str(exe)],check=True)
    assert db.read_bytes()==before and backup.read_bytes()==oldbackup
    with sqlite3.connect(db) as c:c.execute('update tbl_contentinfo set titleName="Unexpected" where titleId="PPSA91761"')
    before=db.read_bytes();assert subprocess.run([str(exe)]).returncode!=0
    assert db.read_bytes()==before
    print('PASS: exactly one title, JSON fields preserved, consistent backup, idempotence, unexpected-name refusal')

