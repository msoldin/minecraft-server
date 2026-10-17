from pathlib import Path
import signal
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from launcher.shutdown_signals import shutdown_signals


class ShutdownSignalTests(unittest.TestCase):
    def test_signals_request_shutdown_and_restore_previous_handlers(self):
        previous_handlers = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }
        requests = []

        with shutdown_signals(lambda: requests.append("shutdown")):
            signal.raise_signal(signal.SIGTERM)
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGTERM)

        self.assertEqual(requests, ["shutdown", "shutdown", "shutdown"])
        for signum, previous in previous_handlers.items():
            self.assertEqual(signal.getsignal(signum), previous)

    def test_handlers_are_restored_when_protected_work_fails(self):
        previous_handlers = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }

        with self.assertRaisesRegex(OSError, "backup failed"):
            with shutdown_signals(lambda: None):
                raise OSError("backup failed")

        for signum, previous in previous_handlers.items():
            self.assertEqual(signal.getsignal(signum), previous)


if __name__ == "__main__":
    unittest.main()
