"""Start the existing local QueueSense installation without replacing unrelated processes."""
import json
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


def main():
    if not PYTHON.exists():raise SystemExit('Install backend dependencies first; see README.md.')
    subprocess.run([str(PYTHON),'-m','backend.local_setup'],cwd=ROOT,check=True)
    subprocess.run([str(PYTHON),'-m','backend.bootstrap_product'],cwd=ROOT,check=True)
    jobs=[('api','http://127.0.0.1:8001/health',[str(PYTHON),'-m','backend.local_run'],ROOT),('web','http://127.0.0.1:3001',['npm','run','start','--','--port','3001'],ROOT/'frontend')]
    for name,url,command,cwd in jobs:
        if probe(url):print(name+': already responding');continue
        if name=='web' and not (ROOT/'frontend/.next/BUILD_ID').exists():subprocess.run(['npm','run','build'],cwd=cwd,check=True)
        with (ROOT/'.local'/f'{name}.log').open('a') as log:
            process=subprocess.Popen(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (ROOT/'.local'/f'{name}.pid').write_text(str(process.pid))
        for _ in range(30):
            if probe(url):break
            if process.poll() is not None:raise SystemExit(f'{name} exited; inspect .local/{name}.log (possibly a port conflict).')
            time.sleep(1)
        else:raise SystemExit(f'{name} did not become ready; inspect its log.')
        print(name+': ready')
    print('QueueSense: http://127.0.0.1:3001')


if __name__=='__main__':main()
