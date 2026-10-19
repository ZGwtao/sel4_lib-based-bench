This repository provides a reproducible build and benchmarking environment for studying how compiler code generation and kernel configuration affect the seL4 IPC fastpath.  It includes:

- pinned seL4 16.0.0-compatible source dependencies;
- GCC 11.3/binutils 2.38 and GCC 15.2/binutils 2.45 toolchains;
- repeatable kernel and application image builds;
- selectable kernel optimisation variants.

The current system-level experiment matrix compares:

- GCC 11.3 versus GCC 15.2;
- one-core SMP versus a unicore kernel; and
- Arm hypervisor support enabled versus disabled.

Each build produces a complete seL4 boot image containing the elfloader, kernel, fglbench root task, and benchset application.  This project currently targets the ODROID-C4/AArch64 platform and focuses on the single-core IPC ping-pong path.

## Quick start

The following sequence starts from a fresh clone and builds benchmark 0 with GCC 15, one-core SMP, hypervisor support disabled, and the default kernel variant (for available branches, see [Section 4](#4-create-the-kernel-experiment-branches)).

```sh
git clone --recursive <repository-url> sel4-ipc-fastpath-lab
cd sel4-ipc-fastpath-lab

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

For a new clone, initialise the submodules and apply the repository's sel4test integration patch:

```sh
make setup
```

This target performs three operations:

1. resets all submodules to the commits recorded by the repository;
2. creates the `fglbench` and `benchset` links under sel4test; and
3. applies the patches under `patches/` to their corresponding submodules.

`make setup` is intended for initial setup or an intentional reset.  Its `reset` stage discards uncommitted changes inside submodules.  Do not rerun it after editing `kernel/` or another submodule unless those changes have been committed or saved elsewhere.

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

Create the local branches used by the selectable kernel optimisation experiments:

```sh
make kernel-variants
```

This Make target runs `tools/setup_kernel_variants.py`.

### Selectable kernel optimisation variants

The framework currently supports three optimisation points.  The two hook points share one switch, so each `getCurrentCPUIndex()` strategy can be combined with either default hooks or always-inline hooks:

| Optimisation point | Scope | Selectable strategies |
|---|---|---|
| `getCurrentCPUIndex()` | AArch64 SMP CPU-index lookup | Default (`static inline CONST`); force inline (`FORCE_INLINE`); no inline (`NO_INLINE`); non-volatile asm (default inline declaration, `asm` instead of `asm volatile`) |
| `arch_c_entry_hook()` / `arch_c_exit_hook()` | ARM entry/exit hook | Default (`static inline`); always inline (`FORCE_INLINE`) |
| `c_entry_hook()` / `c_exit_hook()` | Generic entry/exit hook | Default (`static inline`); always inline (`FORCE_INLINE`) |

The setup script creates eight branches from the seL4 `16.0.0` tag: `v16-getcurrentcpu-{default,force-inline,no-inline,nonvolatile-asm}` for default hooks, plus the same four names with `-hooks-inline` appended for always-inline hooks.  Both hook points always use the same strategy in a branch.

The source patches are stored in `seL4-patch/aarch64/`.  The default CPU patch is an empty marker commit, so it identifies the baseline without changing kernel source.  Each `-hooks-inline` branch applies its CPU patch followed by separate patches for the ARM and generic hooks.

The setup script is safe to rerun: existing branches are skipped.  It refuses to switch branches if `kernel/` contains uncommitted changes and restores the original kernel branch before exiting.

Branch creation and image building are deliberately separate.  The setup script creates reproducible source variants; `build_variant.py` only selects an existing branch and builds it.

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

Although the SMP experiment uses `NumCores=1`, an SMP-enabled kernel still executes SMP-specific kernel paths.  This is intentional: it isolates the cost of enabling SMP from the workload scaling effects of using additional cores.

### Build-directory naming

Unless `--build-dir` is supplied, each combination receives a separate path:

```text
builds/<compiler>-<smp|unicore>-<hyp|nohyp>-<kernel-branch>/
```

Keeping the branch name in the path prevents CMake caches and binaries from different inline variants from overwriting one another.  If you provide a custom `--build-dir`, use a distinct directory for every experimental variant.

## Benchmarks

<strong>These benchmarks are derived from the sel4test-based <a href="https://github.com/JE-Archer/sel4test/tree/fgs">fglbench</a> written by James Archer in 2022–2023.  It was originally developed to compare the performance of IPC operations on multicore fine-grained-locking and SMP kernels.  This repository currently uses only its single-core IPC ping-pong component.</strong>

Most workloads report completed loop iterations during a timer interval and an average cycle cost derived from that count.  Benchmark 3 is different: it reads the cycle counter around each IPC round trip and reports the maximum observed cost.

There are two kinds of workload in this benchmark: (1) the `_nc` workloads run the measured worker on one core and place a contender (which is a worker that repeatedly invokes `seL4_TCB_CopyRegisters()`) on every other configured core, and (2) the `_1c` workloads reserve only the last configured core for one contender and run measured workers on the preceding cores. With `NumCores=1`, `_1c` has no contender and reduces to one measured worker on core 0.

The workload dispatch table in `fglbench/src/main.c` is:

| Number | Function | What it benchmarks |
|---:|---|---|
| 0 | `bm_ipc_tp` | Cross-address-space IPC fastpath throughput.  For every configured core, an fglbench client repeatedly executes `seL4_Call()` to a separate benchset process whose server loops in `seL4_ReplyRecv()`.  This is the primary Call/ReplyRecv round-trip experiment. |
| 1 | `bm_ipc_tp_nc` | Same-address-space IPC throughput under contention.  A client/server thread pair performs `seL4_Call()`/`seL4_ReplyRecv()` on core 0, while every remaining core runs a `seL4_TCB_CopyRegisters()` contender. |
| 2 | `bm_ipc_tp_1c` | Same-address-space IPC throughput with one contender core.  IPC ping-pong pairs run on the measured cores and the final core runs one `seL4_TCB_CopyRegisters()` contender. |
| 3 | `bm_ipc_max_nc` | Worst observed same-address-space IPC round-trip latency.  The client measures cycles around each `seL4_Call()` on core 0; all remaining cores run contenders.  It reports maximum cycles rather than throughput. |
| 4 | `bm_signal_tp` | Uncontended `seL4_Signal()` throughput.  One thread per configured core repeatedly signals its own notification, with no waiting receiver. |
| 5 | `bm_signal_tp_nc` | `seL4_Signal()` throughput under contention.  The measured signal loop runs on core 0 and every remaining core runs a contender. |
| 6 | `bm_signal_tp_1c` | `seL4_Signal()` throughput with one contender core.  Signal loops occupy the measured cores and the final core runs one contender. |
| 7 | `bm_nbwait_tp` | `seL4_NBWait()` polling throughput.  One thread per configured core repeatedly performs a non-blocking wait on an otherwise unsignalled private notification. |
| 8 | `bm_nbsend_tp` | `seL4_NBSend()` throughput when no receiver is waiting.  One thread per configured core repeatedly performs a non-blocking send to its own endpoint. |
| 9 | `bm_send_and_recv_tp` | Blocking endpoint ping-pong throughput using separate `seL4_Send()` and `seL4_Recv()` calls between two threads on each core. |
| 10 | `bm_signal_and_wait_tp` | Notification ping-pong throughput using separate `seL4_Signal()` and `seL4_Wait()` calls between two threads on each core. |
| 11 | `bm_nbsendrecv_tp` | Combined `seL4_NBSendRecv()` loop throughput between two threads sharing an endpoint on each core. |

The notification ping-pong helpers named `bm_ntfn_tp*` are present in `benchmarks.c`, but they are not entries in the current dispatch table and therefore cannot be selected through `--benchmark`.

Select a workload with `--benchmark`, for example:

```sh
./build_variant.py \
    --compiler gcc15 --smp on --hyp off \
    --kernel-branch v16-getcurrentcpu-default \
    --benchmark 4
```

## Build all compiler/kernel-optimisation combinations

The following loop builds benchmark 0 for both compilers and all eight combinations of CPU-index and hook strategies, with SMP enabled and hypervisor support disabled:

```sh
for compiler in gcc11 gcc15; do
    for cpu in default force-inline no-inline nonvolatile-asm; do
        for hooks in "" -hooks-inline; do
            ./build_variant.py \
                --compiler "$compiler" \
                --smp on \
                --hyp off \
                --kernel-branch "v16-getcurrentcpu-${cpu}${hooks}" \
                --benchmark 0
        done
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

Deploy `images/fglbench-image-arm-odroidc4`, not `kernel/kernel.elf` by itself. The complete image already packages the kernel and user-level applications via the elfloader.

Copy or load that image using the ODROID-C4 boot mechanism used by your lab, for example an existing U-Boot/TFTP or removable-media workflow.  Board-side bootloader installation, network setup, and serial-console configuration are not currently automated by this repository.  A hypervisor-enabled kernel must also be entered at the exception level expected by that configuration.

On a successful run, the serial console should contain output similar to:

```text
FGLBENCH | Bootstrapped into environment.
FGLBENCH | Running benchmark 0 on 1 cores
...
FGLBENCH | ### Average cycle cost: ...
FGLBENCH | All is well in the universe
```

Record the full build variant together with every result: compiler, kernel branch, SMP setting, HYP setting, benchmark number, and kernel commit.

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

## Repository layout

```text
benchset/                 benchmark child process
fglbench/                 benchmark root task and workloads
kernel/                   seL4 kernel submodule
projects/                 seL4 userspace library submodules
patches/                  project integration patches used by make setup
seL4-patch/aarch64/       kernel experiment patches
tools/setup_kernel_variants.py  create local kernel experiment branches
tools/download_toolchains.py    download the two cross-compilers
build_variant.py          configure-and-build entry point
tc/                       downloaded toolchains (ignored)
builds/                   generated variant build trees (ignored)
```

Use `make help` and `./build_variant.py --help` for a concise command summary.
