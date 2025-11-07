import json
import shutil
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

def is_docker():
    return Path("/.dockerenv").exists()

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
    mods: List[str]

    @staticmethod
    def from_json(path: Path) -> "MinecraftConfig":
        """Load and parse JSON into a ModConfig instance."""
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return MinecraftConfig(**data)

@dataclass
class SystemConfig:
    data_dir: Path
    mods_dir: Path
    server_dir: Path
    config_path: Path
    profile_path: Path


    @staticmethod
    def auto() -> "SystemConfig":
        if is_docker():
            return SystemConfig(
                data_dir=Path("/data"),
                mods_dir=Path("/data/mods"),
                server_dir=Path("/opt/minecraft"),
                config_path=Path("/config/config.json"),
                profile_path=Path("/config/minecraft_version.sh")
      
            )
        else:
            base = Path("./local")
            if base.exists():
                shutil.rmtree(base)
                print(f"🗑️ Removed existing {base} directory")
            return SystemConfig(
                data_dir=base / "data",
                mods_dir=base / "data" / "mods",
                server_dir=base / "server",
                config_path=Path("config.json"),
                profile_path=base / "config" / "minecraft_version.sh"
            )


def get_latest_modrinth_version(project_slug: str, game_version: str, loader: str = "fabric") -> Optional[ModFile]:
    url = f"https://api.modrinth.com/v2/project/{project_slug}/version"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch {project_slug}: HTTP {response.status_code}")
        return None
    versions = response.json()

    # Filter by game version and loader
    filtered = [
        v for v in versions
        if game_version in v.get("game_versions", [])
        and loader in v.get("loaders", [])
    ]

    if not filtered:
        print(f"❌ No matching version found for {project_slug} ({game_version}, {loader})")
        return None

    # Sort newest first
    filtered.sort(
        key=lambda v: datetime.fromisoformat(v["date_published"].replace("Z", "+00:00")),
        reverse=True
    )

    latest = filtered[0]
    file = latest["files"][0]

    return ModFile(
        url=file["url"],
        name=file["filename"],
        version_number=latest["version_number"],
        date_published=datetime.fromisoformat(latest["date_published"].replace("Z", "+00:00"))
    )

def download_file(url: str, filename: str, dest_folder: Path):
    """Download a file if it does not already exist."""
    dest_folder.mkdir(parents=True, exist_ok=True)
    dest_path = dest_folder / filename

    if dest_path.exists():
        print(f"✅ {filename} already exists, skipping download.")
        return dest_path

    print(f"⬇️ Downloading {filename} ...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    print(f"✅ Saved to {dest_path}\n")
    return dest_path

def download_mod(mod: ModFile, dest_folder: Path):
    """Download a mod .jar file to the given destination folder."""
    return download_file(mod.url, mod.name, dest_folder)

def download_fabric_server(config: MinecraftConfig, dest_folder: Path):
    """Download Fabric server JAR if not already present."""
    filename = f"{config.minecraft_version}-server.jar"
    url = f"https://meta.fabricmc.net/v2/versions/loader/{config.minecraft_version}/{config.fabric_loader_version}/{config.fabric_installer_version}/server/jar"
    return download_file(url, filename, dest_folder)

def write_env_profile(path: Path, variables: dict):
    """
    Write environment variables to a shell script that can be sourced later.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for key, value in variables.items():
            f.write(f'export {key}="{value}"\n')
    print(f"✅ Environment profile written to {path}")

def write_eula(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    eula_path = data_dir / "eula.txt"
    
    if not eula_path.exists():
        with open(eula_path, "w") as f:
            f.write("eula=true\n")
        print(f"✅ eula.txt created at {eula_path}")
    else:
        print(f"ℹ️ eula.txt already exists at {eula_path}, skipping")

# Example usage
def main():
    system_config = SystemConfig.auto()
    minecraft_config = MinecraftConfig.from_json(system_config.config_path)
    
    print(f"📦 Minecraft {minecraft_config.minecraft_version} | Fabric Loader {minecraft_config.fabric_loader_version} | Fabric Installer {minecraft_config.fabric_installer_version}")
    download_fabric_server(config=minecraft_config, dest_folder=system_config.server_dir)

    print(f"Mods to check: {', '.join(minecraft_config.mods)}\n")
    for mod in minecraft_config.mods:
        latest = get_latest_modrinth_version(mod, minecraft_config.minecraft_version)
        if latest:
            download_mod(latest, system_config.mods_dir)
    
    print(f"Write current configuration to profile \n")
    vars_to_write = {
        "MINECRAFT_VERSION": minecraft_config.minecraft_version,
    }
    write_env_profile(system_config.profile_path, vars_to_write)
    write_eula(data_dir=system_config.data_dir)


if __name__ == "__main__":
    main()