"""Runtime smoke test: readiness and least-privilege access, without mutations."""
import urllib.request
from sqlalchemy import text
from app.db import engine
with urllib.request.urlopen('http://api:8000/api/v1/health/ready', timeout=5) as response:
    assert response.status == 200
with engine.connect() as c:
    assert c.execute(text('SELECT current_user')).scalar_one() == 'sya9a_student_runtime'
    assert not c.execute(text("SELECT has_table_privilege(current_user,'content.answer_keys','SELECT')")).scalar_one()
    assert c.execute(text('SELECT count(*) FROM learning.attempts')).scalar_one() == 0
print('PASS: runtime readiness, private answer keys and deny-by-default learner scope')
