"""Temporarily route termination signals to an application's shutdown request."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import signal


@contextmanager
def shutdown_signals(request_shutdown: Callable[[], None]) -> Iterator[None]:
    """Keep handlers active through cleanup, then restore the previous handlers."""
    def handle_signal(signum, frame):
        # Request shutdown without interrupting an active save or backup.
        request_shutdown()

    previous_handlers = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, handle_signal)
        yield
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
