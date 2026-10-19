# seL4 IPC fastpath benchmark

This repository builds an IPC/notification benchmark for the Hardkernel
ODROID-C4.  It is intended for controlled comparisons of:

- GCC 11.3 versus GCC 15.2;
- one-core SMP versus a unicore kernel;
- Arm hypervisor support enabled versus disabled; and
- the default, forced-inline, and no-inline implementations of
  `getCurrentCPUIndex()`.

The build produces a complete seL4 boot image containing the elfloader, kernel,
fglbench root task, and benchset application.  The repository currently targets
the ODROID-C4/AArch64 platform and seL4 16.0.0.

## Quick start

The following sequence starts from a fresh clone and builds benchmark 0 with
GCC 15, one-core SMP, hypervisor support disabled, and the default kernel
variant.

```sh
git clone --recursive <repository-url> sel4_lib-based-bench
cd sel4_lib-based-bench

make setup
make venv
source .pyenv/bin/activate
make toolchain
make kernel-variants

./build_variant.py \
    --compiler gcc15 \
    --smp on \
    --hyp off \
    --kernel-branch v16-getcurrentcpu-default \
    --benchmark 0
```

The deployable image is then:

```text
builds/gcc15-smp-nohyp-v16-getcurrentcpu-default/
└── images/fglbench-image-arm-odroidc4
```

`build_variant.py` prints the exact image path when the build completes.

## 1. Initialise the source tree

For a new clone, initialise the submodules and apply the repository's sel4test
integration patch:

```sh
make setup
```

This target performs three operations:

1. resets all submodules to the commits recorded by the repository;
2. creates the `fglbench` and `benchset` links under sel4test; and
3. applies the patches under `patches/` to their corresponding submodules.

`make setup` is intended for initial setup or an intentional reset.  Its
`reset` stage discards uncommitted changes inside submodules.  Do not rerun it
after editing `kernel/` or another submodule unless those changes have been
committed or saved elsewhere.

The individual setup targets are also available:

```sh
make create-links
make apply-patches
```

## 2. Create the Python environment

```sh
make venv
source .pyenv/bin/activate
```

## 3. Download the cross-compilers

```sh
make toolchain
```

Both toolchains are downloaded into the ignored `tc/` directory:

| Build name | Install directory | Compiler | Binutils |
|---|---|---|---|
| `gcc11` | `tc/gcc11` | Arm GNU Toolchain 11.3.Rel1 | 2.38 |
| `gcc15` | `tc/gcc15` | Arm GNU Toolchain 15.2.Rel1 | 2.45 |

## 4. Create the kernel experiment branches

Create the three local branches used by the inline experiment:

```sh
make kernel-variants
```

This Make target runs `tools/setup_kernel_variants.py`.

The script creates the following branches from the seL4 `16.0.0` tag:

| Branch | `getCurrentCPUIndex()` declaration |
|---|---|
| `v16-getcurrentcpu-default` | `static inline CONST` |
| `v16-getcurrentcpu-force-inline` | `static inline CONST ... FORCE_INLINE` |
| `v16-getcurrentcpu-no-inline` | `static NO_INLINE CONST` |

The source patches are stored in `seL4-patch/aarch64/`.  The default patch is
an empty marker commit, so it identifies the baseline without changing kernel
source.

The setup script is safe to rerun: existing branches are skipped.  It refuses
to switch branches if `kernel/` contains uncommitted changes and restores the
original kernel branch before exiting.

Branch creation and image building are deliberately separate.  The setup
script creates reproducible source variants; `build_variant.py` only selects
an existing branch and builds it.

## 5. Build an image

The general command is:

```sh
./build_variant.py \
    --compiler {gcc11,gcc15} \
    --smp {on,off} \
    --hyp {on,off} \
    --kernel-branch <local-kernel-branch> \
    --benchmark <number>
```

For example, build the GCC 11 no-inline variant:

```sh
./build_variant.py \
    --compiler gcc11 \
    --smp on \
    --hyp off \
    --kernel-branch v16-getcurrentcpu-no-inline \
    --benchmark 0 \
    --jobs 8
```

### Build dimensions

| Option | Values | Meaning |
|---|---|---|
| `--compiler` | `gcc11`, `gcc15` | Selects the repository-local compiler and matching binutils. |
| `--smp` | `on`, `off` | Enables SMP support or builds a unicore kernel. Both use one benchmark core. |
| `--hyp` | `on`, `off` | Enables or disables Arm kernel hypervisor support. |
| `--kernel-branch` | local branch name | Selects an existing branch in `kernel/`. |
| `--benchmark` | integer | Selects the fglbench workload; the default is 0. |
| `--jobs`, `-j` | positive integer | Sets Ninja parallelism. |
| `--build-dir` | path | Overrides the automatically generated build directory. |
| `--configure-only` | flag | Runs CMake without Ninja. |
| `--dry-run` | flag | Prints the branch switch and build commands without executing them. |

Although the SMP experiment uses `NumCores=1`, an SMP-enabled kernel still
executes SMP-specific kernel paths.  This is intentional: it isolates the cost
of enabling SMP from the workload scaling effects of using additional cores.

### Build-directory naming

Unless `--build-dir` is supplied, each combination receives a separate path:

```text
builds/<compiler>-<smp|unicore>-<hyp|nohyp>-<kernel-branch>/
```

Keeping the branch name in the path prevents CMake caches and binaries from
different inline variants from overwriting one another.  If you provide a
custom `--build-dir`, use a distinct directory for every experimental variant.

## Benchmarks

Benchmark 0 is the primary IPC fastpath experiment: the client performs
`seL4_Call()` while the server repeatedly performs `seL4_ReplyRecv()`.

The current workload table in `fglbench/src/main.c` is:

| Number | Function |
|---:|---|
| 0 | `bm_ipc_tp` |
| 1 | `bm_ipc_tp_nc` |
| 2 | `bm_ipc_tp_1c` |
| 3 | `bm_ipc_max_nc` |
| 4 | `bm_signal_tp` |
| 5 | `bm_signal_tp_nc` |
| 6 | `bm_signal_tp_1c` |
| 7 | `bm_nbwait_tp` |
| 8 | `bm_nbsend_tp` |
| 9 | `bm_send_and_recv_tp` |
| 10 | `bm_signal_and_wait_tp` |
| 11 | `bm_nbsendrecv_tp` |

Select a workload with `--benchmark`, for example:

```sh
./build_variant.py \
    --compiler gcc15 --smp on --hyp off \
    --kernel-branch v16-getcurrentcpu-default \
    --benchmark 4
```

## Build all compiler/inline combinations

The following loop builds benchmark 0 for both compilers and all three inline
variants, with SMP enabled and hypervisor support disabled:

```sh
for compiler in gcc11 gcc15; do
    for branch in \
        v16-getcurrentcpu-default \
        v16-getcurrentcpu-force-inline \
        v16-getcurrentcpu-no-inline
    do
        ./build_variant.py \
            --compiler "$compiler" \
            --smp on \
            --hyp off \
            --kernel-branch "$branch" \
            --benchmark 0
    done
done
```

To compare the four one-core kernel configurations, repeat a build with:

```text
--smp on  --hyp off
--smp off --hyp off
--smp on  --hyp on
--smp off --hyp on
```

## Build products and deployment

Each successful build contains:

| Product | Relative path inside the build directory |
|---|---|
| Complete bootable/deployable image | `images/fglbench-image-arm-odroidc4` |
| seL4 kernel ELF | `kernel/kernel.elf` |
| fglbench root task | `apps/fglbench/fglbench` |
| benchset process | `apps/fglbench/benchset/benchset` |
| elfloader | `elfloader/elfloader` |
| Generated kernel configuration | `kernel/gen_config.h` |

Deploy `images/fglbench-image-arm-odroidc4`, not `kernel/kernel.elf` by itself.
The complete image already packages the kernel and user-level applications via
the elfloader.

Copy or load that image using the ODROID-C4 boot mechanism used by your lab,
for example an existing U-Boot/TFTP or removable-media workflow.  Board-side
bootloader installation, network setup, and serial-console configuration are
not currently automated by this repository.  A hypervisor-enabled kernel must
also be entered at the exception level expected by that configuration.

On a successful run, the serial console should contain output similar to:

```text
FGLBENCH | Bootstrapped into environment.
FGLBENCH | Running benchmark 0 on 1 cores
...
FGLBENCH | ### Average cycle cost: ...
FGLBENCH | All is well in the universe
```

Record the full build variant together with every result: compiler, kernel
branch, SMP setting, HYP setting, benchmark number, and kernel commit.

## Compare fastpath instruction streams

`tools/analyze_fastpath.py` compares already-built kernels; it does not rebuild
or modify them.  Pass two or more build directories, `kernel.elf` files, or
complete `fglbench-image-arm-odroidc4` paths.  The first input is the baseline.

For example, compare the GCC 11 and GCC 15 no-inline builds:

```sh
./tools/analyze_fastpath.py \
    --output-dir fastpath-analysis/noinline-gcc11-vs-gcc15 \
    builds/gcc11-smp-nohyp-v16-getcurrentcpu-no-inline \
    builds/gcc15-smp-nohyp-v16-getcurrentcpu-no-inline
```

The script automatically:

1. resolves each input to its unstripped `kernel/kernel.elf`;
2. infers GCC 11 or GCC 15 and uses the matching repository-local `objdump`;
3. disassembles `c_handle_fastpath_call` and
   `c_handle_fastpath_reply_recv` by symbol name;
4. records instruction, byte, load, store, branch, call, TPIDR-read, and
   `getCurrentCPUIndex()` call counts;
5. normalises relocated addresses while retaining mnemonics, operands, branch
   structure, and symbolic call targets; and
6. compares every later input against the first input.

The output directory contains:

| File | Purpose |
|---|---|
| `comparison.md` | Human-readable summary table. |
| `summary.csv` | Metrics, call targets, and ELF paths. |
| `*.asm` | Raw `objdump` evidence. |
| `*.normalized.asm` | Address-normalised instruction streams. |
| `*.diff` | Unified instruction-stream diff against the baseline. |

This mirrors the manual comparison workflow used during development: preserve
the raw disassembly, compare aggregate shape first, then read the normalised
diff around the relevant control-flow paths.

The statistics cover the complete static function, including error and
slowpath branches.  They do **not** tell how many instructions execute during
one successful `Call`/`ReplyRecv` round trip.  Treat them as a way to locate
compiler/code-generation differences. Confirm a performance explanation with
hardware cycle measurements or a traced hot path rather than equating total
function length with runtime cost.

## Inspecting and reproducing a build

Show the selected kernel revision:

```sh
git -C kernel status --short --branch
git -C kernel rev-parse HEAD
```

Inspect the effective generated configuration:

```sh
less builds/<variant>/kernel/gen_config.h
less builds/<variant>/kernel/autoconf/autoconf.h
```

Inspect a fastpath symbol using the matching toolchain:

```sh
tc/gcc15/bin/aarch64-none-linux-gnu-objdump \
    -d --disassemble=c_handle_fastpath_call \
    builds/<variant>/kernel/kernel.elf
```

Use the GCC 11 `objdump` for a GCC 11 build when making compiler comparisons.

## Repository layout

```text
benchset/                 benchmark child process
fglbench/                 benchmark root task and workloads
kernel/                   seL4 kernel submodule
projects/                 seL4 userspace library submodules
patches/                  project integration patches used by make setup
seL4-patch/aarch64/       kernel experiment patches
tools/setup_kernel_variants.py  create local kernel experiment branches
tools/analyze_fastpath.py       compare kernel fastpath instruction streams
tools/download_toolchains.py    download the two cross-compilers
build_variant.py          configure-and-build entry point
tc/                       downloaded toolchains (ignored)
builds/                   generated variant build trees (ignored)
```

Use `make help` and `./build_variant.py --help` for a concise command summary.
