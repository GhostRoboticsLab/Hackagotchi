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
# Adversarial-only: run the OLED stress task AT DAP priority so a busy_wait genuinely time-slices
# with DAP (the idle-priority stall is preempted in ~50us = a no-op threat). NOT a product config.
option(ADVERSARIAL_AT_DAP_PRIO "Run the OLED stress task at DAP priority (adversarial contention test)" OFF)

# [HACKAGOTCHI] M2: carlk3 no-OS-FatFS-SD (SDIO+SPI) for the SD black-box recorder. Fetched by
# setup.sh into the gitignored upstream/ (same pattern as debugprobe), NOT a submodule. INTERFACE lib;
# our src/sd/hw_config.c provides the SPI0 pin map. Requires pico_sdk_init() to have run (above).
set(FATFS ${CMAKE_CURRENT_LIST_DIR}/upstream/no-OS-FatFS)
if (NOT EXISTS ${FATFS}/src/CMakeLists.txt)
    message(FATAL_ERROR "upstream/no-OS-FatFS not found — run ./setup.sh first (fetches carlk3 FatFs).")
endif ()
add_subdirectory(${FATFS}/src ${CMAKE_BINARY_DIR}/no-OS-FatFS)
# Drop carlk3's src/crash.c — it defines its OWN naked isr_hardfault (collides with our src/crash_box.c)
# and parks a buffer in .uninitialized_data. We use OUR crash box; surgically remove just that source.
get_target_property(_fatfs_srcs no-OS-FatFS-SD-SDIO-SPI-RPi-Pico INTERFACE_SOURCES)
list(FILTER _fatfs_srcs EXCLUDE REGEX "/src/crash\\.c$")
# We use the card over SPI only (SD_IF_SPI) — drop the ~11 KB of unused SDIO code (dead weight in the
# flash image). sd_card.c references 2 SDIO symbols; src/sd/sdio_stubs.c satisfies the linker.
list(FILTER _fatfs_srcs EXCLUDE REGEX "/SDIO/")
set_target_properties(no-OS-FatFS-SD-SDIO-SPI-RPi-Pico PROPERTIES INTERFACE_SOURCES "${_fatfs_srcs}")

add_executable(hackagotchi_probe
        # --- OUR overlay (compiled instead of the matching upstream files; see each file's header) ---
        ${CMAKE_CURRENT_LIST_DIR}/src/main.c                 # + OLED coexistence task (Gate 1)
        ${CMAKE_CURRENT_LIST_DIR}/src/hackagotchi_dashboard.c
        ${CMAKE_CURRENT_LIST_DIR}/src/ssd1306/ssd1306.c
        ${CMAKE_CURRENT_LIST_DIR}/src/usb_descriptors.c      # Gate 2: 2nd CDC + IAD composite
        ${CMAKE_CURRENT_LIST_DIR}/src/cdc_uart.c             # Gate 2: itf-guard the CDC class callbacks
        ${CMAKE_CURRENT_LIST_DIR}/src/uart_bridge.c          # M1: IRQ-driven RX capture into an SPSC ring
        ${CMAKE_CURRENT_LIST_DIR}/src/cdc1_control.c         # Gate 2: CDC1 JSON control handler
        ${CMAKE_CURRENT_LIST_DIR}/src/crash_box.c            # M1: post-mortem crash box + HardFault handler
        ${CMAKE_CURRENT_LIST_DIR}/src/watchdog_task.c        # M1: SW watchdog (HW WDT + per-task check-in)
        ${CMAKE_CURRENT_LIST_DIR}/src/sd/hw_config.c         # M2: carlk3 SD pin map (SPI0 GP2/3/4/CS28)
        ${CMAKE_CURRENT_LIST_DIR}/src/sd/sdio_stubs.c        # M2: stub the unused SDIO refs (SPI-only)
        ${CMAKE_CURRENT_LIST_DIR}/src/sd_gate.c              # M2: SD bring-up gate + recorder/SD task
        ${CMAKE_CURRENT_LIST_DIR}/src/recorder.c             # M2: black-box recorder core (host-tested)
        # --- pristine upstream debugprobe sources ---
        ${UPSTREAM}/src/probe_config.c
        ${UPSTREAM}/src/probe.c
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
        ${CMAKE_CURRENT_LIST_DIR}/src/sd   # M2: our ffconf.h overlay shadows carlk3's (FatFs feature trim)
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
if(ADVERSARIAL_AT_DAP_PRIO)
    target_compile_definitions(hackagotchi_probe PRIVATE ADVERSARIAL_AT_DAP_PRIO=1)
endif()

target_link_libraries(hackagotchi_probe PRIVATE
        pico_multicore
        pico_stdlib
        pico_unique_id
        tinyusb_device
        tinyusb_board
        hardware_pio
        hardware_irq            # M1 uart_bridge: RX IRQ handler
        hardware_i2c            # OLED coexistence task
        hardware_watchdog       # M1 crash box: watchdog_reboot + scratch-register mirror; SW watchdog
        pico_bootrom            # M1: reset_usb_boot for the {"q":"bootsel"} self-reflash command
        FreeRTOS-Kernel
        FreeRTOS-Kernel-Heap4   # heap_4: supports vPortFree + xPortGetMinimumEverFreeHeapSize (Gate-1 metric)
        no-OS-FatFS-SD-SDIO-SPI-RPi-Pico  # M2: carlk3 SD/FatFs (propagates hardware_spi/dma, pico_aon_timer)
)

# Run from flash (XIP), NOT copy_to_ram. Upstream debugprobe defaults to copy_to_ram for "deterministic
# SWD timing", but SWCLK is generated by PIO hardware (probe.pio) and the SWD servicing hot path is tiny
# (stays warm in the 16 KB XIP cache), so XIP matches RAM throughput. Re-gated under XIP: probe-rs
# 1000/1000 + openocd 200/200 (0 fail/0 stall), throughput +2.6% vs copy_to_ram (noise), crash box +
# watchdog HIL pass. Payoff: text+rodata stay in flash instead of being copied to SRAM → free SRAM
# 35 KB -> 174 KB (+139 KB) for M3. See tests/m2/M2_RESULTS.md "copy_to_ram -> XIP".
pico_set_binary_type(hackagotchi_probe default)

pico_add_extra_outputs(hackagotchi_probe)
