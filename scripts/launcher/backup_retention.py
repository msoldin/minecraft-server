"""Remove excess completed world backups after a new archive is published."""

import re
import stat
from datetime import datetime
from pathlib import Path


_BACKUP_NAME = re.compile(r'world-backup-(\d{8}-\d{6})(-\d{6})?\.zip', re.ASCII)


def _backup_mtime(path: Path) -> int | None:
    match = _BACKUP_NAME.fullmatch(path.name)
    if match is None:
        return None
    try:
        datetime.strptime(match[1], '%Y%m%d-%H%M%S')
    except ValueError:
        return None
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    return metadata.st_mtime_ns if stat.S_ISREG(metadata.st_mode) else None


def _oldest_backups(directory: Path, newest_backup: Path) -> list[Path]:
    candidates = []
    for path in directory.iterdir():
        if path == newest_backup:
            continue
        mtime = _backup_mtime(path)
        if mtime is not None:
            candidates.append((mtime, path.name, path))
    return [path for _, _, path in sorted(candidates)]


def prune_backups(directory: Path, *, max_backups: int, newest_backup: Path) -> list[Path]:
    """Keep the new archive plus the newest max_backups - 1 eligible files."""
    if type(max_backups) is not int or max_backups < 1:
        raise ValueError('backup.max must be a positive integer')
    directory = directory.absolute()
    newest_backup = newest_backup.absolute()
    if newest_backup.parent != directory or _backup_mtime(newest_backup) is None:
        raise ValueError('newest_backup must be a completed regular backup in the backup directory')

    candidates = _oldest_backups(directory, newest_backup)
    excess_count = max(0, len(candidates) + 1 - max_backups)
    deleted = []
    for path in candidates[:excess_count]:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise OSError(
                f'Backup saved at {newest_backup}, but retention failed removing {path}: {error}'
            ) from error
        deleted.append(path)
    return deleted
