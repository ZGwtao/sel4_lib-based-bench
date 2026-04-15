cmake_minimum_required(VERSION 3.7.2)

project(benchset C)

set(configure_string "")
add_config_library(benchset "${configure_string}")

file(
    GLOB
        deps
        src/*.c
)

add_executable(benchset EXCLUDE_FROM_ALL ${deps})

target_link_libraries(
    benchset
    PUBLIC
        sel4_autoconf
        muslc
        sel4
        sel4runtime
        sel4allocman
        sel4vka
        sel4utils
        sel4rpc
        sel4test
        sel4platsupport
        sel4muslcsys
        sel4testsupport
    PRIVATE benchset_Config
)
target_compile_options(benchset PRIVATE -Werror -O2)

