"""Start the existing local QueueSense installation without replacing unrelated processes."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/'.venv/bin/python'


def probe(url):
    try:
        with urllib.request.urlopen(url,timeout=3) as response:return response.status==200
    except (urllib.error.URLError,TimeoutError):return False


def lan_ipv4():
    """Return the active outbound interface address without sending traffic."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 80))
            address=sock.getsockname()[0]
            return address if not address.startswith('127.') else None
    except OSError:
        return None


def main():
    if not PYTHON.exists():raise SystemExit('Install backend dependencies first; see README.md.')
    env=os.environ.copy()
    env.setdefault('APP_HOST','127.0.0.1')
    env.setdefault('APP_PORT','8001')
    origins={origin.strip().rstrip('/') for origin in env.get('FRONTEND_ORIGINS','').split(',') if origin.strip()}
    origins.update(('http://127.0.0.1:3001','http://localhost:3001'))
    address=lan_ipv4()
    if address:origins.add(f'http://{address}:3001')
    env['FRONTEND_ORIGINS']=','.join(sorted(origins))
    subprocess.run([str(PYTHON),'-m','backend.local_setup'],cwd=ROOT,env=env,check=True)
    subprocess.run([str(PYTHON),'-m','backend.bootstrap_product'],cwd=ROOT,env=env,check=True)
    jobs=[('api','http://127.0.0.1:8001/health',[str(PYTHON),'-m','backend.local_run'],ROOT),('web','http://127.0.0.1:3001',['npm','run','start','--','--port','3001'],ROOT/'frontend')]
    for name,url,command,cwd in jobs:
        if probe(url):print(name+': already responding');continue
        if name=='web' and not (ROOT/'frontend/.next/BUILD_ID').exists():subprocess.run(['npm','run','build'],cwd=cwd,check=True)
        with (ROOT/'.local'/f'{name}.log').open('a') as log:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/'.local'/f'{name}.pid').write_text(str(process.pid))
        for _ in range(30):
            if probe(url):break
            if process.poll() is not None:raise SystemExit(f'{name} exited; inspect .local/{name}.log (possibly a port conflict).')
            time.sleep(1)
        else:raise SystemExit(f'{name} did not become ready; inspect its log.')
        print(name+': ready')
    print('QueueSense: http://127.0.0.1:3001')
    if address:print(f'LAN access: http://{address}:3001 (other devices must be on the same network)')


if __name__=='__main__':main()
