"""Verify a restored database and archive its referenced media, without exposing rows."""
import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

from psycopg import sql
from import_dataset import connect


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


def run(output, root):
    with connect() as connection:
        database = connection.execute('SELECT current_database()').fetchone()[0]
        if not re.fullmatch(r'sya9a_student_restore_[a-f0-9]{12}', database):
            raise ValueError('Verification requires an isolated restore database')
        tables = connection.execute("""
            SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND n.nspname NOT LIKE 'pg_toast%' ORDER BY 1,2
        """).fetchall()
        counts = {}
        security = {}
        for schema, table, rls, forced in tables:
            name = f'{schema}.{table}'
            counts[name] = connection.execute(sql.SQL('SELECT count(*) FROM {}').format(
                sql.Identifier(schema, table))).fetchone()[0]
            if rls:
                security[name] = {'rls': rls, 'forced': forced}
        version = connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        assets = connection.execute("SELECT object_key,sha256 FROM content.media_assets WHERE availability='local'").fetchall()
        # These sensitive tables must remain inaccessible to the runtime role after restore.
        for table in ('identity.account_recovery', 'identity.account_access_audit'):
            if connection.execute("SELECT has_table_privilege('sya9a_student_runtime', %s, 'SELECT')", (table,)).fetchone()[0]:
                raise ValueError(f'Unexpected runtime access: {table}')
    archive = output / 'content.tar.gz'
    hashes = {}
    with tarfile.open(archive, 'x:gz') as tar:
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root)
            if relative.parts[0] == 'backups':
                continue
            if path.is_symlink():
                raise ValueError(f'Symlink not supported: {relative}')
            if path.is_file():
                with path.open('rb') as stream:
                    hashes[relative.as_posix()] = digest(stream)
                tar.add(path, arcname=relative.as_posix(), recursive=False)
    with tarfile.open(archive, 'r:gz') as tar:
        archived = {}
        for member in tar:
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe archive member')
            with tar.extractfile(member) as stream:
                archived[member.name] = digest(stream)
        if archived != hashes:
            raise ValueError('Archive bytes differ from source files')
        for key, expected in assets:
            if archived.get(key) != expected:
                raise ValueError(f'Restored database media missing or changed: {key}')
    report = {'migration': version, 'restored_table_counts': counts,
              'restored_row_security': security, 'verified_local_media_references': len(assets),
              'archived_files': len(hashes), 'media_sha256': hashes,
              'runtime_sensitive_tables_denied': True}
    (output / 'restore-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'PASS: {len(counts)} restored tables; {len(assets)} media references; {len(hashes)} archived files verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/backup'))
    parser.add_argument('--content', type=Path, default=Path('/content'))
    args = parser.parse_args()
    run(args.output, args.content)
