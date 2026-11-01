"""Create a standalone, private searchable glossary review. The page cannot approve the glossary."""
import csv
import hashlib
import json
from pathlib import Path

LAB=Path(__file__).resolve().parents[1]

def build(glossary=None,out=None):
    glossary=Path(glossary or LAB/'glossary.tsv');out=Path(out or LAB/'review-glossary.html')
    with glossary.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f,delimiter='\t'))
    digest=hashlib.sha256(glossary.read_bytes()).hexdigest()
    data=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>מילון פוקימון — טיוטה לבדיקה</title>
<style>body{font:16px system-ui;background:#f5f7f9;color:#172b39;margin:0}main{max-width:1450px;margin:auto;padding:28px}h1{margin:0 0 8px}p{line-height:1.7}.card{background:white;border:1px solid #dce3e9;border-radius:12px;padding:18px;margin:18px 0}.controls{display:flex;gap:12px;flex-wrap:wrap}input,select,button{font:inherit;border:1px solid #bbc8d1;border-radius:7px;padding:9px}input{min-width:280px;flex:1}button{background:#eaf4ef;cursor:pointer}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:right;vertical-align:top;padding:12px;border-bottom:1px solid #e4e9ed}th{background:#e6eef2;position:sticky;top:0}td.en{direction:ltr;text-align:left;min-width:180px}td.note{color:#586b76;max-width:530px;font-size:14px}td.he{font-size:18px;min-width:170px}.missing{background:#fff1ed}.pager{display:flex;gap:12px;align-items:center;margin:15px 0}code{direction:ltr;display:inline-block;overflow-wrap:anywhere;font-size:12px}.pill{display:inline-block;background:#e7edf1;padding:5px 9px;border-radius:20px}small{color:#5b6e79}</style>
<main><h1>מילון פוקימון משותף</h1><p>טיוטה לבדיקה לפני תרגום האצוות. כל הסוכנים והכלים משתמשים באותו מילון. ניסוחים אוטומטיים ותעתיקים משוערים מסומנים בהערות; הם אינם תרגום מאושר.</p>
<div class="card"><span class="pill" id="total"></span><p><b>כללי היסוד:</b> שמות פוקימונים ושמות פרטיים בתעתיק; מהלכים, יכולות וחפצים לפי המשמעות; פנייה ניטרלית; ללא ניקוד. מונח חדש נרשם כהצעה ובדיקת התנגשויות קודמת לאיחודו.</p><small>SHA-256 של קובץ המילון: <code>__DIGEST__</code>. האישור ניתן בשיחה ומתייחס לגרסה זו; עמוד זה אינו מאשר דבר.</small></div>
<div class="card controls"><input id="q" placeholder="חיפוש בעברית או באנגלית" aria-label="חיפוש במילון"><select id="cat" aria-label="קטגוריה"><option value="">כל הקטגוריות</option></select><select id="status" aria-label="מצב בדיקה"><option value="">כל המצבים</option><option value="missing">חסר תרגום</option><option value="review">מסומן לבדיקה</option><option value="seed">מונחי יסוד קבועים</option></select><button id="download">הורדת המילון</button></div>
<div class="pager"><button id="prev">הקודם</button><span id="position"></span><button id="next">הבא</button></div>
<table><thead><tr><th>מונח באנגלית</th><th>עברית מוצעת</th><th>קטגוריה</th><th>הערה ומצב בדיקה</th></tr></thead><tbody id="body"></tbody></table><div class="pager"><button id="top">לראש העמוד</button></div></main>
<script>const rows=__DATA__;let page=0;const size=100;const $=x=>document.getElementById(x);
const categories=[...new Set(rows.map(r=>r.category))].sort();for(const c of categories){const o=document.createElement('option');o.value=c;o.textContent=c;$('cat').append(o)}
function filter(){const q=$('q').value.toLocaleLowerCase(),c=$('cat').value,s=$('status').value;return rows.filter(r=>(!c||r.category===c)&&(!q||Object.values(r).join(' ').toLocaleLowerCase().includes(q))&&(!s||(s==='missing'&&!r.hebrew)||(s==='review'&&/בדיק|ביקורת|משוער|אוטומטי|needs.review|candidate/i.test(r.note))||(s==='seed'&&/קבוע|מחייב|seed|locked/i.test(r.note))))}
function render(){const rs=filter();page=Math.min(page,Math.max(0,Math.ceil(rs.length/size)-1));$('body').replaceChildren();for(const r of rs.slice(page*size,(page+1)*size)){const tr=document.createElement('tr');if(!r.hebrew)tr.className='missing';for(const [k,cls] of [['english','en'],['hebrew','he'],['category','category'],['note','note']]){const td=document.createElement('td');td.className=cls;td.textContent=r[k]||'—';tr.append(td)}$('body').append(tr)}$('position').textContent=`${rs.length.toLocaleString('he-IL')} רשומות · עמוד ${page+1} מתוך ${Math.max(1,Math.ceil(rs.length/size))}`;$('prev').disabled=page===0;$('next').disabled=(page+1)*size>=rs.length;$('total').textContent=`${rows.length.toLocaleString('he-IL')} רשומות מונחים`}
for(const id of ['q','cat','status'])$(id).addEventListener('input',()=>{page=0;render()});$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render()};$('top').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
$('download').onclick=()=>{const clean=v=>String(v||'').replace(/[\t\r\n]+/g,' ');const text=['english\thebrew\tcategory\tnote',...rows.map(r=>['english','hebrew','category','note'].map(k=>clean(r[k])).join('\t'))].join('\n');const u=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/tab-separated-values;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download='glossary-review.tsv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};render();</script></html>'''
    # Keep JS escape sequences literal in the generated file.
    page=page.replace("/[\t\r\n]+/g","/[\\t\\r\\n]+/g").replace(".join('\n')",".join('\\n')")
    page=page.replace('__DIGEST__',digest).replace('__DATA__',data)
    out.write_text(page,encoding='utf-8');return {'rows':len(rows),'sha256':digest,'path':str(out)}

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
