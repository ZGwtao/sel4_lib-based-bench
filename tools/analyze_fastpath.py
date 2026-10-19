#!/usr/bin/env python3

import argparse
import csv
from dataclasses import dataclass
import difflib
from pathlib import Path
import re
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
TOOLCHAINS = PROJECT / "tc"
SYMBOLS = ("c_handle_fastpath_call", "c_handle_fastpath_reply_recv")

OBJDUMPS = {
    "gcc11": TOOLCHAINS / "gcc11/bin/aarch64-none-linux-gnu-objdump",
    "gcc15": TOOLCHAINS / "gcc15/bin/aarch64-none-linux-gnu-objdump",
}

INSTRUCTION_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+([.a-zA-Z0-9_]+)(?:\s+(.*?))?\s*$"
)
SYMBOL_TARGET_RE = re.compile(r"(?:0x)?[0-9a-f]+\s+<([^>]+)>")
PLAIN_TARGET_RE = re.compile(r"^(?:0x)?([0-9a-f]+)(.*)$")


@dataclass(frozen=True)
class InputImage:
    label: str
    original: Path
    build_dir: Path | None
    elf: Path
    compiler: str
    objdump: Path


@dataclass(frozen=True)
class Instruction:
    address: int
    opcode: str
    mnemonic: str
    operands: str


def resolve_elf(path: Path) -> tuple[Path, Path | None]:
    path = path.expanduser().resolve()
    if path.is_dir():
        candidates = (path / "kernel/kernel.elf", path / "kernel.elf")
        for candidate in candidates:
            if candidate.is_file():
                return candidate, path
        raise ValueError(f"no kernel.elf found below build directory: {path}")

    if not path.is_file():
        raise ValueError(f"input does not exist: {path}")

    if path.name == "kernel.elf":
        build_dir = path.parent.parent if path.parent.name == "kernel" else None
        return path, build_dir

    if path.name.startswith("fglbench-image-") and path.parent.name == "images":
        build_dir = path.parent.parent
        elf = build_dir / "kernel/kernel.elf"
        if elf.is_file():
            return elf, build_dir
        raise ValueError(
            f"the deployable image is stripped/packed; sibling kernel ELF not found: {elf}"
        )

    raise ValueError(
        f"expected a build directory, kernel.elf, or fglbench-image path: {path}"
    )


def detect_compiler(path: Path, build_dir: Path | None) -> str:
    searchable = " ".join(str(item) for item in (path, build_dir) if item is not None)
    matches = [name for name in OBJDUMPS if name in searchable.lower()]
    if len(matches) == 1:
        return matches[0]

    if build_dir is not None:
        cache = build_dir / "CMakeCache.txt"
        if cache.is_file():
            text = cache.read_text(errors="replace")
            if "11.3.rel1" in text or "/11.3.1/" in text:
                return "gcc11"
            if "15.2.rel1" in text or "/15.2.1/" in text:
                return "gcc15"

    raise ValueError(
        f"cannot infer gcc11/gcc15 from {path}; use a standard build_variant.py directory"
    )


def unique_label(path: Path, build_dir: Path | None, used: set[str]) -> str:
    base = (build_dir or path).name
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-") or "image"
    candidate = label
    number = 2
    while candidate in used:
        candidate = f"{label}-{number}"
        number += 1
    used.add(candidate)
    return candidate


def resolve_input(path: Path, used_labels: set[str]) -> InputImage:
    elf, build_dir = resolve_elf(path)
    compiler = detect_compiler(path.resolve(), build_dir)
    objdump = OBJDUMPS[compiler]
    if not objdump.is_file():
        raise ValueError(f"{compiler} objdump not found; run `make toolchain`: {objdump}")
    return InputImage(
        label=unique_label(path.resolve(), build_dir, used_labels),
        original=path.resolve(),
        build_dir=build_dir,
        elf=elf,
        compiler=compiler,
        objdump=objdump,
    )


def disassemble(image: InputImage, symbol: str) -> str:
    result = subprocess.run(
        [str(image.objdump), "-d", f"--disassemble={symbol}", str(image.elf)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    if f"<{symbol}>:" not in result.stdout:
        raise RuntimeError(f"symbol not found in {image.elf}: {symbol}")
    return result.stdout


def parse_instructions(disassembly: str) -> list[Instruction]:
    instructions: list[Instruction] = []
    for line in disassembly.splitlines():
        match = INSTRUCTION_RE.match(line)
        if match:
            instructions.append(
                Instruction(
                    address=int(match.group(1), 16),
                    opcode=match.group(2),
                    mnemonic=match.group(3),
                    operands=match.group(4) or "",
                )
            )
    return instructions


def is_branch(mnemonic: str) -> bool:
    return (
        mnemonic in {"b", "bl", "blr", "br", "ret", "eret"}
        or mnemonic.startswith("b.")
        or mnemonic.startswith("cb")
        or mnemonic.startswith("tb")
    )


def normalise_instruction(instruction: Instruction, start: int) -> str:
    operands = instruction.operands
    symbol_match = SYMBOL_TARGET_RE.search(operands)
    if symbol_match and is_branch(instruction.mnemonic):
        operands = SYMBOL_TARGET_RE.sub(f"<{symbol_match.group(1)}>", operands)
    elif is_branch(instruction.mnemonic):
        target_match = PLAIN_TARGET_RE.match(operands)
        if target_match:
            target = int(target_match.group(1), 16)
            suffix = target_match.group(2)
            operands = f"<function+0x{target - start:x}>{suffix}"
    return f"{instruction.mnemonic}\t{operands}".rstrip()


def call_targets(instructions: list[Instruction]) -> list[str]:
    targets: list[str] = []
    for instruction in instructions:
        if instruction.mnemonic not in {"bl", "blr"}:
            continue
        match = SYMBOL_TARGET_RE.search(instruction.operands)
        targets.append(match.group(1) if match else instruction.operands)
    return targets


def collect_metrics(
    image: InputImage, symbol: str, instructions: list[Instruction]
) -> dict[str, str | int]:
    mnemonics = [instruction.mnemonic for instruction in instructions]
    operands = [instruction.operands for instruction in instructions]
    calls = call_targets(instructions)
    return {
        "label": image.label,
        "compiler": image.compiler,
        "symbol": symbol,
        "instructions": len(instructions),
        "bytes": sum(len(instruction.opcode) // 2 for instruction in instructions),
        "loads": sum(mnemonic.startswith("ld") for mnemonic in mnemonics),
        "stores": sum(mnemonic.startswith("st") for mnemonic in mnemonics),
        "branches": sum(is_branch(mnemonic) for mnemonic in mnemonics),
        "calls": sum(mnemonic in {"bl", "blr"} for mnemonic in mnemonics),
        "mrs": mnemonics.count("mrs"),
        "msr": mnemonics.count("msr"),
        "tpidr_el1": sum("tpidr_el1" in operand for operand in operands),
        "tpidr_el2": sum("tpidr_el2" in operand for operand in operands),
        "getcpu_calls": sum("getCurrentCPUIndex" in target for target in calls),
        "call_targets": ";".join(calls),
        "elf": str(image.elf),
    }


def write_markdown(
    path: Path,
    images: list[InputImage],
    rows: list[dict[str, str | int]],
) -> None:
    lines = [
        "# Static fastpath instruction comparison",
        "",
        "The first input is the comparison baseline. Counts cover the complete static",
        "function, including cold/error paths; they are not dynamic executed-instruction",
        "counts for one successful IPC operation.",
        "",
        "## Inputs",
        "",
    ]
    for image in images:
        lines.append(f"- `{image.label}`: {image.compiler}, `{image.elf}`")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Image | Symbol | Instructions | Bytes | Loads | Stores | Branches | Calls | TPIDR_EL1 | TPIDR_EL2 | getCPU calls |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['label']} | `{row['symbol']}` | {row['instructions']} | "
            f"{row['bytes']} | {row['loads']} | {row['stores']} | "
            f"{row['branches']} | {row['calls']} | {row['tpidr_el1']} | "
            f"{row['tpidr_el2']} | {row['getcpu_calls']} |"
        )

    lines.extend(
        [
            "## Files",
            "",
            "- `*.asm`: raw objdump output with addresses and opcodes.",
            "- `*.normalized.asm`: mnemonic/operand streams with relocated addresses normalised.",
            "- `*.diff`: unified normalized-stream diff against the first input.",
            "- `summary.csv`: machine-readable metrics and call targets.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="build directories, kernel.elf files, or fglbench-image paths",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT / "fastpath-analysis",
        help="report directory (default: ./fastpath-analysis)",
    )
    args = parser.parse_args()

    used_labels: set[str] = set()
    try:
        images = [resolve_input(path, used_labels) for path in args.inputs]
    except ValueError as exc:
        parser.error(str(exc))

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str | int]] = []
    streams: dict[tuple[str, str], list[str]] = {}

    for symbol in SYMBOLS:
        for image in images:
            print(f"Analysing {image.label}: {symbol}")
            raw = disassemble(image, symbol)
            instructions = parse_instructions(raw)
            if not instructions:
                raise RuntimeError(f"no instructions parsed for {symbol} in {image.elf}")

            start = instructions[0].address
            normalised = [normalise_instruction(item, start) for item in instructions]
            streams[(image.label, symbol)] = normalised

            stem = f"{image.label}.{symbol}"
            (output_dir / f"{stem}.asm").write_text(raw)
            (output_dir / f"{stem}.normalized.asm").write_text(
                "\n".join(normalised) + "\n"
            )
            rows.append(collect_metrics(image, symbol, instructions))

    fields = list(rows[0])
    with (output_dir / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    baseline = images[0]
    for image in images[1:]:
        for symbol in SYMBOLS:
            before = streams[(baseline.label, symbol)]
            after = streams[(image.label, symbol)]
            diff = difflib.unified_diff(
                before,
                after,
                fromfile=f"{baseline.label}/{symbol}",
                tofile=f"{image.label}/{symbol}",
                lineterm="",
                n=3,
            )
            (output_dir / f"{baseline.label}-vs-{image.label}.{symbol}.diff").write_text(
                "\n".join(diff) + "\n"
            )

    write_markdown(output_dir / "comparison.md", images, rows)

    print()
    print("Image / symbol                              insn  load store branch TPIDR getCPU")
    for row in rows:
        name = f"{row['label']} / {row['symbol']}"
        tpidr = int(row["tpidr_el1"]) + int(row["tpidr_el2"])
        print(
            f"{name:<43} {row['instructions']:>4} "
            f"{row['loads']:>5} {row['stores']:>5} {row['branches']:>6} "
            f"{tpidr:>5} {row['getcpu_calls']:>6}"
        )
    print(f"\nReport: {output_dir / 'comparison.md'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
