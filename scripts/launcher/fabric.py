from pathlib import Path
from .config import MinecraftConfig
from .utils import download_file


def download_server(config: MinecraftConfig, dest_folder: Path):
    """Download Fabric server JAR if not already present."""
    filename = f"{config.minecraft_version}-server.jar"
    url = f"https://meta.fabricmc.net/v2/versions/loader/{config.minecraft_version}/{config.fabric_loader_version}/{config.fabric_installer_version}/server/jar"
    return download_file(url, filename, dest_folder)
