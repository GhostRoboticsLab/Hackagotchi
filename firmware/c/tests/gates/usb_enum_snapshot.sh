#!/usr/bin/env bash
# usb_enum_snapshot.sh — timestamped USB enumeration snapshot. Run before/after a gate and
# diff the two to see exactly how the descriptors changed (e.g. CDC0 -> CDC0+CDC1 at Gate 2).
#   ./usb_enum_snapshot.sh [outfile]
set -uo pipefail
OUT="${1:-usb_snapshot_$(date +%Y%m%dT%H%M%S).txt}"
{
  echo "=== USB snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "--- /dev/cu.usbmodem* ---"
  ls -1 /dev/cu.usbmodem* 2>/dev/null || echo "(none)"
  echo
  echo "--- system_profiler SPUSBDataType (probe / CDC / serial) ---"
  system_profiler SPUSBDataType 2>/dev/null \
    | grep -iA12 -E 'CMSIS|debugprobe|Picoprobe|Hackagotchi|Composite|CDC|Serial Number' \
    || echo "(no match)"
  echo
  echo "--- ioreg IOUSB (probe / callout nodes) ---"
  ioreg -p IOUSB -l -w0 2>/dev/null \
    | grep -iE 'CMSIS|debugprobe|Hackagotchi|IOCalloutDevice|USB Product Name|USB Vendor Name|bInterfaceNumber' \
    || echo "(no match)"
} | tee "$OUT"
echo "[snapshot] wrote $OUT"
