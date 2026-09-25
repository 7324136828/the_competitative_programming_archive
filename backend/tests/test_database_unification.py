import tempfile
import unittest
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
