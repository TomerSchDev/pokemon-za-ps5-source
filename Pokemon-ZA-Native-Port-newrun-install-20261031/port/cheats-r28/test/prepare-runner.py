from pathlib import Path
p=Path(__file__).with_name('run-pc.py')
s=p.read_text()
s=s.replace("choices=[10000,100000,1000000],default=10000","choices=[1,10,99,999],default=99")
s=s.replace("a=p.parse_args();assert", "p.add_argument('--item-id',type=int,default=50);p.add_argument('--all-items',action='store_true')\na=p.parse_args();assert")
s=s.replace("sent=False", "sent=False;sequence=0;completed=0;queue=json.loads((Path(__file__).resolve().parents[1]/'research/menu-catalog.json').read_text()) if a.all_items else [{'id':a.item_id}]")
old="""                if a.money_after_shot and not sent and (out/'build/frames'/f'frame_{a.money_after_shot:05d}.png').exists():
                    (out/'money-command.txt').write_text(f'1 {a.amount}\\n');sent=True
                    record['money_request_after_shot']=a.money_after_shot;record['money_request_amount']=a.amount"""
new="""                log=(out/'r28items-control.log').read_text() if (out/'r28items-control.log').exists() else ''
                if sequence and f'done={sequence} ' in log:completed=sequence
                if a.money_after_shot and completed==sequence and sequence<len(queue) and (out/'build/frames'/f'frame_{a.money_after_shot:05d}.png').exists():
                    item=queue[sequence];sequence+=1
                    (out/'money-command.txt').write_text(f'{sequence} {item['id']} {a.amount}\\n');sent=True
                    record['item_requests_sent']=sequence
                    record['item_requests_completed']=completed
                record['item_requests_completed']=completed"""
assert old in s
s=s.replace(old,new)
p.write_text(s)
