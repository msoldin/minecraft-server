import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from launcher.backup_schedule import CronSchedule
from launcher.config import SystemConfig
from launcher.world_backup_manager import WorldBackupManager


class FakeClock:
    def __init__(self):
        self.instant = datetime(2026, 10, 17, 12, 0, 30, tzinfo=UTC)
        self.sleeps = []

    def now(self):
        return self.instant

    def advance(self, seconds):
        self.instant += timedelta(seconds=seconds)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if len(self.sleeps) > 1000:
            raise AssertionError('Scheduler did not stop')
        self.advance(seconds)


class BackupSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.attempts = []
        self.system = SystemConfig(*(Path('/unused') for _ in range(5)))

    def manager(self, schedule='* * * * *', sleep=None):
        return WorldBackupManager(
            self.system, schedule=CronSchedule(schedule) if schedule else None,
            max_backups=10, now=self.clock.now, sleep=sleep or self.clock.sleep,
        )

    def run_until(self, manager, until, attempt=None):
        def record():
            self.attempts.append(self.clock.now())
            if attempt:
                attempt()
        with patch.object(manager, '_perform_backup', side_effect=record):
            manager.start(lambda: self.clock.now() < until)
        self.assertTrue(all(0 < seconds <= 1 for seconds in self.clock.sleeps))

    def test_runs_once_per_boundary_and_never_early(self):
        self.run_until(self.manager(), datetime(2026, 10, 17, 12, 2, 1, tzinfo=UTC))
        self.assertEqual(self.attempts, [
            datetime(2026, 10, 17, 12, 1, tzinfo=UTC),
            datetime(2026, 10, 17, 12, 2, tzinfo=UTC),
        ])

    def test_slow_backup_skips_missed_occurrences(self):
        def slow_first():
            if len(self.attempts) == 1:
                self.clock.advance(185)
        self.run_until(self.manager(), datetime(2026, 10, 17, 12, 5, 1, tzinfo=UTC), slow_first)
        self.assertEqual(self.attempts, [
            datetime(2026, 10, 17, 12, 1, tzinfo=UTC),
            datetime(2026, 10, 17, 12, 5, tzinfo=UTC),
        ])

    def test_failed_slow_backup_retries_at_next_future_occurrence(self):
        def fail_first():
            if len(self.attempts) == 1:
                self.clock.advance(65)
                raise OSError('disk full')
        self.run_until(self.manager(), datetime(2026, 10, 17, 12, 3, 1, tzinfo=UTC), fail_first)
        self.assertEqual(self.attempts, [
            datetime(2026, 10, 17, 12, 1, tzinfo=UTC),
            datetime(2026, 10, 17, 12, 3, tzinfo=UTC),
        ])

    def test_forward_clock_jump_causes_one_due_run_without_catchup(self):
        def jump_once(seconds):
            if not self.clock.sleeps:
                self.clock.advance(599)
            self.clock.sleep(seconds)
        self.run_until(self.manager(sleep=jump_once), datetime(2026, 10, 17, 12, 11, 1, tzinfo=UTC))
        self.assertEqual(self.attempts, [
            datetime(2026, 10, 17, 12, 10, 30, tzinfo=UTC),
            datetime(2026, 10, 17, 12, 11, tzinfo=UTC),
        ])

    def test_backward_jump_during_backup_cannot_repeat_handled_occurrence(self):
        def jump_once():
            if len(self.attempts) == 1:
                self.clock.advance(-120)
        self.run_until(self.manager(), datetime(2026, 10, 17, 12, 2, 1, tzinfo=UTC), jump_once)
        self.assertEqual(self.attempts, [
            datetime(2026, 10, 17, 12, 1, tzinfo=UTC),
            datetime(2026, 10, 17, 12, 2, tzinfo=UTC),
        ])

    def test_disabled_schedule_monitors_server_across_cron_boundaries(self):
        with patch('launcher.world_backup_manager.MCRcon', side_effect=AssertionError('RCON used')):
            manager = self.manager(schedule=None)
            manager.start(lambda: self.clock.now() < datetime(2026, 10, 17, 12, 3, tzinfo=UTC))
        self.assertEqual(self.clock.now(), datetime(2026, 10, 17, 12, 3, tzinfo=UTC))
        self.assertTrue(all(0 < seconds <= 1 for seconds in self.clock.sleeps))

    def test_disabled_or_far_future_schedule_responds_to_shutdown(self):
        for expression in (None, '0 0 1 1 *'):
            with self.subTest(expression=expression):
                self.clock = FakeClock()
                def stop_after_poll(seconds):
                    self.clock.sleep(seconds)
                    manager.request_shutdown()
                manager = self.manager(schedule=expression, sleep=stop_after_poll)
                with patch('launcher.world_backup_manager.MCRcon', side_effect=AssertionError('RCON used')):
                    manager.start(lambda: True)
                self.assertEqual(self.clock.sleeps, [1])
