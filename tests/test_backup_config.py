import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from launcher.config import MinecraftConfig


class BackupConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'config.json'
        self.data = dict(
            minecraft_version='test', fabric_loader_version='test',
            fabric_installer_version='test', memory_size='1G', mods=[],
            backup=dict(periodic=True, period='* * * * *', max=10),
        )

    def read(self):
        self.path.write_text(json.dumps(self.data))
        return MinecraftConfig.from_json(self.path)

    def test_nested_settings_are_parsed(self):
        backup = self.read().backup
        self.assertIs(backup.periodic_enabled, True)
        self.assertEqual(backup.cron_expression, '* * * * *')
        self.assertEqual(backup.max_backups, 10)

    def test_disabled_settings_allow_unused_expression_and_one_archive(self):
        self.data['backup'] = dict(periodic=False, period='unused', max=1)
        backup = self.read().backup
        self.assertIs(backup.periodic_enabled, False)
        self.assertEqual(backup.cron_expression, 'unused')
        self.assertEqual(backup.max_backups, 1)

    def test_missing_backup_is_actionable(self):
        del self.data['backup']
        with self.assertRaisesRegex(ValueError, 'backup'):
            self.read()

    def test_backup_must_be_object(self):
        for value in (None, [], 'backup', 1, False):
            with self.subTest(value=value):
                self.data['backup'] = value
                with self.assertRaisesRegex(ValueError, 'backup'):
                    self.read()

    def test_nested_keys_are_required(self):
        for key in ('periodic', 'period', 'max'):
            with self.subTest(key=key):
                self.data['backup'] = dict(periodic=True, period='* * * * *', max=10)
                del self.data['backup'][key]
                with self.assertRaisesRegex(ValueError, rf'backup\.{key}'):
                    self.read()

    def test_unknown_key_is_rejected(self):
        self.data['backup']['maximum'] = 10
        with self.assertRaisesRegex(ValueError, r'backup\.maximum'):
            self.read()

    def test_invalid_types_and_values_name_the_setting(self):
        cases = {
            'periodic': ('false', 0, None),
            'period': ('', '   ', 10, None, False),
            'max': (0, -1, 1.5, '10', True, None),
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.data['backup'] = dict(periodic=True, period='* * * * *', max=10)
                    self.data['backup'][key] = value
                    with self.assertRaisesRegex(ValueError, rf'backup\.{key}'):
                        self.read()

    def test_legacy_setting_is_rejected_even_alongside_new_settings(self):
        self.data['backup_period'] = 1
        for mixed in (True, False):
            with self.subTest(mixed=mixed):
                if not mixed:
                    del self.data['backup']
                with self.assertRaisesRegex(ValueError, 'backup_period is no longer supported'):
                    self.read()
