#!/usr/bin/env bash
# lib_target_state.sh — classify a flash failure as TARGET-side vs PROBE-side, so a glitched /
# brown-out TARGET is never misattributed to the probe.
#
# WHY THIS EXISTS: every "the probe can't flash" scare in this project has traced back to the
# TARGET, not the probe — either a HardFault-locked core (cannot run the flash ROM functions) or a
# QSPI brown-out under sustained reflash hammering (its AHB access port vanishes). A probe that is
# provably healthy (0 stalls, DAP enumerates, attestation clean) cannot cause or fix that — only a
# power-cycle of the TARGET does. The bare "FAIL" the old harness logged invited the misdiagnosis.
#
# On RP2040 the decisive tell is the AHB-AP:
#   AHB-AP present (AmbaAhb3 / ROM Table answers) => target is debuggable & flashable. A verify
#     mismatch HERE is SWD wiring / host load / a genuine probe issue — it FAILS the probe verdict.
#   AHB-AP absent (probe still on USB, DP answers, but no AP) => target access port is gone:
#     QSPI brown-out / lockup. POWER-CYCLE THE TARGET. NOT a probe fault.
#   probe absent from USB => probe/cable/USB problem (this one IS probe-side).
#
# NOTE: under RP2040 multidrop the rescue DP (instance 0x0f) ALWAYS prints "No access ports found"
# even on a perfectly healthy target, so we classify on the POSITIVE signal (an AHB-AP answering),
# never on the absence string.

# classify_target [CHIP]  -> echoes one of: TARGET_OK | TARGET_GLITCH | PROBE_ABSENT | UNKNOWN
classify_target() {
  local chip="${1:-RP2040}" info
  command -v probe-rs >/dev/null 2>&1 || { echo UNKNOWN; return; }
  probe-rs list 2>/dev/null | grep -qi cmsis || { echo PROBE_ABSENT; return; }
  info="$(probe-rs info --chip "$chip" --protocol swd 2>&1)"
  if printf '%s' "$info" | grep -qiE "AmbaAhb3|ROM Table"; then
    echo TARGET_OK            # at least one core's AHB-AP answered => flashable
  else
    echo TARGET_GLITCH        # probe is on USB + DP answered, but no AHB-AP => glitched/brown-out target
  fi
}

# target_hint CLASS  -> one line of operator guidance (tee'd into the soak log)
target_hint() {
  case "$1" in
    TARGET_OK)     echo "    -> target debuggable (AHB-AP present): SWD wiring / host load / genuine — counts against the PROBE." ;;
    TARGET_GLITCH) echo "    -> TARGET brown-out/lockup (AHB-AP gone): POWER-CYCLE THE TARGET. NOT a probe fault." ;;
    PROBE_ABSENT)  echo "    -> PROBE vanished from USB: check the probe cable/port — this IS probe-side." ;;
    *)             echo "    -> unclassified (probe-rs unavailable)." ;;
  esac
}
