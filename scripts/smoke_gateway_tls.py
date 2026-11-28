"""Exercise the integration ingress using local synthetic gateway credentials."""
import argparse
import json
import os
import secrets
import ssl
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from time import sleep, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(__file__).resolve().parents[1]
label = 'qs-gateway-' + uuid4().hex[:8]
pg, api, signer, nginx = (label + '-' + part for part in ('db', 'api', 'keys', 'tls'))
path = '/api/integrations/v1/wait-time-summary'
dept = str(uuid4())
issuer, audience, context = 'local-fixture-issuer', 'queue-gateway-local', '/fixture/proxy/1.0'
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
kid = 'synthetic-gateway'


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, **kw)


def docker(*cmd, **kw):
    return run('docker', *cmd, **kw)


def certificates(folder):
    def openssl(*args):
        run('openssl', *args, cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj',
            '/CN=Local Gateway Fixture', '-keyout', 'ca.key', '-out', 'ca.pem')
    for item in ('origin', 'client'):
        openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=' + item,
                '-keyout', f'{item}.key', '-out', f'{item}.csr')
        (folder / 'ext.txt').write_text(
            'subjectAltName=IP:127.0.0.1,DNS:signer\nextendedKeyUsage=serverAuth\n'
            if item == 'origin' else 'extendedKeyUsage=clientAuth\n')
        openssl('x509', '-req', '-in', f'{item}.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
                '-CAcreateserial', '-days', '1', '-extfile', 'ext.txt', '-out', f'{item}.pem')
    (folder / 'origin-key.pem').write_bytes((folder / 'origin.key').read_bytes())
    (folder / 'origin-fullchain.pem').write_bytes((folder / 'origin.pem').read_bytes())
    (folder / 'choreo-client-trust.pem').write_bytes((folder / 'ca.pem').read_bytes())


def wait_for(fn):
    for _ in range(55):
        try:
            value = fn()
            if value:
                return value
        except (OSError, URLError):
            pass
        sleep(.25)
    raise RuntimeError('A local fixture did not become available')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Local image built from backend/Dockerfile')
    image = parser.parse_args().image

    try:
        docker('network', 'create', label, stdout=subprocess.DEVNULL)
        with TemporaryDirectory(prefix='qs11-') as temp:
            folder = Path(temp)
            certificates(folder)
            password = secrets.token_urlsafe(24)
            env = folder / 'postgres.env'
            env.touch(mode=0o600)
            env.write_text(f'POSTGRES_PASSWORD={password}\nPOSTGRES_DB=queuesense\n')
            docker('run', '-d', '--name', pg, '--network', label, '--env-file', str(env),
                   'postgres:17', stdout=subprocess.DEVNULL)
            wait_for(lambda: subprocess.run(
                ['docker', 'exec', pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'queuesense'],
                capture_output=True).returncode == 0)
            runtime_password = secrets.token_urlsafe(24)
            schema = f"CREATE ROLE queuesense_auth LOGIN PASSWORD '{runtime_password}';\n"
            schema += '\n'.join(p.read_text() for p in sorted((root / 'database/migrations').glob('*.sql')))
            schema += '\n' + '\n'.join(
                (root / f'database/sql/{role}_runtime_grants.sql').read_text()
                for role in ('auth', 'product')
            )
            schema += f'''
            INSERT INTO departments(id,code,name,location)
            VALUES ('{dept}','TLS','Synthetic TLS clinic','Test only');
            '''
            docker('exec', '-i', pg, 'psql', '-U', 'postgres', '-d', 'queuesense', '-q',
                   '-v', 'ON_ERROR_STOP=1', input=schema, stdout=subprocess.DEVNULL)
            public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
            public_jwk.update(kid=kid, alg='RS256', use='sig')
            (folder/'jwks.json').write_text(json.dumps({'keys': [public_jwk]}))
            (folder/'jwks.py').write_text(dedent("""
    import ssl
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path
    class Keys(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/.wellknown/jwks':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(Path('/fixture/jwks.json').read_bytes())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/fixture/origin-fullchain.pem','/fixture/origin-key.pem')
    service = HTTPServer(('0.0.0.0', 443), Keys)
    service.socket = context.wrap_socket(service.socket, server_side=True)
    service.serve_forever()
    """))
            os.chmod(folder, 0o755)
            docker('run', '-d', '--name', signer, '--network', label, '--network-alias', 'signer', '--user', '0',
                   '-v', f'{folder}:/fixture:ro', image, 'python', '/fixture/jwks.py', stdout=subprocess.DEVNULL)
            runtime = folder / 'runtime.env'
            runtime.touch(mode=0o600)
            runtime.write_text(
                f'DATABASE_URL=postgresql://queuesense_auth:{runtime_password}@{pg}:5432/queuesense\n'
                f'JWT_SIGNING_SECRET={secrets.token_urlsafe(32)}\nAPP_ENV=production\n'
                'FRONTEND_ORIGINS=https://clinic.example.invalid\nENABLE_AUTOMATION=false\n'
                f'CHOREO_JWKS_URL=https://signer/.wellknown/jwks\nCHOREO_ASSERTION_ISSUER={issuer}\n'
                f'CHOREO_ASSERTION_AUDIENCE={audience}\nCHOREO_ASSERTION_CONTEXT={context}\n'
                f'CHOREO_DEPARTMENT_ID={dept}\nSSL_CERT_FILE=/fixture/ca.pem\n'
            )
            docker('run', '-d', '--name', api, '--network', label, '--network-alias', 'api',
                   '--env-file', str(runtime), '-v', f'{folder / "ca.pem"}:/fixture/ca.pem:ro',
                   image, stdout=subprocess.DEVNULL)
            def health():
                result = subprocess.run(['docker', 'exec', api, 'python', '-c',
                    'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=2).read().decode())'],
                    text=True, capture_output=True)
                return result.returncode == 0 and json.loads(result.stdout) == {'status': 'ok'}
            wait_for(health)
            docker('run', '-d', '--name', nginx, '--network', label, '-p', '127.0.0.1::443',
                   '-v', f'{folder}:/etc/queuesense/tls:ro',
                   '-v', f'{root / "api-management/integration-ingress.conf"}:/etc/nginx/conf.d/default.conf:ro',
                   'nginx:stable-alpine', stdout=subprocess.DEVNULL)
            port = int(docker('port', nginx, '443/tcp', capture_output=True).stdout.strip().rsplit(':', 1)[1])
            trust = ssl.create_default_context(cafile=str(folder/'ca.pem'))
            mtls = ssl.create_default_context(cafile=str(folder/'ca.pem'))
            mtls.load_cert_chain(str(folder/'client.pem'), str(folder/'client.key'))
            epoch = int(time())
            signed = jwt.encode(
                {'iss': issuer, 'aud': audience, 'iat': epoch, 'exp': epoch + 180,
                 'jti': str(uuid4()), 'http://wso2.org/claims/apicontext': context},
                key, algorithm='RS256', headers={'kid': kid},
            )
            def call(route, tls, headers=None, method='GET'):
                try:
                    with urlopen(Request(f'https://127.0.0.1:{port}'+route, headers=headers or {}, method=method),
                                 context=tls, timeout=8) as response:
                        return response.status, response.headers, json.load(response)
                except HTTPError as response:
                    return response.status, response.headers, response.read().decode()
            query = path + f'?department_id={dept}&week_start=2026-11-02'
            assert wait_for(lambda: call(query, mtls)[0]) == 401
            assert call(query, mtls, {'X-JWT-Assertion': 'invalid.synthetic.jwt'})[0] == 401
            assert call(query, trust)[0] >= 400
            assert call('/health', mtls)[0] == 404
            assert call(query, mtls, method='POST')[0] == 405
            status, headers, body = call(query, mtls, {'X-JWT-Assertion': signed})
            assert status == 200, (status, body)
            assert headers['X-Request-ID'] and headers['Cache-Control'] == 'no-store'
            assert body['data'] == {'department_id': dept, 'week_start': '2026-11-02', 'suppressed': True, 'metrics': None}
            docker('stop', api, stdout=subprocess.DEVNULL)
            unavailable = call(query, mtls, {'X-JWT-Assertion': signed})[0]
            assert unavailable in (502, 504), unavailable
            docker('start', api, stdout=subprocess.DEVNULL)
            assert wait_for(lambda: call(query, mtls, {'X-JWT-Assertion': signed})[0] == 200)
            for _ in range(62):
                status, headers, _ = call(query, mtls, {'X-JWT-Assertion': signed})
                if status == 429:
                    assert int(headers['Retry-After']) > 0 and headers['X-Request-ID']
                    print('PASS: origin quota 429, Retry-After and correlation passed through HTTPS ingress.')
                    break
                assert status == 200
            else:
                raise AssertionError('Origin quota did not reject requests in the synthetic test')
            print(f'PASS: private health, HTTPS/mTLS, actual JWKS verification, exact route and method, upstream outage {unavailable} and recovery.')
    finally:
        subprocess.run(['docker', 'rm', '-fv', nginx, api, signer, pg], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', label], capture_output=True)


if __name__ == '__main__':
    main()
