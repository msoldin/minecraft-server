"""Run the production launcher with downloads disabled and isolated test paths."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import runpy
import sys
import time
import zipfile

PROJECT_ROOT = Path(sys.argv[1])
DATA_DIR = Path(os.environ['TEST_DATA'])
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

from launcher import backup_schedule, fabric, modrinth, world_backup_manager
from launcher.config import SystemConfig


def wait_for_release(filename):
    deadline = time.monotonic() + 5
    while not (DATA_DIR / filename).exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f'Test did not create {filename}')
        time.sleep(0.01)


def pause_final_archive():
    original_write = zipfile.ZipFile.write

    def slow_write(self, *args, **kwargs):
        original_write(self, *args, **kwargs)
        (DATA_DIR / 'final-backup-active').touch()
        wait_for_release('release-final-backup')

    zipfile.ZipFile.write = slow_write


def pause_scheduled_backup():
    class FastSchedule:
        def __init__(self, expression):
            pass

        def next_after(self, instant):
            return instant + timedelta(seconds=0.06)

    class PausingRcon:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def command(self, command):
            if command == 'save-all flush':
                (DATA_DIR / 'backup-active').touch()
                wait_for_release('release-backup')
            if command == 'save-on':
                (DATA_DIR / 'saving-restored').touch()

    backup_schedule.CronSchedule = FastSchedule
    world_backup_manager.MCRcon = PausingRcon


def advance_scheduler_clock():
    """Cross cron boundaries quickly while retaining the real monitoring loop."""
    instant = datetime(2026, 10, 17, 12, tzinfo=UTC)
    manager_class = world_backup_manager.WorldBackupManager

    def sleep(seconds):
        nonlocal instant
        instant += timedelta(seconds=61)
        if instant.minute >= 3:
            (DATA_DIR / 'clock-advanced').touch()
        time.sleep(0.01)

    def create_manager(system_config, **kwargs):
        return manager_class(system_config, now=lambda: instant, sleep=sleep, **kwargs)

    def unexpected_rcon(**kwargs):
        (DATA_DIR / 'rcon-used').touch()
        raise AssertionError('Exit-only mode must not use RCON')

    world_backup_manager.WorldBackupManager = create_manager
    world_backup_manager.MCRcon = unexpected_rcon


def fail_retention():
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.suffix == '.zip':
            raise PermissionError(f'Cannot remove {path}')
        return original_unlink(path, *args, **kwargs)

    Path.unlink = unlink


def main():
    config_path = DATA_DIR / 'config.json'
    if not config_path.exists():
        config_path = PROJECT_ROOT / 'config.json'
    SystemConfig.auto = staticmethod(lambda: SystemConfig(
        DATA_DIR, DATA_DIR / 'mods', DATA_DIR / 'server',
        config_path, DATA_DIR / 'backups'))
    fabric.download_server = lambda **kwargs: None
    modrinth.sync_mods = lambda *args: None
    if os.environ.get('SLOW_FINAL_BACKUP'):
        pause_final_archive()
    if os.environ.get('ACTIVE_BACKUP'):
        pause_scheduled_backup()
    if os.environ.get('ADVANCE_CLOCK'):
        advance_scheduler_clock()
    if os.environ.get('FAIL_RETENTION'):
        fail_retention()
    runpy.run_path(str(PROJECT_ROOT / 'scripts/launcher.py'), run_name='__main__')


if __name__ == '__main__':
    main()
