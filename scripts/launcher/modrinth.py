from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from .config import ModFile, MinecraftConfig, SystemConfig
from .utils import download_file


def download_mods(
    minecraft_config: MinecraftConfig, system_config: SystemConfig
) -> None:
    for mod in minecraft_config.mods:
        latest = get_latest_modrinth_version(mod, minecraft_config.minecraft_version)
        if latest:
            download_mod(latest, system_config.mods_dir)


def download_mod(mod: ModFile, dest_folder: Path):
    """Download a mod .jar file to the given destination folder."""
    return download_file(mod.url, mod.name, dest_folder)


def get_latest_modrinth_version(
    project_slug: str, game_version: str, loader: str = "fabric"
) -> Optional[ModFile]:
    url = f"https://api.modrinth.com/v2/project/{project_slug}/version"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch {project_slug}: HTTP {response.status_code}")
        return None
    versions = response.json()

    # Filter by game version and loader
    filtered = [
        v
        for v in versions
        if game_version in v.get("game_versions", []) and loader in v.get("loaders", [])
    ]

    if not filtered:
        print(
            f"❌ No matching version found for {project_slug} ({game_version}, {loader})"
        )
        return None

    # Sort newest first
    filtered.sort(
        key=lambda v: datetime.fromisoformat(
            v["date_published"].replace("Z", "+00:00")
        ),
        reverse=True,
    )

    latest = filtered[0]
    file = latest["files"][0]

    return ModFile(
        url=file["url"],
        name=file["filename"],
        version_number=latest["version_number"],
        date_published=datetime.fromisoformat(
            latest["date_published"].replace("Z", "+00:00")
        ),
    )
