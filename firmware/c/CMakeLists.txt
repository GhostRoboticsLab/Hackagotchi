cmake_minimum_required(VERSION 3.12)

# Hackagotchi probe — FORK of raspberrypi/debugprobe @ debugprobe-v2.2.3.
#
# This is an OVERLAY build: the pristine upstream tree is fetched (gitignored) by ./setup.sh into
# upstream/debugprobe; this project compiles upstream's sources EXCEPT main.c, which we fork
# (OUR src/main.c is compiled explicitly below instead of upstream's). The board pin map is injected
# WITHOUT touching upstream via boards/board_debug_probe_config.h — upstream's probe_config.h does
# `#include "board_debug_probe_config.h"` (not adjacent to it), so our boards/ copy shadows it on the
# -I path. Plus the Gate-1 OLED coexistence task (src/hackagotchi_dashboard.c) + vendored SSD1306.
#
# Build via ./build_fork.sh (pins Arm GCC 13.3.Rel1 + the existing pico-sdk 2.2.0). See
# docs/engineering-plan.md §6 (GATE 1).

set(UPSTREAM ${CMAKE_CURRENT_LIST_DIR}/upstream/debugprobe)
if (NOT EXISTS ${UPSTREAM}/CMakeLists.txt)
    message(FATAL_ERROR "upstream/debugprobe not found — run ./setup.sh first (fetches debugprobe-v2.2.3).")
endif ()

include(${UPSTREAM}/pico_sdk_import.cmake)

set(FREERTOS_KERNEL_PATH ${UPSTREAM}/freertos)
include(${UPSTREAM}/FreeRTOS_Kernel_import.cmake)

project(hackagotchi_probe C CXX ASM)

pico_sdk_init()

if (${PICO_SDK_VERSION_MAJOR} LESS 2)
    message(SEND_ERROR "Version 2 of the Pico SDK is required.")
endif ()

# Optional adversarial stress: a busy_wait_us(ms*1000) per OLED loop (the "slow SD write" proxy).
# Default 0 (off). Build the 50 ms variant with: cmake -DADVERSARIAL_STALL_MS=50 …
set(ADVERSARIAL_STALL_MS 0 CACHE STRING "Gate-1 adversarial stall (ms) injected into the OLED task")

add_executable(hackagotchi_probe
        # --- OUR overlay (shadows upstream main.c/probe_config.h; adds the OLED coexistence task) ---
        ${CMAKE_CURRENT_LIST_DIR}/src/main.c
        ${CMAKE_CURRENT_LIST_DIR}/src/hackagotchi_dashboard.c
        ${CMAKE_CURRENT_LIST_DIR}/src/ssd1306/ssd1306.c
        # --- pristine upstream debugprobe sources ---
        ${UPSTREAM}/src/probe_config.c
        ${UPSTREAM}/src/usb_descriptors.c
        ${UPSTREAM}/src/probe.c
        ${UPSTREAM}/src/cdc_uart.c
        ${UPSTREAM}/src/get_serial.c
        ${UPSTREAM}/src/sw_dp_pio.c
        ${UPSTREAM}/src/tusb_edpt_handler.c
)

target_sources(hackagotchi_probe PRIVATE
        ${UPSTREAM}/CMSIS_DAP/CMSIS/DAP/Firmware/Source/DAP.c
        ${UPSTREAM}/CMSIS_DAP/CMSIS/DAP/Firmware/Source/JTAG_DP.c
        ${UPSTREAM}/CMSIS_DAP/CMSIS/DAP/Firmware/Source/DAP_vendor.c
        ${UPSTREAM}/CMSIS_DAP/CMSIS/DAP/Firmware/Source/SWO.c
)

# Include-path ORDER is load-bearing: OUR src/ + boards/ come BEFORE upstream so our probe_config.h
# (and board_hackagotchi_config.h) shadow the upstream defaults.
target_include_directories(hackagotchi_probe PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}/src
        ${CMAKE_CURRENT_LIST_DIR}/boards
        ${CMAKE_CURRENT_LIST_DIR}/src/ssd1306
        ${UPSTREAM}/include/
        ${UPSTREAM}/src
        ${UPSTREAM}/CMSIS_DAP/CMSIS/DAP/Firmware/Include/
        ${UPSTREAM}/CMSIS_DAP/CMSIS/Core/Include/
)

target_compile_options(hackagotchi_probe PRIVATE -Wall)

# PIO headers (probe.pio.h / probe_oen.pio.h) — generated from the pristine upstream PIO.
pico_generate_pio_header(hackagotchi_probe ${UPSTREAM}/src/probe.pio)
pico_generate_pio_header(hackagotchi_probe ${UPSTREAM}/src/probe_oen.pio)

target_compile_definitions(hackagotchi_probe PRIVATE
        BOARD_HACKAGOTCHI=1
        PICO_RP2040_USB_DEVICE_ENUMERATION_FIX=1
        ADVERSARIAL_STALL_MS=${ADVERSARIAL_STALL_MS}
)

target_link_libraries(hackagotchi_probe PRIVATE
        pico_multicore
        pico_stdlib
        pico_unique_id
        tinyusb_device
        tinyusb_board
        hardware_pio
        hardware_i2c            # OLED coexistence task
        FreeRTOS-Kernel
        FreeRTOS-Kernel-Heap4   # heap_4: supports vPortFree + xPortGetMinimumEverFreeHeapSize (Gate-1 metric)
)

# Match upstream: the whole image runs from RAM (copy_to_ram) for deterministic SWD timing.
pico_set_binary_type(hackagotchi_probe copy_to_ram)

pico_add_extra_outputs(hackagotchi_probe)
