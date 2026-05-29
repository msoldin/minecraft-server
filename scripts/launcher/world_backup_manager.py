import os
import time
import zipfile
import threading
from mcrcon import MCRcon
from typing import Optional
from datetime import datetime
from .config import MinecraftConfig, SystemConfig


class WorldBackupManager:
    """Schedules and performs Minecraft world backups, keeping RCON calls in the main thread."""

    def __init__(self, minecraft_config: MinecraftConfig, system_config: SystemConfig):
        self.minecraft_config = minecraft_config
        self.system_config = system_config
        self.running = False
        self.mcr = None

    def start(self) -> None:
        """Start the backup scheduling thread."""
        while self.mcr is None:
            try:
                time.sleep(self.minecraft_config.backup_period * 60)
                self.mcr = MCRcon(host="localhost", password="test", port=25575)
                self.mcr.connect()
            except Exception as e:
                self.mcr = None
                print(f"⚠️ Failed to initialize RCON client: {e}")
        self._run()

    def stop(self) -> None:
        """Stop the RCON client connection."""
        if self.mcr:
            self.running = False
            self.mcr.disconnect()
            self.mcr = None

    def _run(self) -> None:
        """Run the backup scheduler in the main thread."""
        self.running = True
        while self.running:
            self._perform_backup()
            time.sleep(self.minecraft_config.backup_period * 60)

    def _perform_backup(self) -> None:
        """Perform a backup of the world directory."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            zip_path = self.system_config.backup_path / f"world-backup-{timestamp}.zip"
            with MCRcon(host="localhost", password="test", port=25575) as mcr:
                mcr.command("say Backup is running!")
                mcr.command("save-off")
                mcr.command("save-all")
                with zipfile.ZipFile(
                    zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
                ) as zipf:
                    for root, _, files in os.walk("/data/world"):
                        for file in files:
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, "/data/world")
                            zipf.write(full_path, arcname=rel_path)
                mcr.command("save-on")
                mcr.command("say Backup is finished!")
        except Exception as e:
            print(f"Backup failed ❌: {e}")
