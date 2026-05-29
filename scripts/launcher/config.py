from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

@dataclass
class ModFile:
    url: str
    name: str
    version_number: str
    date_published: datetime

@dataclass
class MinecraftConfig:
    minecraft_version: str
    fabric_loader_version: str
    fabric_installer_version: str
    memory_size: str
    backup_period: int
    mods: list

    @staticmethod
    def from_json(path: Path) -> "MinecraftConfig":
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return MinecraftConfig(**data)

@dataclass
class SystemConfig:
    data_dir: Path
    mods_dir: Path
    server_dir: Path
    config_path: Path
    backup_path: Path

    @staticmethod
    def auto() -> "SystemConfig":
        if Path("/.dockerenv").exists():
            return SystemConfig(
                data_dir=Path("/data"),
                mods_dir=Path("/data/mods"),
                server_dir=Path("/opt/minecraft"),
                config_path=Path("/config/config.json"),
                backup_path=Path("/backups")
            )
        else:
            base = Path("./local")
            return SystemConfig(
                data_dir=base / "data",
                mods_dir=base / "data" / "mods",
                server_dir=base / "server",
                config_path=Path("config.json"),
                backup_path=base / "backups"
            )