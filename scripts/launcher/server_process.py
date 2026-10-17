import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from .config import MinecraftConfig, SystemConfig


class ServerProcess:
    """Own the Java process, console forwarding, and graceful shutdown."""

    CONSOLE_POLL_SECONDS = 0.1
    STOP_COMMAND_TIMEOUT_SECONDS = 1.0

    def __init__(self, minecraft_config: MinecraftConfig, system_config: SystemConfig):
        self.minecraft_config = minecraft_config
        self.system_config = system_config
        self._process: Optional[subprocess.Popen[str]] = None
        self._output_thread: Optional[threading.Thread] = None
        self._input_thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()

    @property
    def has_started(self) -> bool:
        """Whether Java was launched, including if it has already exited."""
        return self._process is not None

    def start(self) -> None:
        print("Launcher finished. Starting Minecraft server... 🚀")
        self._write_eula(self.system_config.data_dir)
        self._process = self._run()
        # Console writes must remain cancellable if Java stops consuming input.
        os.set_blocking(self._process.stdin.fileno(), False)
        self._output_thread = threading.Thread(
            target=self._relay_output, args=(self._process,), daemon=True
        )
        self._output_thread.start()
        self._input_thread = threading.Thread(target=self._relay_input, daemon=True)
        self._input_thread.start()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> int:
        """Ask Minecraft to save and stop, then wait for the JVM to exit."""
        if self._process is None:
            return 0
        self._stopping.set()
        if self._input_thread is not None:
            self._input_thread.join()
        if self.is_running():
            print("Stopping Minecraft and waiting for its world save...")
            self._request_stop()
        returncode = self._process.wait()
        if self._output_thread is not None:
            self._output_thread.join()
        self._close_streams()
        return returncode

    def _request_stop(self) -> None:
        deadline = time.monotonic() + self.STOP_COMMAND_TIMEOUT_SECONDS
        # Finish any partial console command before sending stop. Input relay
        # has finished, so it cannot interleave bytes with this command.
        sent = self._write_input(
            b"\nstop\n", cancelled=lambda: time.monotonic() >= deadline
        )
        if not sent and self.is_running():
            print("Console unavailable; requesting Java shutdown with SIGTERM...")
            self._process.terminate()

    def _close_streams(self) -> None:
        try:
            self._process.stdin.close()
        except OSError:
            # Java has exited; pipe cleanup must not prevent its final backup.
            pass
        self._process.stdout.close()

    def _run(self) -> subprocess.Popen[str]:
        jar_path = (
            self.system_config.server_dir
            / f"{self.minecraft_config.minecraft_version}-server.jar"
        ).resolve()
        java_cmd = [
            "java",
            f"-Xms{self.minecraft_config.memory_size}",
            f"-Xmx{self.minecraft_config.memory_size}",
            "-Dlog4j2.formatMsgNoLookups=true",
            "-XX:+UseZGC",
            "-XX:+AlwaysPreTouch",
            "-XX:+UseStringDeduplication",
            "-XX:+UseCompactObjectHeaders",
            "-jar",
            str(jar_path),
            "nogui",
        ]
        return subprocess.Popen(
            java_cmd,
            cwd=self.system_config.data_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            # Let the launcher serialize terminal signals with active backups.
            start_new_session=True,
        )

    def _relay_input(self) -> None:
        """Keep docker attach console input working through the stdin pipe."""
        try:
            input_fd = sys.stdin.fileno()
            while not self._stopping.is_set() and self.is_running():
                if not select.select([input_fd], [], [], self.CONSOLE_POLL_SECONDS)[0]:
                    continue
                data = os.read(input_fd, 4096)
                if not data:
                    return
                if not self._write_input(data, cancelled=self._stopping.is_set):
                    return
        except (OSError, ValueError):
            # A detached container may have no readable console input.
            return

    def _write_input(self, data: bytes, *, cancelled: Callable[[], bool]) -> bool:
        """Write all bytes without blocking indefinitely; report cancellation/EOF."""
        input_fd = self._process.stdin.fileno()
        remaining = memoryview(data)
        try:
            while remaining:
                if cancelled() or not self.is_running():
                    return False
                try:
                    written = os.write(input_fd, remaining)
                    remaining = remaining[written:]
                except BlockingIOError:
                    select.select([], [input_fd], [], self.CONSOLE_POLL_SECONDS)
        except OSError:
            return False
        return True

    def _write_eula(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        eula_path = data_dir / "eula.txt"

        if not eula_path.exists():
            with open(eula_path, "w") as f:
                f.write("eula=true\n")
            print(f"✅ eula.txt created at {eula_path}")
        else:
            print(f"ℹ️ eula.txt already exists at {eula_path}, skipping")

    def _relay_output(self, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()  # flush immediately so it appears in console
