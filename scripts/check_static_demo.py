"""Fail a static-demo release if it accidentally bundles backend/local endpoints."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'student/frontend/dist'
if not (root / 'index.html').is_file():
    raise SystemExit('Build the static demo first: npm run build:demo')
files = list(root.rglob('*.js'))
if not files:
    raise SystemExit('No JavaScript build assets found.')
for path in files:
    body = path.read_text(encoding='utf-8')
    for value in ('/api/v1', 'localhost:', '127.0.0.1:', 'api.openai.com', 'api.groq.com'):
        if value in body:
            raise SystemExit(f'Static-demo boundary failed in {path.name}: {value}')
print(f'PASS: {len(files)} JavaScript assets contain no backend, localhost or AI-provider endpoints.')
