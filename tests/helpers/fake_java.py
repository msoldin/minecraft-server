"""A small process that simulates Minecraft saving its world during shutdown."""

import array
import fcntl
import os
from pathlib import Path
import signal
import sys
import termios
import time


def save_and_exit(signum=None, frame=None):
    Path('stopping').touch()
    time.sleep(0.2)
    Path('world/level.dat').write_text('saved on shutdown')
    sys.exit(0)


def wait_for_full_console():
    """Notify the test once the Java input pipe is full, without draining it."""
    capacity = fcntl.fcntl(0, fcntl.F_GETPIPE_SZ)
    while True:
        pending = array.array('i', [0])
        fcntl.ioctl(0, termios.FIONREAD, pending)
        if pending[0] == capacity:
            Path('console-full').touch()
            return
        time.sleep(0.01)


def main():
    Path('java.pid').write_text(str(os.getpid()))
    Path('world').mkdir(exist_ok=True)
    Path('world/level.dat').write_text('before shutdown')
    signal.signal(signal.SIGTERM, save_and_exit)
    if os.environ.get('CLOSE_STDIN'):
        os.close(0)
    Path('ready').touch()

    if os.environ.get('CLOSE_STDIN') or os.environ.get('STALL_STDIN'):
        if os.environ.get('STALL_STDIN'):
            wait_for_full_console()
        while True:
            time.sleep(0.01)

    if os.environ.get('PAUSE_STDIN'):
        wait_for_full_console()
        while not Path('release-console').exists():
            time.sleep(0.01)

    if os.environ.get('SERVER_EXIT'):
        sys.exit(int(os.environ['SERVER_EXIT']))
    for line in sys.stdin:
        if line.strip() == 'stop':
            save_and_exit()
        received = Path('console-command.part')
        received.write_text(line)
        received.replace('console-command')


if __name__ == '__main__':
    main()
