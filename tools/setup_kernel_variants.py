#!/usr/bin/env python3

from pathlib import Path
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
KERNEL = PROJECT / "kernel"
PATCH_DIR = PROJECT / "seL4-patch" / "aarch64"
BASE = "16.0.0"

CPU_VARIANTS = (
    (
        "v16-getcurrentcpu-default",
        "0001-aarch64-smp-default-getCurrentCPUIndex.patch",
    ),
    (
        "v16-getcurrentcpu-force-inline",
        "0001-aarch64-smp-force-inlining-getCurrentCPUIndex.patch",
    ),
    (
        "v16-getcurrentcpu-no-inline",
        "0001-aarch64-smp-no-inlining-getCurrentCPUIndex.patch",
    ),
    (
        "v16-getcurrentcpu-nonvolatile-asm",
        "0001-aarch64-smp-nonvolatile-asm-getCurrentCPUIndex.patch",
    ),
)

HOOK_PATCHES = (
    "0001-arm-force-inlining-arch-c-hooks.patch",
    "0002-force-inlining-c-hooks.patch",
)

VARIANTS = tuple(
    (branch, (cpu_patch,))
    for branch, cpu_patch in CPU_VARIANTS
) + tuple(
    (f"{branch}-hooks-inline", (cpu_patch, *HOOK_PATCHES))
    for branch, cpu_patch in CPU_VARIANTS
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(KERNEL), *args]
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, text=True, check=check)


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(KERNEL), *args], text=True
    ).strip()


def branch_exists(branch: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(KERNEL),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        check=False,
    )
    return result.returncode == 0


def create_variant(branch: str, patches: tuple[Path, ...]) -> None:
    git("switch", "--create", branch, BASE)
    try:
        # --empty=keep lets the default variant use an empty marker commit.
        for patch in patches:
            git("am", "--empty=keep", str(patch))
    except subprocess.CalledProcessError:
        git("am", "--abort", check=False)
        git("switch", "--detach", BASE)
        git("branch", "--delete", "--force", branch)
        raise


def main() -> int:
    if not (KERNEL / ".git").exists():
        print(f"error: kernel Git repository not found: {KERNEL}", file=sys.stderr)
        return 1

    if git_output("status", "--porcelain"):
        print(
            "error: kernel has uncommitted changes; commit or stash them first",
            file=sys.stderr,
        )
        return 1

    try:
        git_output("rev-parse", "--verify", f"{BASE}^{{commit}}")
    except subprocess.CalledProcessError:
        print(f"error: kernel tag not found: {BASE}", file=sys.stderr)
        return 1

    for _, patch_names in VARIANTS:
        for patch_name in patch_names:
            patch = PATCH_DIR / patch_name
            if not patch.is_file():
                print(f"error: patch not found: {patch}", file=sys.stderr)
                return 1

    original_branch = git_output("branch", "--show-current")
    original_commit = git_output("rev-parse", "HEAD")

    try:
        for branch, patch_names in VARIANTS:
            if branch_exists(branch):
                print(f"Skipping existing branch: {branch}")
                continue
            print(f"Creating branch: {branch}")
            create_variant(branch, tuple(PATCH_DIR / name for name in patch_names))
    finally:
        if original_branch:
            git("switch", original_branch)
        else:
            git("switch", "--detach", original_commit)

    print("Kernel variants are ready:")
    for branch, _ in VARIANTS:
        print(f"  {branch}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed with exit status {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
