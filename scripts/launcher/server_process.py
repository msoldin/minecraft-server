from pathlib import Path
import subprocess
import sys
import threading
from typing import Optional
from .config import MinecraftConfig, SystemConfig


class ServerProcess:

    output_thread: Optional[threading.Thread] = None

    def __init__(self, minecraft_config: MinecraftConfig, system_config: SystemConfig):
        self.minecraft_config = minecraft_config
        self.system_config = system_config
        self.backup_thread = None

    def start(self) -> None:
        print(f"Launcher finished. Starting Minecraft server... 🚀")
        server_proc = self._run()
        self.output_thread = threading.Thread(
            target=self.relay_output, args=(server_proc,), daemon=True
        )
        self.output_thread.start()

    def _run(self) -> subprocess.Popen:
        java_cmd = [
            "java",
            f"-Xms{self.minecraft_config.memory_size}",
            f"-Xmx{self.minecraft_config.memory_size}",
            "-Dlog4j2.formatMsgNoLookups=true",
            "-XX:+UseZGC",
            "-XX:+AlwaysPreTouch",
            "-XX:+UseStringDeduplication",
            "-XX:+UseCompactObjectHeaders",
            "-jar",
            f"{self.system_config.server_dir}/{self.minecraft_config.minecraft_version}-server.jar",
            "nogui",
        ]
        server_proc = subprocess.Popen(
            java_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )
        return server_proc

    def write_eula(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        eula_path = data_dir / "eula.txt"

        if not eula_path.exists():
            with open(eula_path, "w") as f:
                f.write("eula=true\n")
            print(f"✅ eula.txt created at {eula_path}")
        else:
            print(f"ℹ️ eula.txt already exists at {eula_path}, skipping")

    def relay_output(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()  # flush immediately so it appears in console
