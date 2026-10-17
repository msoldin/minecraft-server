import os
import signal
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from mcrcon import MCRcon

from .backup_retention import prune_backups
from .backup_schedule import BackupSchedule, utc_now
from .config import SystemConfig


class WorldBackupManager:
    """Run scheduled backups on the main thread, then back up the stopped world."""

    def __init__(
        self,
        system_config: SystemConfig,
        *,
        schedule: BackupSchedule | None,
        max_backups: int,
        now: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.system_config = system_config
        self._schedule = schedule
        self._max_backups = max_backups
        self._now = now
        self._sleep = sleep
        self._shutdown_requested = False

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def start(self, is_server_running: Callable[[], bool]) -> None:
        """Block until shutdown or server exit, checking at least once a second."""
        next_backup = self._schedule.next_after(self._now()) if self._schedule else None
        while not self.shutdown_requested and is_server_running():
            if next_backup is None:
                self._sleep(1)
                continue
            remaining = (next_backup - self._now()).total_seconds()
            if remaining > 0:
                self._sleep(min(remaining, 1))
                continue
            self._attempt_periodic_backup()
            next_backup = self._schedule.next_after(max(self._now(), next_backup))

    def _attempt_periodic_backup(self) -> None:
        try:
            self._perform_backup()
        except Exception as error:
            print(f"Backup failed ❌: {error}", flush=True)

    def request_shutdown(self) -> None:
        """Request shutdown without interrupting any backup already in progress."""
        self._shutdown_requested = True

    def backup_stopped_world(self) -> Path:
        """Back up after the Java process exits; no RCON connection is needed."""
        print("Creating final world backup...", flush=True)
        try:
            path = self._archive_and_prune()
        except Exception as error:
            print(f"Final world backup failed ❌: {error}", flush=True)
            raise
        print(f"Final world backup complete ✅: {path}", flush=True)
        return path

    def _perform_backup(self) -> None:
        """Flush a running server and always restore saving after archiving."""
        try:
            with MCRcon(host="localhost", password="test", port=25575) as mcr:
                mcr.command("say Backup is running!")
                try:
                    mcr.command("save-off")
                    mcr.command("save-all flush")
                    self._archive_and_prune()
                finally:
                    mcr.command("save-on")
                mcr.command("say Backup is finished!")
        finally:
            # mcrcon can leave its read timeout armed after a socket error.
            # It must not interrupt the subsequent server stop/offline backup.
            signal.alarm(0)

    def _archive_and_prune(self) -> Path:
        path = self._create_archive()
        try:
            prune_backups(
                self.system_config.backup_path,
                max_backups=self._max_backups,
                newest_backup=path,
            )
        except OSError as error:
            raise OSError(f"Backup saved at {path}, but retention failed: {error}") from error
        return path

    def _create_archive(self) -> Path:
        world_path = self.system_config.data_dir / "world"
        if not world_path.is_dir():
            raise FileNotFoundError(f"World directory does not exist: {world_path}")
        self.system_config.backup_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        zip_path = self.system_config.backup_path / f"world-backup-{timestamp}.zip"
        temporary_path = zip_path.with_suffix(".zip.part")

        def raise_walk_error(error):
            raise error

        try:
            with zipfile.ZipFile(
                temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zipf:
                for root, _, files in os.walk(world_path, onerror=raise_walk_error):
                    for filename in files:
                        full_path = Path(root) / filename
                        zipf.write(full_path, arcname=full_path.relative_to(world_path))
            temporary_path.replace(zip_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        return zip_path
