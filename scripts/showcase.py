"""Start/stop an isolated, synthetic local showcase. Never loads the development .env."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'test'])
    parser.add_argument('--port', type=int, help='Local HTTP port for this invocation (default 5184).')
    args = parser.parse_args()
    port = args.port or 5184
    if not 1024 <= port <= 65535:
        parser.error('Use an unprivileged local port between 1024 and 65535.')
    private = ROOT / 'data' / 'showcase'
    private.mkdir(parents=True, exist_ok=True)
    env = private / '.env'
    if not env.exists():
        with env.open('x', encoding='utf-8') as f:
            f.write(f'SHOWCASE_DB_PASSWORD={secrets.token_hex(32)}\n'
                    f'SHOWCASE_RUNTIME_PASSWORD={secrets.token_hex(32)}\n')
        env.chmod(0o600)
    # Each checkout has its own volumes and credentials; a clean exported copy
    # cannot accidentally reuse a working directory's database with new secrets.
    project = 'perminia-showcase-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:8]
    command = ['docker', 'compose', '--project-directory', str(ROOT),
               '--env-file', str(env), '-f', str(ROOT / 'compose.showcase.yaml'),
               '-p', project]
    operations = {
        'start': ['up', '-d', '--build', '--wait', 'api'],
        'stop': ['stop'],
        'status': ['ps'],
        'test': ['run', '--rm', '--no-deps', 'tests'],
    }
    subprocess.run(command + operations[args.action], cwd=ROOT,
                   env={**os.environ, 'SHOWCASE_PORT':str(port)}, check=True)
    if args.action == 'start':
        print(f'Showcase ready: http://localhost:{port} ({project})')
        print('Private, generated demo logins: data/showcase/accounts.json (never publish).')
        print('AI is disabled. Synthetic exercises are not Moroccan driving-law content.')


if __name__ == '__main__':
    main()
