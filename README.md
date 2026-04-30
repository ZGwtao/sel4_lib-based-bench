
First, do what is recorded in https://docs.sel4.systems/projects/sel4test/
Also make sure you have already setup python venv and seL4-dependency.

(https://docs.sel4.systems/projects/buildsystem/host-dependencies.html)

You may also install required dependency at `requirements.txt`

Setup the repo with `git submodule update --init --recursive`

Then at root directory, do:

```
$ mkdir build
$ cd build
```

then, pick one available configuration from `config.txt`

e.g.,

../init-build.sh \
    -DHardwareDebugAPI=OFF -DKernelDebugBuild=OFF \
    -DKernelVerificationBuild=OFF \
    -DMCS=ON -DKernelBenchmarks=generic \
    -DPLATFORM=odroidc4 -DBuildBenchmarks=ON \
    -DKernelFastpath=ON -DKernelSignalFastpath=ON \
    -DKernelArmExportPMUUser=ON \
    -DKernelArmHypervisorSupport=ON \
    -DNumCores=1 -DSMP=OFF -DWhichBenchmark=0 \
    -DCROSS_COMPILER_PREFIX=aarch64-none-linux-gnu- \
    -DRELEASE=ON

You also need to manually change the kernel version if you want to test the 
performance of seL4 ppc based on kernels different than 13.0.0 etc.

Recommended binutils version == 2.38.0 (not applicable to Ubuntu 24)

This project helps you compare the performance of SMP vs unicore on seL4_libs ecosystem
