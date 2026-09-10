"""Launch local auth API with credentials from ignored, private local configuration."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure(owner=False):
    config = json.loads((ROOT / '.local/database.json').read_text())
    user = 'queuesense_owner' if owner else 'queuesense_auth'
    password = config['owner_password'] if owner else config['runtime_password']
    return f"postgresql://{user}:{password}@127.0.0.1:{config['port']}/queuesense"


def main():
    os.environ['DATABASE_URL'] = configure()
    os.environ.setdefault('ENABLE_DEMO_LOGIN', 'true')
    os.environ.setdefault('FRONTEND_ORIGINS', 'http://127.0.0.1:3001,http://localhost:3001')
    import uvicorn
    uvicorn.run('backend.app:create_app', factory=True, host='127.0.0.1', port=8001, proxy_headers=False)


if __name__ == '__main__':
    main()
