import sys

from launcher import modrinth
from launcher import fabric
from launcher.backup_schedule import CronSchedule, utc_now
from launcher.server_process import ServerProcess
from launcher.shutdown_signals import shutdown_signals
from launcher.world_backup_manager import WorldBackupManager
from launcher.config import MinecraftConfig, SystemConfig


def main() -> int:
    system_config = SystemConfig.auto()
    minecraft_config = MinecraftConfig.from_json(system_config.config_path)
    backup_config = minecraft_config.backup
    schedule = CronSchedule(backup_config.cron_expression) if backup_config.periodic_enabled else None
    if schedule is not None:
        schedule.next_after(utc_now())  # Validate before downloads or Java startup.
    print(
        f"📦 Minecraft {minecraft_config.minecraft_version} | Fabric Loader {minecraft_config.fabric_loader_version} | Fabric Installer {minecraft_config.fabric_installer_version}"
    )
    fabric.download_server(
        config=minecraft_config, dest_folder=system_config.server_dir
    )
    modrinth.sync_mods(minecraft_config, system_config)
    server = ServerProcess(minecraft_config, system_config)
    backups = WorldBackupManager(
        system_config, schedule=schedule, max_backups=backup_config.max_backups,
    )
    return run_server(server, backups)


def run_server(server: ServerProcess, backups: WorldBackupManager) -> int:
    """Run the server, then stop it before creating the final backup."""
    returncode = 0
    with shutdown_signals(backups.request_shutdown):
        try:
            if not backups.shutdown_requested:
                server.start()
                backups.start(server.is_running)
        finally:
            backups.request_shutdown()
            if server.has_started:
                returncode = server.stop()
                backups.backup_stopped_world()
    return returncode


if __name__ == "__main__":
    sys.exit(main())
