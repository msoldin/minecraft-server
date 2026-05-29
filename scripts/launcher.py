from launcher import modrinth
from launcher import fabric
from launcher.server_process import ServerProcess
from launcher.world_backup_manager import WorldBackupManager
from launcher.config import MinecraftConfig, SystemConfig


def main():
    system_config = SystemConfig.auto()
    minecraft_config = MinecraftConfig.from_json(system_config.config_path)
    print(
        f"📦 Minecraft {minecraft_config.minecraft_version} | Fabric Loader {minecraft_config.fabric_loader_version} | Fabric Installer {minecraft_config.fabric_installer_version}"
    )
    fabric.download_server(
        config=minecraft_config, dest_folder=system_config.server_dir
    )
    modrinth.download_mods(minecraft_config, system_config)
    ServerProcess(minecraft_config, system_config).start()
    WorldBackupManager(minecraft_config, system_config).start()


if __name__ == "__main__":
    main()
