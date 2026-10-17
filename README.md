# minecraft-server

Stopping the container with `docker compose stop` or `docker compose down`
requests a graceful shutdown. The launcher finishes any backup already in
progress, sends Minecraft `stop`, waits for Java to exit and save the world,
and then creates a final ZIP in `/backups` before exiting. The final backup
does not require RCON. A backup failure is logged and causes a nonzero exit.

Console writes remain cancellable if Minecraft stops reading input. If the
launcher cannot deliver the `stop` command within one second, it sends Java
`SIGTERM` instead and waits for Java to exit before creating the backup.

Compose allows five minutes for the whole sequence (`stop_grace_period: 5m`).
Increase this for worlds whose save and backup take longer. For a direct
Docker stop, use `docker stop --time 300 minecraft`. A forced kill (`SIGKILL`),
an expired stop timeout, or power loss cannot run this cleanup.

Backups contain `/data/world` and appear in the host's `./backups` directory.
Both bind-mounted directories must be writable by the container's Minecraft
user (UID/GID 1000 by default). Scheduled backups use the existing RCON
settings: localhost port 25575, password `test`; configure the server to match.

Configure backups in `config.json`:

```json
"backup": {
    "periodic": true,
    "period": "* * * * *",
    "max": 10
}
```

All three settings are required. `periodic` must be a boolean, `period` a
nonempty string, and `max` a positive integer (including `1`). Unknown keys
inside `backup` are rejected. Set `periodic` to `false` for **exit-only backups**:
the server stays running, no scheduled backups or RCON connections are made,
and a final backup still runs after the server exits. In this mode `period`
is unused and its cron syntax is not validated.

Enabled schedules use **UTC**, independent of the host's timezone, and five
cron fields: minute, hour, day of month, month, day of week. Wildcards, steps,
ranges, lists, and month/weekday names are supported. Aliases such as `@daily`,
seconds/year fields, and extensions such as randomized or hashed schedules
are not supported.

| `period` | Schedule (UTC) |
| --- | --- |
| `* * * * *` | Every minute |
| `*/15 * * * *` | Every quarter hour |
| `0 3 * * *` | Daily at 03:00 |
| `0 3 * * mon` | Mondays at 03:00 |
| `0 0 1 * *` | Midnight on the first day of each month |

When both day fields are restricted, either can match: `0 0 1 * mon` means
midnight on the first of each month **or** any Monday. The first backup runs
at the next matching instant after startup. Backups never overlap, and missed
occurrences are skipped. A failed periodic attempt is logged and retried at
the next future occurrence. Enabled schedules are validated before downloading
server files or starting Java.

`max` limits periodic and exit backups **together**. After successfully writing
and publishing a new ZIP, the launcher removes the oldest excess completed
archives by modification time, using filenames to break ties. It always keeps
the newly saved archive. Rotation recognizes valid
`world-backup-YYYYMMDD-HHMMSS.zip` and
`world-backup-YYYYMMDD-HHMMSS-ffffff.zip` regular files; unrelated files,
partial archives, directories, and symlinks are left alone.

Old archives are not deleted at startup or when creating/publishing a new
backup fails. Allow space for one additional archive during rotation. If
deleting an old archive fails, the new backup remains saved, the failure is
reported, and the limit may be exceeded. A periodic attempt continues to the
next schedule; a final backup reports a nonzero application exit status.

To migrate, replace the old top-level `backup_period` setting with the object
above. Keeping `backup_period`, even alongside `backup`, fails startup with
`backup_period is no longer supported; use backup.periodic, backup.period, and backup.max`.
An interval is not automatically converted into a calendar schedule.

Rebuild and recreate the container to apply launcher changes:

```sh
docker compose up -d --build
```

Run the backup and shutdown regression tests with the dependencies from
`build/requirements.txt` installed:

```sh
python -m unittest discover -s tests -v
```

The tests send real signals to the Python launcher and use a small substitute
for Java, so they do not start Minecraft or modify an existing world.

The code is organized by responsibility:

- `scripts/launcher.py` prepares the server; `run_server()` coordinates server
  shutdown and the final backup.
- `shutdown_signals()` temporarily installs termination handlers and restores
  the previous handlers after cleanup, even when cleanup fails.
- `ServerProcess` owns Java and its console streams. Callers use `has_started`
  and `is_running()` rather than accessing the subprocess directly.
- `WorldBackupManager` schedules backups and shares archive creation between
  live and stopped worlds. `request_shutdown()` stops future scheduling while
  allowing an active backup to finish.
- `BackupConfig` validates the nested settings; `CronSchedule` calculates UTC
  occurrences through a one-method `BackupSchedule` interface. The manager's
  schedule, clock, and sleep function are injected for deterministic tests.
- `prune_backups()` owns archive selection and deletion independently of
  scheduling, RCON, and server lifecycle handling.
- `tests/helpers/` contains the executable test server and launcher setup.
