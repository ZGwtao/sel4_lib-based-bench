#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TOOLCHAINS_DIR = ROOT / "tc"

TOOLCHAINS = (
    {
        "name": "gcc11",
        "version": "11.3.1",
        "dir": "arm-gnu-toolchain-11.3.rel1-x86_64-aarch64-none-linux-gnu",
        "url": (
            "https://developer.arm.com/-/media/Files/downloads/gnu/11.3.rel1/binrel/"
            "arm-gnu-toolchain-11.3.rel1-x86_64-aarch64-none-linux-gnu.tar.xz"
        ),
    },
    {
        "name": "gcc15",
        "version": "15.2.1",
        "dir": "arm-gnu-toolchain-15.2.rel1-x86_64-aarch64-none-linux-gnu",
        "url": (
            "https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/"
            "arm-gnu-toolchain-15.2.rel1-x86_64-aarch64-none-linux-gnu.tar.xz"
        ),
    },
)


def is_installed(toolchain: dict[str, str]) -> bool:
    gcc = TOOLCHAINS_DIR / toolchain["name"] / "bin/aarch64-none-linux-gnu-gcc"
    if not gcc.is_file():
        return False

    try:
        version = subprocess.check_output(
            [gcc, "-dumpfullversion"], text=True
        ).strip()
        target = subprocess.check_output(
            [gcc, "-dumpmachine"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return False

    return version == toolchain["version"] and target == "aarch64-none-linux-gnu"


def download(target: dict[str, str]) -> None:
    if is_installed(target):
        print(f"{target['name']}: already installed, skipping")
        return

    d = TOOLCHAINS_DIR / target["name"]
    if d.exists():
        raise RuntimeError(f"{d} exists but not expected")

    print(f"{target['name']}: downloading to {d}", flush=True)

    with tempfile.TemporaryDirectory(dir=TOOLCHAINS_DIR) as t:
        a = Path(t) / "toolchain.tar.xz"
        urllib.request.urlretrieve(target["url"], a)

        with tarfile.open(a) as archive:
            archive.extractall(t)

        extracted = Path(t) / target["dir"]
        shutil.move(extracted, d)

    if not is_installed(target):
        raise RuntimeError(f"failed to install {target['name']}")


def main() -> None:
    TOOLCHAINS_DIR.mkdir(exist_ok=True)
    print(f"Toolchain directory: {TOOLCHAINS_DIR}", flush=True)
    for target in TOOLCHAINS:
        download(target)


if __name__ == "__main__":
    main()
