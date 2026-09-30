import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.database_unification import copy_legacy_workspace, merge_legacy_databases
from backend.db import Database
from backend.jira.db import db
from backend.jira.seed import seed_demo_data


class DatabaseUnificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def tearDown(self):
        db.reopen(':memory:')

    def test_legacy_domains_are_merged_into_one_physical_database(self):
        archive_source = self.root / 'archive.sqlite'
        archive = Database(archive_source)
        archive.initialize()
        archive.create_problem({
            'title': 'Migrated problem',
            'problem_statements': 'Preserve me',
        })

        jira_source = self.root / 'jira.sqlite'
        db.reopen(str(jira_source))
        seed_demo_data()

        unified_path = self.root / 'unified.sqlite'
        unified_archive = Database(unified_path)
        unified_archive.initialize()
        db.reopen(str(unified_path))

        result = merge_legacy_databases(unified_path, [archive_source, jira_source])

        self.assertIn(str(archive_source.resolve()), result)
        self.assertIn(str(jira_source.resolve()), result)
        self.assertEqual(unified_archive.count(), 1)
        self.assertEqual(unified_archive.get_problem(1)['title'], 'Migrated problem')
        self.assertGreater(db.q1('SELECT COUNT(*) AS c FROM issues')['c'], 0)
        self.assertEqual(Path(db.path).resolve(), unified_archive.path.resolve())

    def test_existing_domain_is_not_overwritten_or_duplicated(self):
        source_path = self.root / 'source.sqlite'
        source = Database(source_path)
        source.initialize()
        source.create_problem({'title': 'Source', 'problem_statements': 'source'})

        target_path = self.root / 'target.sqlite'
        target = Database(target_path)
        target.initialize()
        target.create_problem({'title': 'Target', 'problem_statements': 'target'})
        db.reopen(str(target_path))

        merge_legacy_databases(target_path, [source_path])

        self.assertEqual(target.count(), 1)
        self.assertEqual(target.get_problem(1)['title'], 'Target')

    def test_legacy_story_finish_dates_are_migrated_once_and_deadlines_preserved(self):
        legacy_path = self.root / 'legacy-dates.sqlite'
        db.reopen(str(legacy_path))
        seed_demo_data()
        stories = db.q("SELECT id FROM issues WHERE type = 'Story' LIMIT 2")
        completed_id, pending_id = (story['id'] for story in stories)
        db.run("UPDATE issues SET status = 'Done', due_date = '2026-09-27' WHERE id = ?", completed_id)
        db.run("UPDATE issues SET status = 'To Do', due_date = '2026-10-01' WHERE id = ?", pending_id)
        db.reopen(':memory:')
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute('ALTER TABLE issues DROP COLUMN finish_date')
            connection.commit()

        db.reopen(str(legacy_path))
        completed = db.q1('SELECT * FROM issues WHERE id = ?', completed_id)
        self.assertEqual(completed['finish_date'], '2026-09-27')
        self.assertEqual(completed['due_date'], '2026-09-27')
        pending = db.q1('SELECT * FROM issues WHERE id = ?', pending_id)
        self.assertIsNone(pending['finish_date'])
        self.assertEqual(pending['due_date'], '2026-10-01')

        db.run('UPDATE issues SET finish_date = NULL WHERE id = ?', completed_id)
        db.reopen(str(legacy_path))
        self.assertIsNone(db.q1('SELECT finish_date FROM issues WHERE id = ?', completed_id)['finish_date'])

    def test_legacy_workspace_copy_preserves_existing_files(self):
        source = self.root / 'old-workspace'
        target = self.root / 'new-workspace'
        (source / 'drafts').mkdir(parents=True)
        (target / 'drafts').mkdir(parents=True)
        (source / 'drafts' / 'new.py').write_text('migrated', encoding='utf-8')
        (source / 'drafts' / 'existing.py').write_text('old', encoding='utf-8')
        (target / 'drafts' / 'existing.py').write_text('new', encoding='utf-8')

        copied = copy_legacy_workspace(source, target)

        self.assertEqual(copied, 1)
        self.assertEqual((target / 'drafts' / 'new.py').read_text(encoding='utf-8'), 'migrated')
        self.assertEqual((target / 'drafts' / 'existing.py').read_text(encoding='utf-8'), 'new')


if __name__ == '__main__':
    unittest.main()
