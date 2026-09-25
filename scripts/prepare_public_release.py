"""Build an allowlisted GitHub handoff; never export the working directory wholesale.

No remote is created, no files are uploaded, and no Git commands are executed.
The scanner is a release guard, not a guarantee against every possible secret format.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('README.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md', '.gitignore', '.dockerignore',
              '.env.example', 'compose.showcase.yaml', 'Dockerfile.showcase')
SCRIPT_FILES = ('showcase.py', 'prepare_public_release.py', 'check_static_demo.py')
TREES = ('student/backend', 'student/frontend', 'docs/public', '.github')
SKIP_PARTS = {'node_modules', 'dist', '__pycache__', '.pytest_cache', '.venv', '.git'}
SOURCE_SUFFIXES = {'.py','.sql','.ini','.txt','.lock','.json','.js','.jsx','.mjs','.css','.html',
                   '.md','.svg','.png','.yml','.yaml'}
SIGNATURES = (
    re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}'),
    re.compile(rb'\bgsk_[A-Za-z0-9]{30,}'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
)


def candidates(root=ROOT):
    selected = [root/name for name in ROOT_FILES]
    selected += [root/'scripts'/name for name in SCRIPT_FILES]
    for tree in TREES:
        for path in (root/tree).rglob('*'):
            if not path.is_file() or any(p in SKIP_PARTS for p in path.relative_to(root).parts):
                continue
            if path.name.startswith('.env') or path.suffix in {'.log','.dump','.zip','.mp4','.mp3'}:
                continue
            if path.suffix in SOURCE_SUFFIXES or path.name in {'Dockerfile','.dockerignore','.gitignore'}:
                selected.append(path)
    return sorted(set(selected))


def local_secrets():
    values = []
    for env in (ROOT/'.env', ROOT/'data/showcase/.env'):
        if env.is_file():
            for line in env.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                value = value.strip().strip('"').strip("'")
                if sep and any(word in key.upper() for word in ('PASSWORD','SECRET','API_KEY','TOKEN')) and len(value) >= 16:
                    values.append(value.encode())
    for private in (ROOT/'data/demo', ROOT/'data/showcase'):
        if private.exists():
            for file in private.glob('*.json'):
                try:
                    data = json.loads(file.read_text(encoding='utf-8-sig'))
                    for account in data.get('accounts', []):
                        if len(account.get('password','')) >= 12:
                            values.append(account['password'].encode())
                except (ValueError, AttributeError, TypeError):
                    continue
    return values


def audit(files, root=ROOT):
    secrets = local_secrets()
    failures = []
    manifest = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            failures.append(relative+': missing file or symlink')
            continue
        payload = path.read_bytes()
        if len(payload) > 5_000_000:
            failures.append(relative+': exceeds source-package size limit')
        if any(pattern.search(payload) for pattern in SIGNATURES) or any(value in payload for value in secrets):
            failures.append(relative+': possible secret; value withheld')
        manifest.append({'path':relative,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
    if failures:
        raise SystemExit('Release blocked:\n'+'\n'.join(failures))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Audit publishable source without copying.')
    args = parser.parse_args()
    files = candidates()
    manifest = audit(files)
    if args.check:
        print(f'PASS: {len(files)} allowlisted source files checked; no matched secret signatures or known local credentials.')
        return
    destination = ROOT/'release'/'perminia-github'
    if destination.exists():
        raise SystemExit('Release directory already exists. No files overwritten; keep it as a snapshot or rename it before rebuilding.')
    destination.mkdir(parents=True)
    for path in files:
        target = destination/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    (destination/'PUBLIC_RELEASE_MANIFEST.json').write_text(json.dumps({'kind':'synthetic-technical-MVP','files':manifest},indent=2), encoding='utf-8')
    print(f'Prepared {len(files)} checked files in {destination}')
    print('Excluded: .env, private data, imports, backups, internal reports, screenshots and prototype.')


if __name__ == '__main__':
    main()
