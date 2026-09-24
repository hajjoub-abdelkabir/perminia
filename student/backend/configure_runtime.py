"""Provision only this project's restricted runtime login, after migrations."""
import os
from psycopg import sql
from import_dataset import connect
with connect() as c:
    c.execute(sql.SQL('ALTER ROLE sya9a_student_runtime PASSWORD {}').format(sql.Literal(os.environ['RUNTIME_DB_PASSWORD'])))
print('Student runtime credentials configured; secret not printed.')
