import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backup_media import run


class BackupTests(unittest.TestCase):
    def connection(self, database, expected):
        connection = MagicMock()
        def execute(query, params=None):
            result = MagicMock()
            if query == 'SELECT current_database()':
                result.fetchone.return_value = (database,)
            elif isinstance(query, str) and 'FROM pg_class' in query:
                result.fetchall.return_value = [('public', 'alembic_version', False, False)]
            elif query == 'SELECT version_num FROM alembic_version':
                result.fetchone.return_value = ('0015_account_recovery',)
            elif isinstance(query, str) and 'FROM content.media_assets' in query:
                result.fetchall.return_value = [('lessons/example.svg', expected)]
            elif isinstance(query, str) and 'has_table_privilege' in query:
                result.fetchone.return_value = (False,)
            else:
                result.fetchone.return_value = (1,)
            return result
        connection.execute.side_effect = execute
        context = MagicMock()
        context.__enter__.return_value = connection
        return context

    def exercise(self, database='sya9a_student_restore_123456abcdef', expected=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'content'
            output = Path(temporary) / 'backup'
            (root / 'lessons').mkdir(parents=True)
            (root / 'backups').mkdir()
            (root / 'backups' / 'old.dump').write_bytes(b'exclude old backup')
            (root / 'lessons' / 'example.svg').write_bytes(b'<svg/>')
            output.mkdir()
            expected = expected or hashlib.sha256(b'<svg/>').hexdigest()
            with patch('backup_media.connect', return_value=self.connection(database, expected)):
                run(output, root)
            report = json.loads((output / 'restore-report.json').read_text())
            self.assertEqual(report['archived_files'], 1)
            self.assertEqual(report['verified_local_media_references'], 1)

    def test_restored_media_verified_and_prior_backups_excluded(self):
        self.exercise()

    def test_live_database_rejected(self):
        with self.assertRaisesRegex(ValueError, 'isolated restore'):
            self.exercise(database='sya9a_student')

    def test_mismatching_media_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            self.exercise(expected='0' * 64)


if __name__ == '__main__':
    unittest.main()
