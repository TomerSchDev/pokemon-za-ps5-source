"""Queue Garden: read-only mobile API on loopback + this computer's Tailscale IP.

No console probing, no queue mutation, no arbitrary paths and no credentials in responses.
Pairing/session state lives in the user's LocalAppData, outside source and deliverables.
"""
import argparse
from collections import defaultdict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import uuid

PORT = 8769
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'QueueGardenBridge'


def load_queue():
    spec = importlib.util.spec_from_file_location('mobile_queue', HERE / 'console_queue.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def tail_ip():
    exe = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale/tailscale.exe'
    result = subprocess.run([str(exe), 'ip', '-4'], capture_output=True, text=True, timeout=8,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''
    if result.returncode or ipaddress.ip_address(value) not in ipaddress.ip_network('100.64.0.0/10'):
        raise RuntimeError('Tailscale is not connected')
    return value


class Pairing:
    def __init__(self, folder=STATE, clock=time.time):
        self.folder, self.clock = Path(folder), clock
        self.path = self.folder / 'devices.json'
        self.lock = threading.RLock()
        self.attempts = defaultdict(list)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if self.data.get('schema') != 1: raise ValueError('Unsupported private pairing state')
        else:
            self.data = {'schema': 1, 'server_id': uuid.uuid4().hex, 'tokens': {}}
            self.save()
        self.code, self.code_until = '', 0

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name('devices-' + uuid.uuid4().hex + '.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(self.data, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def rotate(self):
        with self.lock:
            self.code = '%06d' % secrets.randbelow(1000000)
            self.code_until = self.clock() + 600
            return self.code

    def pair(self, code, client):
        with self.lock:
            now = self.clock()
            recent = [stamp for stamp in self.attempts[client] if now - stamp < 60]
            self.attempts[client] = recent
            if len(recent) >= 5: raise PermissionError('RATE_LIMIT')
            recent.append(now)
            if not self.code or now >= self.code_until or not hmac.compare_digest(str(code), self.code):
                raise PermissionError('PAIRING_FAILED')
            token = secrets.token_urlsafe(32)
            self.data['tokens'][hashlib.sha256(token.encode()).hexdigest()] = {'paired_at': now}
            self.save()
            self.code = ''; self.code_until = 0  # One successful use only.
            return token

    def authorized(self, header):
        if not isinstance(header, str) or not header.startswith('Bearer '): return False
        supplied = hashlib.sha256(header[7:].encode()).hexdigest()
        with self.lock: return any(hmac.compare_digest(supplied, known) for known in self.data['tokens'])


def public_snapshot(queue, clock=time.time):
    result = {'schema': 1, 'generated_at': clock(), 'queues': {}}
    for resource in ('pc', 'console'):
        try:
            status = queue.Board(resource=resource).status()
            active = status['active']
            public = None
            if active is not None:
                keys = ('ticket', 'agent', 'phase', 'acquired_at', 'heartbeat_at', 'expired',
                        'paused', 'must_yield', 'yield_by', 'seconds_to_yield')
                public = {key: active.get(key) for key in keys}
                row = next((r for r in status['jobs'] if r['ticket'] == active['ticket']), {})
                public['task'] = str(row.get('job', {}).get('name', ''))[:500]
            waiting = [{'ticket': row['ticket'], 'agent': row['requested_by'],
                        'task': str(row['job'].get('name', ''))[:500], 'position': i}
                       for i, row in enumerate((r for r in status['jobs'] if r['state'] == 'queued'), 1)]
            result['queues'][resource] = {'ok': True, 'resource': resource, 'generation': status['generation'],
                'yield_seconds': status['yield_seconds'], 'active': public,
                'waiting_count': len(waiting), 'waiting': waiting[:200]}
        except Exception:
            # Never serialize paths, exception details, baseline manifests or private state.
            result['queues'][resource] = {'ok': False, 'resource': resource, 'error': 'STATE_UNAVAILABLE'}
    return result


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, address, pairing, queue, show=None):
        self.pairing, self.queue, self.show = pairing, queue, show
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'QueueGarden/1.0'
    def log_message(self, *_): pass  # Do not log pairing codes or bearer headers.
    def setup(self):
        super().setup(); self.connection.settimeout(10)
    def send_json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(raw)
    def allowed_peer(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
            return address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')
        except ValueError: return False
    def do_GET(self):
        if not self.allowed_peer(): return self.send_json(403, {'error': 'TAILSCALE_REQUIRED'})
        if self.headers.get('Origin'): return self.send_json(403, {'error': 'NATIVE_CLIENT_ONLY'})
        if self.path == '/health': return self.send_json(200, {'app': 'queue-garden', 'schema': 1})
        if self.path != '/v1/status': return self.send_json(404, {'error': 'NOT_FOUND'})
        if not self.server.pairing.authorized(self.headers.get('Authorization')):
            return self.send_json(401, {'error': 'PAIRING_REQUIRED'})
        snapshot = public_snapshot(self.server.queue)
        snapshot['server_id'] = self.server.pairing.data['server_id']
        self.send_json(200, snapshot)
    def do_POST(self):
        if not self.allowed_peer(): return self.send_json(403, {'error': 'TAILSCALE_REQUIRED'})
        if self.headers.get('Origin'): return self.send_json(403, {'error': 'NATIVE_CLIENT_ONLY'})
        if self.path == '/local/show':
            if self.server.server_address[0] != '127.0.0.1' or not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return self.send_json(403, {'error': 'LOCAL_ONLY'})
            if self.headers.get('X-QueueGarden-Local') != '1': return self.send_json(403, {'error': 'LOCAL_ONLY'})
            if self.server.show: self.server.show()
            return self.send_json(200, {'ok': True})
        if self.path != '/v1/pair': return self.send_json(405, {'error': 'READ_ONLY'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 1 <= size <= 2048 or self.headers.get('Transfer-Encoding'): raise ValueError()
            data = json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(data, dict): raise ValueError()
            code = data.get('code', '')
            if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit(): raise ValueError()
            token = self.server.pairing.pair(code, self.client_address[0])
            return self.send_json(200, {'token': token, 'server_id': self.server.pairing.data['server_id']})
        except PermissionError as error:
            return self.send_json(429 if str(error) == 'RATE_LIMIT' else 403, {'error': str(error)})
        except (ValueError, UnicodeError, TypeError): return self.send_json(400, {'error': 'BAD_REQUEST'})
    def do_PUT(self): self.send_json(405, {'error': 'READ_ONLY'})
    def do_DELETE(self): self.send_json(405, {'error': 'READ_ONLY'})


def show_existing(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/health' % port, timeout=2) as response:
            if json.load(response).get('app') != 'queue-garden': return False
        request = urllib.request.Request('http://127.0.0.1:%d/local/show' % port, data=b'',
            headers={'X-QueueGarden-Local': '1'}, method='POST')
        with urllib.request.urlopen(request, timeout=2): return True
    except (OSError, ValueError): return False


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    if show_existing(args.port): return
    root = tk.Tk(); root.title('Queue Garden · Android connection'); root.configure(bg='#f5f3ec')
    root.geometry('455x440'); root.resizable(False, False)
    pairing, queue = Pairing(), load_queue()
    pairing.rotate()
    servers = []
    tk.Label(root, text='🌱 חיבור תורי המעבדה לאנדרואיד', bg='#f5f3ec', fg='#263e39',
             font=('Segoe UI', 17, 'bold')).pack(pady=(22, 12))
    info = tk.Label(root, text='טוען כתובת Tailscale...', bg='#f5f3ec', fg='#317b68', font=('Segoe UI', 11)); info.pack(pady=8)
    code = tk.Label(root, bg='#f5f3ec', fg='#317b68', font=('Consolas', 36, 'bold')); code.pack(pady=5)
    expires = tk.Label(root, bg='#f5f3ec', fg='#79877f', font=('Segoe UI', 10)); expires.pack()
    def rotate(): pairing.rotate()
    tk.Button(root, text='קוד חיבור חדש', command=rotate, bg='#e5eee2', fg='#263e39', relief='flat',
              font=('Segoe UI', 11), padx=16, pady=7).pack(pady=14)
    tk.Label(root, text='באפליקציה מזינים את הקוד הזה פעם אחת.\nהטלפון והמחשב צריכים להיות מחוברים ל־Tailscale.\nסגירת החלון מסתירה אותו; השיתוף נשאר פעיל.',
             bg='#f5f3ec', fg='#62766c', font=('Segoe UI', 10), justify='center').pack(pady=9)
    def stop():
        for server in servers: server.shutdown(); server.server_close()
        root.destroy()
    tk.Button(root, text='עצירת השיתוף', command=stop, bg='#f5f3ec', fg='#a15d4c', relief='flat').pack(pady=4)
    root.protocol('WM_DELETE_WINDOW', root.withdraw)
    def show(): root.after(0, lambda: (root.deiconify(), root.lift()))
    try:
        addresses = ['127.0.0.1', tail_ip()]
        for address in addresses:
            server = Server((address, args.port), pairing, queue, show)
            threading.Thread(target=server.serve_forever, daemon=True).start(); servers.append(server)
        info.config(text='http://%s:%d' % (addresses[1], args.port))
    except Exception as error:
        info.config(text='לא ניתן לפתוח שיתוף · בדוק Tailscale או שהפורט תפוס', fg='#ac5248')
        code.config(text='—')
        # No wildcard/LAN fallback and no public exposure.
        for server in servers: server.shutdown(); server.server_close()
        servers.clear()
    def tick():
        left = max(0, int(pairing.code_until - time.time()))
        if servers:
            code.config(text=pairing.code if left and pairing.code else ('—' if pairing.code else '✓'))
            expires.config(text=('תוקף הקוד: %02d:%02d' % divmod(left, 60)) if left else 'הקוד נוצל או פג · אפשר ליצור קוד חדש')
        root.after(1000, tick)
    tick(); root.mainloop()


if __name__ == '__main__': main()
