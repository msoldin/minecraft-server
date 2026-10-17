import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HELPERS = Path(__file__).resolve().parent / "helpers"
sys.path.insert(0, str(ROOT / "scripts"))

from launcher.config import BackupConfig, MinecraftConfig, SystemConfig
from launcher import modrinth
from launcher.world_backup_manager import WorldBackupManager


# Substitute only Java and downloads: the launcher, signal handlers, subprocess
# lifecycle, scheduler and ZIP creation all run as they do in the container.
class ShutdownIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = json.loads((ROOT / 'config.json').read_text())
        self.console_writer = None
        java = self.base / 'java'
        java.write_text(f'#!{sys.executable}\n' + (HELPERS / 'fake_java.py').read_text())
        java.chmod(0o755)

    def launch(self, *, wait_ready=True, **env):
        (self.base / 'config.json').write_text(json.dumps(self.config))
        self.log = (self.base / 'launcher.log').open('w+')
        self.addCleanup(self.log.close)
        self.proc = subprocess.Popen(
            [sys.executable, '-u', str(HELPERS / 'run_launcher.py'), str(ROOT)],
            env={**os.environ, 'PATH': f'{self.base}:{os.environ["PATH"]}',
                 'TEST_DATA': str(self.base), **env},
            stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(self.cleanup_processes)
        if wait_ready:
            self.wait_for('ready')

    def seed_old_backups(self, count):
        directory = self.base / 'backups'
        directory.mkdir()
        paths = []
        for day in range(1, count + 1):
            path = directory / f'world-backup-202601{day:02}-120000.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('level.dat', b'old world')
            os.utime(path, ns=(day, day))
            paths.append(path)
        return paths

    def cleanup_processes(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=5)
        if self.console_writer is not None:
            self.console_writer.join(timeout=1)
        self.proc.stdin.close()
        pid_file = self.base / 'java.pid'
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def logs(self):
        self.log.seek(0)
        return self.log.read()

    def send_console_in_background(self, data):
        def write_console():
            try:
                remaining = memoryview(data)
                while remaining:
                    written = os.write(self.proc.stdin.fileno(), remaining)
                    remaining = remaining[written:]
            except BrokenPipeError:
                pass

        self.console_writer = threading.Thread(target=write_console, daemon=True)
        self.console_writer.start()

    def wait_for(self, name):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (self.base / name).exists():
                return
            if self.proc.poll() is not None:
                break
            time.sleep(0.01)
        self.fail(f'{name} was not created:\n{self.logs()}')

    def assert_backup(self, expected):
        archives = list((self.base / 'backups').glob('*.zip'))
        self.assertEqual(len(archives), 1, self.logs())
        with zipfile.ZipFile(archives[0]) as archive:
            self.assertEqual(archive.read('level.dat'), expected)
        self.assertFalse(list((self.base / 'backups').glob('*.part')))

    def check_shutdown(self, sig):
        self.launch()
        self.proc.send_signal(sig)
        self.wait_for('stopping')
        self.proc.send_signal(sig)  # Repeated signals must not interrupt cleanup.
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_sigterm_waits_for_save_then_backs_up_without_rcon(self):
        self.check_shutdown(signal.SIGTERM)

    def test_sigint_waits_for_save_then_backs_up_without_rcon(self):
        self.check_shutdown(signal.SIGINT)

    def test_server_exit_also_triggers_backup_and_preserves_failure(self):
        self.launch(SERVER_EXIT='7')
        self.assertEqual(self.proc.wait(timeout=5), 7, self.logs())
        self.assert_backup(b'before shutdown')

    def test_exit_only_ignores_unused_cron_and_stays_alive_across_boundaries(self):
        self.config['backup'].update(periodic=False, period='unused invalid expression')
        self.launch(ADVANCE_CLOCK='1')
        self.wait_for('clock-advanced')
        self.assertIsNone(self.proc.poll(), self.logs())
        self.assertFalse((self.base / 'backups').exists())
        self.assertFalse((self.base / 'rcon-used').exists())
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_disabled_periodic_backups_still_archive_unexpected_server_exit(self):
        self.config['backup']['periodic'] = False
        self.launch(SERVER_EXIT='7')
        self.assertEqual(self.proc.wait(timeout=5), 7, self.logs())
        self.assert_backup(b'before shutdown')

    def test_exit_backup_rotates_only_after_shutdown_save(self):
        self.config['backup'].update(periodic=False, max=1)
        old_paths = self.seed_old_backups(2)
        self.launch()
        self.assertEqual(set((self.base / 'backups').iterdir()), set(old_paths))
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')
        self.assertTrue(all(not path.exists() for path in old_paths))

    def test_active_and_exit_backups_share_one_retention_limit(self):
        self.config['backup']['max'] = 2
        old_paths = self.seed_old_backups(3)
        self.launch(ACTIVE_BACKUP='1')
        self.wait_for('backup-active')
        self.proc.send_signal(signal.SIGTERM)
        (self.base / 'release-backup').touch()
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assertTrue(all(not path.exists() for path in old_paths))
        contents = []
        for path in (self.base / 'backups').glob('*.zip'):
            with zipfile.ZipFile(path) as archive:
                contents.append(archive.read('level.dat'))
        self.assertCountEqual(contents, [b'before shutdown', b'saved on shutdown'])

    def test_invalid_enabled_schedule_fails_before_java_starts(self):
        self.config['backup']['period'] = '0 0 31 2 *'
        self.launch(wait_ready=False)
        self.assertNotEqual(self.proc.wait(timeout=5), 0)
        self.assertIn('backup.period', self.logs())
        self.assertFalse((self.base / 'ready').exists())
        self.assertFalse((self.base / 'world').exists())

    def test_exit_retention_failure_preserves_saved_archive_and_returns_failure(self):
        self.config['backup'].update(periodic=False, max=1)
        old = self.seed_old_backups(1)[0]
        self.launch(FAIL_RETENTION='1')
        self.proc.send_signal(signal.SIGTERM)
        self.assertNotEqual(self.proc.wait(timeout=5), 0)
        self.assertIn('retention failed', self.logs())
        self.assertIn('Backup saved at', self.logs())
        archives = set((self.base / 'backups').glob('*.zip'))
        self.assertEqual(len(archives), 2)
        with zipfile.ZipFile((archives - {old}).pop()) as archive:
            self.assertEqual(archive.read('level.dat'), b'saved on shutdown')

    def test_console_commands_still_reach_minecraft(self):
        self.launch()
        self.proc.stdin.write('say hello\n')
        self.proc.stdin.flush()
        self.wait_for('console-command')
        self.assertEqual((self.base / 'console-command').read_text(), 'say hello\n')
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())

    def test_final_backup_failure_is_reported_as_failure(self):
        self.launch()
        (self.base / 'backups').write_text('not a directory')
        self.proc.send_signal(signal.SIGTERM)
        self.assertNotEqual(self.proc.wait(timeout=5), 0)
        self.assertEqual((self.base / 'world/level.dat').read_text(), 'saved on shutdown')
        self.assertIn('backup', self.logs().lower())

    def test_closed_server_stdin_still_waits_and_creates_final_backup(self):
        self.launch(CLOSE_STDIN='1')
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_full_console_pipe_does_not_block_shutdown_or_final_backup(self):
        self.launch(STALL_STDIN='1')
        self.send_console_in_background(b'say hello\n' * 100000)
        self.wait_for('console-full')
        self.proc.send_signal(signal.SIGTERM)
        try:
            returncode = self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.fail('Shutdown blocked behind the full console pipe')
        self.assertEqual(returncode, 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_console_preserves_input_after_a_full_pipe_becomes_writable(self):
        self.launch(PAUSE_STDIN='1')
        command = 'say ' + 'x' * 100000 + '\n'
        self.send_console_in_background(command.encode())
        self.wait_for('console-full')
        (self.base / 'release-console').touch()
        self.wait_for('console-command')
        self.console_writer.join(timeout=1)
        self.assertEqual((self.base / 'console-command').read_text(), command)
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_repeated_signals_do_not_interrupt_final_archive(self):
        self.launch(SLOW_FINAL_BACKUP='1')
        self.proc.send_signal(signal.SIGTERM)
        self.wait_for('final-backup-active')
        self.proc.send_signal(signal.SIGTERM)
        self.proc.send_signal(signal.SIGINT)
        time.sleep(0.1)
        self.assertIsNone(self.proc.poll(), self.logs())
        self.assertFalse(list((self.base / 'backups').glob('*.zip')))
        (self.base / 'release-final-backup').touch()
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assert_backup(b'saved on shutdown')

    def test_signal_during_live_backup_finishes_it_before_stopping_server(self):
        self.launch(ACTIVE_BACKUP='1')
        self.wait_for('backup-active')
        self.proc.send_signal(signal.SIGTERM)
        time.sleep(0.1)
        self.assertFalse((self.base / 'stopping').exists())
        (self.base / 'release-backup').touch()
        self.assertEqual(self.proc.wait(timeout=5), 0, self.logs())
        self.assertTrue((self.base / 'saving-restored').exists())
        contents = []
        for archive in (self.base / 'backups').glob('*.zip'):
            with zipfile.ZipFile(archive) as zip_file:
                contents.append(zip_file.read('level.dat'))
        self.assertCountEqual(contents, [b'before shutdown', b'saved on shutdown'])


class BackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.world = self.base / 'world'
        self.world.mkdir()
        (self.world / 'level.dat').write_bytes(b'world data')
        self.system = SystemConfig(self.base, self.base / 'mods', self.base / 'server',
                              self.base / 'config.json', self.base / 'backups')
        self.manager = WorldBackupManager(self.system, schedule=None, max_backups=10)

    def test_failed_write_preserves_existing_backup(self):
        self.manager = WorldBackupManager(self.system, schedule=None, max_backups=1)
        existing = self.manager.backup_stopped_world()
        with patch.object(zipfile.ZipFile, 'write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.backup_stopped_world()
        self.assertEqual(list(self.system.backup_path.iterdir()), [existing])

    def test_failed_publication_preserves_existing_backup(self):
        self.manager = WorldBackupManager(self.system, schedule=None, max_backups=1)
        existing = self.manager.backup_stopped_world()
        with patch.object(Path, 'replace', side_effect=OSError('rename failed')):
            with self.assertRaises(OSError):
                self.manager.backup_stopped_world()
        self.assertEqual(list(self.system.backup_path.iterdir()), [existing])

    def test_exit_backups_enforce_shared_limit_after_publication(self):
        self.manager = WorldBackupManager(self.system, schedule=None, max_backups=1)
        existing = self.manager.backup_stopped_world()
        (self.world / 'level.dat').write_bytes(b'new saved world')
        latest = self.manager.backup_stopped_world()
        self.assertFalse(existing.exists())
        self.assertEqual(list(self.system.backup_path.iterdir()), [latest])
        with zipfile.ZipFile(latest) as archive:
            self.assertEqual(archive.read('level.dat'), b'new saved world')

    def test_retention_failure_preserves_new_archive_and_reports_saved_path(self):
        self.manager = WorldBackupManager(self.system, schedule=None, max_backups=1)
        existing = self.manager.backup_stopped_world()
        with patch.object(Path, 'unlink', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(OSError, 'saved.*retention failed') as raised:
                self.manager.backup_stopped_world()
        archives = set(self.system.backup_path.glob('*.zip'))
        self.assertEqual(len(archives), 2)
        newest = (archives - {existing}).pop()
        self.assertIn(str(newest), str(raised.exception))
        with zipfile.ZipFile(newest) as archive:
            self.assertEqual(archive.read('level.dat'), b'world data')

    def test_offline_backups_create_directory_and_keep_distinct_archives(self):
        with patch('launcher.world_backup_manager.MCRcon', side_effect=AssertionError('RCON used')):
            self.manager.backup_stopped_world()
            self.manager.backup_stopped_world()
        archives = list((self.base / 'backups').glob('*.zip'))
        self.assertEqual(len(archives), 2)
        for archive in archives:
            with zipfile.ZipFile(archive) as zip_file:
                self.assertEqual(zip_file.read('level.dat'), b'world data')

    def test_missing_world_does_not_produce_a_successful_empty_backup(self):
        (self.world / 'level.dat').unlink()
        self.world.rmdir()
        with self.assertRaises(FileNotFoundError):
            self.manager.backup_stopped_world()
        self.assertFalse(list((self.base / 'backups').glob('*.zip')))

    def test_failed_archive_leaves_no_partial_backup(self):
        with patch.object(zipfile.ZipFile, 'write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.backup_stopped_world()
        self.assertEqual(list((self.base / 'backups').iterdir()), [])

    def test_shutdown_during_scheduled_backup_restores_saving_before_returning(self):
        commands = []
        manager = self.manager

        class Rcon:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def command(self, command):
                commands.append(command)
                if command == 'save-all flush':
                    manager.request_shutdown()

        with patch('launcher.world_backup_manager.MCRcon', return_value=Rcon()):
            self.manager._perform_backup()
        self.assertLess(commands.index('save-all flush'), commands.index('save-on'))
        self.assertEqual(len(list((self.base / 'backups').glob('*.zip'))), 1)

    def test_archive_failure_still_restores_live_saving(self):
        commands = []

        class Rcon:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def command(self, command):
                commands.append(command)

        with patch('launcher.world_backup_manager.MCRcon', return_value=Rcon()), \
                patch.object(zipfile.ZipFile, 'write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager._perform_backup()
        self.assertIn('save-on', commands)

    def test_failed_rcon_read_cannot_leave_an_alarm_to_interrupt_shutdown(self):
        previous_handler = signal.signal(signal.SIGALRM, lambda *args: None)
        self.addCleanup(signal.signal, signal.SIGALRM, previous_handler)
        self.addCleanup(signal.alarm, 0)

        class FailedRcon:
            def __enter__(self):
                # mcrcon arms an alarm before recv and does not cancel it if
                # recv raises (including a failed authentication exchange).
                signal.alarm(5)
                raise ConnectionResetError('connection reset during read')

            def __exit__(self, *args):
                pass

        with patch('launcher.world_backup_manager.MCRcon', return_value=FailedRcon()):
            with self.assertRaises(ConnectionResetError):
                self.manager._perform_backup()
        self.assertEqual(signal.alarm(0), 0, 'RCON left an alarm armed during shutdown')


class StartupTests(unittest.TestCase):
    def test_mod_sync_uses_configured_minecraft_version(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = MinecraftConfig(
                minecraft_version='1.21.10', fabric_loader_version='test',
                fabric_installer_version='test', memory_size='1G',
                backup=BackupConfig(False, '* * * * *', 10), mods=['example'],
            )
            system = SystemConfig(base, base / 'mods', base / 'server',
                                  base / 'config.json', base / 'backups')
            with patch('launcher.modrinth.requests.get') as get, \
                    patch('launcher.modrinth.download_file') as download:
                get.return_value.status_code = 200
                get.return_value.json.return_value = [{
                    'game_versions': ['1.21.10'], 'loaders': ['fabric'],
                    'date_published': '2026-01-01T00:00:00Z', 'version_number': '1',
                    'files': [{'url': 'https://example.com/mod.jar', 'filename': 'mod.jar'}],
                }]
                download.side_effect = lambda url, name, dest: (dest / name).write_bytes(b'mod')
                modrinth.sync_mods(config, system)
            self.assertEqual((system.mods_dir / 'mod.jar').read_bytes(), b'mod')


if __name__ == '__main__':
    unittest.main()
