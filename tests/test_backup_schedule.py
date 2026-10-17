import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from launcher.backup_schedule import CronSchedule


class CronScheduleTests(unittest.TestCase):
    reference = datetime(2026, 10, 17, 12, tzinfo=UTC)

    def test_next_occurrence_obeys_standard_cron_in_utc(self):
        cases = [
            ('* * * * *', '2026-10-17T12:01:00+00:00'),
            ('*/15 * * * *', '2026-10-17T12:15:00+00:00'),
            ('0 0 1 * *', '2026-11-01T00:00:00+00:00'),
            ('0 9 * * mon', '2026-10-19T09:00:00+00:00'),
            ('0 0 1 * mon', '2026-10-19T00:00:00+00:00'),
            ('0 0 29 2 *', '2028-02-29T00:00:00+00:00'),
            ('0 0 31 2 mon', '2027-02-01T00:00:00+00:00'),
            ('5,20 12-14 * * *', '2026-10-17T12:05:00+00:00'),
            ('0 0 * * 0', '2026-10-18T00:00:00+00:00'),
            ('0 0 * * 7', '2026-10-18T00:00:00+00:00'),
            ('0 0 1 mar *', '2027-03-01T00:00:00+00:00'),
            ('0 0 * * thu', '2026-10-22T00:00:00+00:00'),
        ]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                actual = CronSchedule(expression).next_after(self.reference)
                self.assertEqual(actual, datetime.fromisoformat(expected))
                self.assertIs(actual.tzinfo, UTC)

    def test_partial_minute_is_not_an_immediate_occurrence(self):
        actual = CronSchedule('*/15 * * * *').next_after(
            datetime(2026, 10, 17, 12, 7, 30, tzinfo=UTC))
        self.assertEqual(actual, datetime(2026, 10, 17, 12, 15, tzinfo=UTC))

    def test_non_utc_input_is_normalized_without_local_clock_scheduling(self):
        instant = datetime.fromisoformat('2026-10-17T14:00:00+02:00')
        actual = CronSchedule('0 13 * * *').next_after(instant)
        self.assertEqual(actual, datetime(2026, 10, 17, 13, tzinfo=UTC))
        self.assertIs(actual.tzinfo, UTC)

    def test_invalid_or_unsupported_expressions_name_backup_period(self):
        for expression in (
            '', '* * * *', '* * * * * *', '* * * * * * *', '@daily',
            '61 * * * *', '0 25 * * *', '*/0 * * * *',
            'R * * * *', 'r(0-30) * * * *', 'H * * * *', 'H/5 * * * *',
            '0 0 31 2 *', '0 0 L * *', '0 0 * * mon#2', '0 0 ? * *',
        ):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(ValueError, r'backup\.period'):
                    CronSchedule(expression).next_after(self.reference)

    def test_naive_time_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'timezone-aware'):
            CronSchedule('* * * * *').next_after(datetime(2026, 10, 17))
