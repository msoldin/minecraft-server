from pathlib import Path

import requests


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
