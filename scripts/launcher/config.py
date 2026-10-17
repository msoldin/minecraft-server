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

@dataclass(frozen=True)
class BackupConfig:
    periodic_enabled: bool
    cron_expression: str
    max_backups: int

    @staticmethod
    def from_dict(data: dict) -> "BackupConfig":
        if not isinstance(data, dict):
            raise ValueError("backup must be an object with periodic, period, and max")
        required = {"periodic", "period", "max"}
        for key in sorted(required - data.keys()):
            raise ValueError(f"backup.{key} is required")
        for key in sorted(data.keys() - required):
            raise ValueError(f"Unknown setting: backup.{key}")
        if type(data["periodic"]) is not bool:
            raise ValueError("backup.periodic must be a boolean")
        if not isinstance(data["period"], str) or not data["period"].strip():
            raise ValueError("backup.period must be a nonempty string")
        if type(data["max"]) is not int or data["max"] < 1:
            raise ValueError("backup.max must be a positive integer")
        return BackupConfig(
            periodic_enabled=data["periodic"],
            cron_expression=data["period"],
            max_backups=data["max"],
        )


@dataclass
class MinecraftConfig:
    minecraft_version: str
    fabric_loader_version: str
    fabric_installer_version: str
    memory_size: str
    backup: BackupConfig
    mods: list

    @staticmethod
    def from_json(path: Path) -> "MinecraftConfig":
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if "backup_period" in data:
            raise ValueError(
                "backup_period is no longer supported; "
                "use backup.periodic, backup.period, and backup.max"
            )
        data["backup"] = BackupConfig.from_dict(data.get("backup"))
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
                server_dir=Path("/opt/minecraft/versions"),
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
