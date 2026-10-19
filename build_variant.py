#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


PROJECT = Path(__file__).resolve().parent
TOOLCHAINS = PROJECT / "tc"
GCC11_ROOT = TOOLCHAINS / "gcc11"
GCC15_ROOT = TOOLCHAINS / "gcc15"
KERNEL = PROJECT / "kernel"


def on_off(value: str) -> bool:
    values = {"on": True, "off": False, "true": True, "false": False, "1": True, "0": False}
    try:
        return values[value.lower()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError("expected on/off") from exc


def run(command: list[str], *, cwd: Path, env: dict[str, str], dry_run: bool) -> None:
    print("+", " ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, cwd=cwd, env=env, check=True)


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(KERNEL), *args], text=True
    ).strip()


def select_kernel_branch(branch: str, *, dry_run: bool) -> None:
    """Select an existing local kernel branch without discarding changes."""
    try:
        git_output("show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    except subprocess.CalledProcessError:
        raise ValueError(f"kernel branch does not exist: {branch}") from None

    if git_output("status", "--porcelain"):
        raise ValueError(
            "kernel working tree has uncommitted changes; commit or stash them before "
            "using --kernel-branch"
        )

    run(["git", "switch", branch], cwd=KERNEL, env=os.environ.copy(), dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a one-core SMP/unicore, hyp/non-hyp benchmark variant."
    )
    parser.add_argument("--smp", required=True, type=on_off, metavar="on|off")
    parser.add_argument("--hyp", required=True, type=on_off, metavar="on|off")
    parser.add_argument("--compiler", required=True, choices=("gcc11", "gcc15"))
    parser.add_argument(
        "--kernel-branch",
        help="existing local branch in ./kernel to select before configuring",
    )
    parser.add_argument("--jobs", "-j", type=int, help="parallel Ninja jobs")
    parser.add_argument("--benchmark", type=int, default=0, help="WhichBenchmark value (default: 0)")
    parser.add_argument("--build-dir", type=Path, help="override the combination-specific build directory")
    parser.add_argument("--configure-only", action="store_true", help="configure without running Ninja")
    parser.add_argument("--dry-run", action="store_true", help="print commands without executing them")
    args = parser.parse_args()

    if args.kernel_branch:
        try:
            select_kernel_branch(args.kernel_branch, dry_run=args.dry_run)
        except ValueError as exc:
            parser.error(str(exc))

    smp_name = "smp" if args.smp else "unicore"
    hyp_name = "hyp" if args.hyp else "nohyp"
    branch_name = args.kernel_branch or "current-kernel"
    branch_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", branch_name).strip("-")
    default_build = (
        PROJECT / "builds" /
        f"{args.compiler}-{smp_name}-{hyp_name}-{branch_slug}"
    )
    build_dir = (args.build_dir or default_build).expanduser().resolve()

    toolchain_root = GCC11_ROOT if args.compiler == "gcc11" else GCC15_ROOT
    toolchain_bin = toolchain_root / "bin"
    prefix = "aarch64-none-linux-gnu-"
    cc = toolchain_bin / f"{prefix}gcc"
    ld = toolchain_bin / f"{prefix}ld"

    for required in (PROJECT / "init-build.sh", cc, ld):
        if not required.exists():
            parser.error(f"required file not found: {required}")

    if not args.dry_run:
        build_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    pyenv_bin = PROJECT / ".pyenv/bin"
    env["PATH"] = os.pathsep.join((str(toolchain_bin), str(pyenv_bin), "/usr/bin", "/bin"))

    cmake_args = [
        str(PROJECT / "init-build.sh"),
        "-DMCS=ON",
        "-DRELEASE=ON",
        "-DKernelDebugBuild=OFF",
        "-DKernelVerificationBuild=OFF",
        "-DHardwareDebugAPI=OFF",
        "-DKernelBenchmarks=generic",
        "-DPLATFORM=odroidc4",
        "-DBuildBenchmarks=ON",
        "-DKernelFastpath=ON",
        "-DKernelSignalFastpath=ON",
        "-DKernelArmExportPMUUser=ON",
        f"-DARM_HYP={'ON' if args.hyp else 'OFF'}",
        f"-DKernelArmHypervisorSupport={'ON' if args.hyp else 'OFF'}",
        f"-DNUM_NODES={4 if args.smp else 1}",
        "-DNumCores=1",
        f"-DSMP={'ON' if args.smp else 'OFF'}",
        f"-DWhichBenchmark={args.benchmark}",
        f"-DCROSS_COMPILER_PREFIX={prefix}",
        "-DCMAKE_C_FLAGS=-Wno-error=array-bounds",
    ]
    selected_branch = args.kernel_branch or git_output("branch", "--show-current") or "detached HEAD"
    print(
        f"Variant:  compiler={args.compiler}, SMP={args.smp}, HYP={args.hyp}, "
        f"cores=1, kernel={selected_branch}"
    )
    print(f"Build:    {build_dir}")
    if not args.dry_run:
        print("Compiler:", subprocess.check_output([str(cc), "--version"], text=True).splitlines()[0])
        print("Linker:  ", subprocess.check_output([str(ld), "--version"], text=True).splitlines()[0])

    run(cmake_args, cwd=build_dir, env=env, dry_run=args.dry_run)
    if not args.configure_only:
        ninja = [shutil.which("ninja", path=env["PATH"]) or "ninja", "-C", str(build_dir)]
        if args.jobs is not None:
            if args.jobs < 1:
                parser.error("--jobs must be at least 1")
            ninja.extend(("-j", str(args.jobs)))
        run(ninja, cwd=PROJECT, env=env, dry_run=args.dry_run)

    print(f"Image:    {build_dir / 'images/fglbench-image-arm-odroidc4'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed with exit status {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
