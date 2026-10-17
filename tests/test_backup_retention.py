import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from launcher.backup_retention import prune_backups


class BackupRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.old = self.archive('world-backup-20261015-120000.zip', 100)
        self.middle = self.archive('world-backup-20261016-120000-000001.zip', 200)
        self.new = self.archive('world-backup-20261017-120000-000001.zip', 300)

    def archive(self, name, mtime):
        path = self.directory / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('level.dat', name)
        os.utime(path, ns=(mtime, mtime))
        return path

    def prune(self, limit, newest=None):
        return prune_backups(self.directory, max_backups=limit, newest_backup=newest or self.new)

    def test_removes_only_oldest_excess_backup(self):
        self.assertEqual(self.prune(2), [self.old])
        self.assertFalse(self.old.exists())
        self.assertTrue(self.middle.exists())
        self.assertTrue(self.new.exists())

    def test_limit_one_preserves_only_newly_saved_archive(self):
        self.assertEqual(self.prune(1), [self.old, self.middle])
        self.assertEqual(set(self.directory.iterdir()), {self.new})

    def test_at_or_below_limit_leaves_all_archives(self):
        for limit in (3, 10):
            with self.subTest(limit=limit):
                self.assertEqual(self.prune(limit), [])
                self.assertEqual(set(self.directory.iterdir()), {self.old, self.middle, self.new})

    def test_removes_all_excess_in_one_rotation(self):
        for day in range(1, 10):
            self.archive(f'world-backup-202610{day:02}-120000.zip', day)
        self.assertEqual(len(self.prune(2)), 10)
        self.assertEqual(set(self.directory.iterdir()), {self.middle, self.new})

    def test_new_archive_is_protected_when_its_mtime_is_oldest(self):
        os.utime(self.new, ns=(1, 1))
        self.assertEqual(self.prune(2), [self.old])
        self.assertEqual(set(self.directory.iterdir()), {self.middle, self.new})

    def test_equal_mtimes_use_filename_order(self):
        os.utime(self.old, ns=(200, 200))
        self.assertEqual(self.prune(2), [self.old])

    def test_ignores_unrelated_partial_invalid_directories_and_symlinks(self):
        ignored = [
            self.archive('other.zip', 1),
            self.archive('world-backup-20261014-120000.zip.part', 1),
            self.archive('world-backup-20260230-120000.zip', 1),
            self.archive('world-backup-20261014-250000.zip', 1),
            self.archive('world-backup-20261014-120000-1.zip', 1),
        ]
        directory = self.directory / 'world-backup-20261013-120000.zip'
        directory.mkdir()
        link = self.directory / 'world-backup-20261012-120000.zip'
        link.symlink_to(ignored[0])
        self.prune(1)
        self.assertEqual(set(self.directory.iterdir()), {*ignored, directory, link, self.new})
        self.assertTrue(link.is_symlink())

    def test_invalid_limits_never_delete(self):
        for limit in (0, -1, True, 1.5, '1', None):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    self.prune(limit)
                self.assertEqual(set(self.directory.iterdir()), {self.old, self.middle, self.new})

    def test_invalid_protected_path_never_deletes(self):
        unrelated = self.archive('unrelated.zip', 1)
        directory = self.directory / 'world-backup-20261013-120000.zip'
        directory.mkdir()
        link = self.directory / 'world-backup-20261012-120000.zip'
        link.symlink_to(self.new)
        paths = [self.directory / 'world-backup-20261011-120000.zip', unrelated,
                 self.directory.parent / self.new.name, directory, link]
        original = set(self.directory.iterdir())
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.prune(1, path)
                self.assertEqual(set(self.directory.iterdir()), original)

    def test_disappearing_old_file_is_tolerated(self):
        unlink = Path.unlink

        def disappear(path, *args, **kwargs):
            unlink(path, *args, **kwargs)
            if path == self.old:
                raise FileNotFoundError(path)

        with patch.object(Path, 'unlink', disappear):
            self.prune(1)
        self.assertEqual(set(self.directory.iterdir()), {self.new})

    def test_delete_failure_reports_saved_and_failed_paths(self):
        with patch.object(Path, 'unlink', side_effect=PermissionError('denied')):
            with self.assertRaises(OSError) as raised:
                self.prune(1)
        self.assertIn(str(self.new), str(raised.exception))
        self.assertIn(str(self.old), str(raised.exception))
        self.assertIn('retention failed', str(raised.exception))
        with zipfile.ZipFile(self.new) as archive:
            self.assertEqual(archive.read('level.dat').decode(), self.new.name)
