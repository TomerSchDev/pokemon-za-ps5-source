"""Tiny standalone, read-only queue monitor. No console/network calls and no queue writes."""
import argparse
from datetime import datetime
import importlib.util
from pathlib import Path
import tkinter as tk
from tkinter import ttk

CANONICAL = Path('C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port')
spec = importlib.util.spec_from_file_location('monitor_queue', CANONICAL / 'tools/console-install-queue/console_queue.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

BG, INK, MUTED = '#f6f4ef', '#253b3a', '#73837e'
TEAL, PEACH, RED = '#287c70', '#e9aa7e', '#ad4e49'


def view_model(status):
    active = status['active']
    waiting = [r for r in status['jobs'] if r['state'] == 'queued']
    if active is None:
        return {'owner': 'אין סוכן פעיל', 'task': 'ממתינים לסיבוב הבא', 'stage': 'פנוי' if not waiting else 'ממתין לראש התור',
                'clock': '—', 'hint': 'אין כרגע זמן פינוי', 'progress': 0, 'color': TEAL, 'waiting': waiting}
    row = next((r for r in status['jobs'] if r['ticket'] == active['ticket']), {})
    remaining = active.get('seconds_to_yield')
    if active.get('paused'):
        clock, stage, hint, color = 'Ⅱ', 'הקונסולה מנותקת', 'התור נשמר · הזמן מוקפא', PEACH
    elif active.get('expired'):
        clock, stage, hint, color = '!', 'לא התקבל אות חיים', 'התור חסום עד בירור · אין השתלטות', RED
    elif remaining is None:
        clock, stage, hint, color = '∞', 'בתור עכשיו', 'אין ממתינים · ללא הגבלת זמן', TEAL
    else:
        seconds = max(0, int(remaining))
        clock = '%02d:%02d' % divmod(seconds, 60)
        stage = 'זמן למסירה' if not active.get('must_yield') else 'נדרש לסיים ולמסור'
        hint, color = 'הזמן כולל ניקוי והחזרה לבסיס', TEAL if seconds > 60 else RED
    phase = {'reserved': 'הכנה', 'installing': 'התקנה / בדיקה'}.get(active.get('phase'), active.get('phase', ''))
    return {'owner': active['agent'], 'task': row.get('job', {}).get('name', 'פרטי המשימה אינם זמינים'),
            'stage': stage + (' · ' + phase if not active.get('paused') else ''),
            'clock': clock, 'hint': hint, 'color': color, 'waiting': waiting,
            'progress': 0 if remaining is None or active.get('paused') else max(0, min(100, 100 * remaining / status['yield_seconds']))}


class Card(tk.Frame):
    def __init__(self, master, resource, heading, badge, color):
        super().__init__(master, bg='white', padx=16, pady=10, highlightthickness=1, highlightbackground='#e4e7df')
        self.resource = resource
        top = tk.Frame(self, bg='white'); top.pack(fill='x')
        tk.Label(top, text=badge, bg=color, fg='white', font=('Segoe UI', 11, 'bold'), padx=9, pady=4).pack(side='left')
        self.stage = tk.Label(top, text=heading, bg='white', fg=INK, font=('Segoe UI', 13, 'bold'), anchor='e')
        self.stage.pack(side='right')
        self.owner = tk.Label(self, bg='white', fg=INK, font=('Segoe UI', 10, 'bold'), anchor='w')
        self.owner.pack(fill='x', pady=(7, 0))
        self.task = tk.Label(self, bg='white', fg=MUTED, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=300, height=1)
        self.task.pack(fill='x')
        clockrow = tk.Frame(self, bg='white'); clockrow.pack(fill='x', pady=3)
        self.clock = tk.Label(clockrow, bg='white', fg=color, font=('Consolas', 24, 'bold'))
        self.clock.pack(side='left')
        self.phase = tk.Label(clockrow, bg='white', fg=MUTED, font=('Segoe UI', 9), wraplength=185, justify='right')
        self.phase.pack(side='right')
        self.progress = ttk.Progressbar(self, maximum=100, mode='determinate'); self.progress.pack(fill='x', pady=3)
        self.hint = tk.Label(self, bg='white', fg=MUTED, font=('Segoe UI', 9), anchor='e'); self.hint.pack(fill='x')
        self.queue_title = tk.Label(self, bg='white', fg=INK, font=('Segoe UI', 9, 'bold'), anchor='e')
        self.queue_title.pack(fill='x', pady=(5, 3))
        frame = tk.Frame(self, bg='white'); frame.pack(fill='both', expand=True)
        self.rows = tk.Listbox(frame, height=2, bg='#f6f8f5', fg=INK, font=('Segoe UI', 9), relief='flat',
                               highlightthickness=0, activestyle='none', exportselection=False)
        bar = ttk.Scrollbar(frame, orient='vertical', command=self.rows.yview)
        self.rows.configure(yscrollcommand=bar.set); self.rows.pack(side='left', fill='both', expand=True); bar.pack(side='right', fill='y')
        self.last_rows = None

    def refresh(self):
        try:
            status = q.Board(resource=self.resource).status()
            model = view_model(status)
            self.owner.config(text=model['owner'])
            self.task.config(text=model['task'])
            self.phase.config(text=model['stage'])
            self.clock.config(text=model['clock'], fg=model['color'])
            self.hint.config(text=model['hint'], fg=MUTED)
            self.progress['value'] = model['progress']
            waiting = model['waiting']
            self.queue_title.config(text='בתור: %d' % len(waiting))
            rows = ['%d. %s  ·  #%s\n' % (i, row['requested_by'], row['ticket']) for i, row in enumerate(waiting, 1)]
            if not rows: rows = ['התור ריק · כולם יכולים לנשום']
            if rows != self.last_rows:
                self.rows.delete(0, 'end')
                for row in rows: self.rows.insert('end', row.strip())
                self.last_rows = rows
        except (q.QueueError, OSError, KeyError, TypeError) as error:
            self.phase.config(text='לא ניתן לקרוא את התור')
            self.hint.config(text=str(error)[:70], fg=RED)
            self.clock.config(text='?', fg=RED)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true', help='render once and exit; no state changes')
    args = parser.parse_args()
    root = tk.Tk(); root.title('ZA Queue Garden')
    root.configure(bg=BG); root.minsize(350, 640)
    root.geometry('370x680+%d+45' % max(0, root.winfo_screenwidth() - 394))
    root.option_add('*Font', ('Segoe UI', 10))
    style = ttk.Style(root); style.theme_use('clam')
    style.configure('TProgressbar', troughcolor='#edf1e9', background=TEAL, bordercolor='#edf1e9', lightcolor=TEAL, darkcolor=TEAL, thickness=4)
    header = tk.Frame(root, bg=BG, padx=17, pady=10); header.pack(fill='x')
    tk.Label(header, text='🌱', font=('Segoe UI Emoji', 22), bg=BG).pack(side='left')
    tk.Label(header, text='תורי המעבדה', bg=BG, fg=INK, font=('Segoe UI', 17, 'bold')).pack(side='right')
    always = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text='תמיד מעל חלונות אחרים', variable=always,
                   command=lambda: root.attributes('-topmost', always.get()), bg=BG, fg=MUTED,
                   activebackground=BG, relief='flat', font=('Segoe UI', 9)).pack(anchor='e', padx=16)
    pc = Card(root, 'pc', 'בדיקות מחשב', 'PC', TEAL); pc.pack(fill='both', expand=True, padx=14, pady=(5, 6))
    console = Card(root, 'console', 'תור הקונסולה', 'PS5', '#ac7957'); console.pack(fill='both', expand=True, padx=14, pady=6)
    footer = tk.Label(root, bg=BG, fg=MUTED, font=('Segoe UI', 8)); footer.pack(pady=(2, 8))
    def tick():
        pc.refresh(); console.refresh()
        footer.config(text='קריאה בלבד · מצב מקומי · ' + datetime.now().strftime('%H:%M:%S'))
        root.after(1000, tick)
    tick(); root.update()
    if args.smoke:
        root.destroy(); return
    root.mainloop()


if __name__ == '__main__':
    main()
