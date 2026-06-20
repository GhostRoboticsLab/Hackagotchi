#!/usr/bin/env bash
# analyze.sh — reliability static-analysis gate for the Hackagotchi fork's OWN code (engineering-plan §3).
#
# Runs GCC -fanalyzer + strict warnings (and cppcheck, if installed) on ONLY our overlay/new sources
# (firmware/c/src/*.c, excluding the vendored ssd1306/), using the exact flags+includes from the
# build's compile_commands.json. Vendored upstream (SDK/TinyUSB/FreeRTOS/debugprobe/ssd1306) is excluded.
#
#   ./build_fork.sh && ./analyze.sh            # analyze build/compile_commands.json
#   BUILD_DIR=/path/to/build ./analyze.sh
#
# Exit policy (CI-friendly):
#   FAIL on any -Wanalyzer-* finding (the serious bug class) in any of our files, OR any warning in the
#   genuinely-NEW files (hackagotchi_dashboard.c, cdc1_control.c — these must stay pristine).
#   REPORT-only for upstream-inherited style warnings (-Wunused-parameter/-Wshadow/-Wsign-compare) in
#   the overlay copies (main.c, cdc_uart.c, usb_descriptors.c), which we keep close to upstream.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${BUILD_DIR:-$HERE/build}"
CCJSON="$BUILD_DIR/compile_commands.json"
[ -f "$CCJSON" ] || { echo "no $CCJSON — run ./build_fork.sh first"; exit 2; }

PRISTINE="hackagotchi_dashboard.c cdc1_control.c"   # new code: any warning fails the gate

python3 - "$CCJSON" "$PRISTINE" <<'PY'
import json, subprocess, shlex, os, sys, re
ccjson, pristine = sys.argv[1], set(sys.argv[2].split())
cc = json.load(open(ccjson))
ours = [e for e in cc if "/firmware/c/src/" in e["file"] and "/ssd1306/" not in e["file"]]
EXTRA = ["-Wall","-Wextra","-Wshadow","-Wundef","-Wdouble-promotion","-fanalyzer","-fsyntax-only"]
fail = 0
print(f"== GCC -fanalyzer + strict warnings on {len(ours)} fork TU(s) ==")
for e in sorted(ours, key=lambda e:e["file"]):
    base = os.path.basename(e["file"])
    parts = shlex.split(e["command"]); cmd=[parts[0]]; skip=False
    for p in parts[1:]:
        if skip: skip=False; continue
        if p=="-o": skip=True; continue
        if p=="-c": continue
        cmd.append(p)
    cmd[1:1]=EXTRA
    r = subprocess.run(cmd, cwd=e["directory"], capture_output=True, text=True)
    lines = [l for l in r.stderr.splitlines() if base+":" in l and (" warning:" in l or " error:" in l)]
    analyzer = [l for l in lines if "-Wanalyzer" in l]
    style    = [l for l in lines if "-Wanalyzer" not in l]
    status = "OK"
    if analyzer or (base in pristine and lines): status, _ = "FAIL", None; fail += 1
    print(f"\n  [{status}] {base}: {len(analyzer)} analyzer / {len(style)} style")
    for l in analyzer: print("    BUG  "+re.sub(r'/Volumes/\S+/firmware/c/','',l)[:200])
    if base in pristine:
        for l in style: print("    NEW  "+re.sub(r'/Volumes/\S+/firmware/c/','',l)[:200])
    else:
        for l in style[:6]: print("    (upstream-inherited) "+re.sub(r'/Volumes/\S+/firmware/c/','',l)[:160])
print(f"\n== gcc analyze: {'PASS' if fail==0 else 'FAIL ('+str(fail)+' file(s))'} ==")
sys.exit(1 if fail else 0)
PY
gcc_rc=$?

# Optional 2nd opinion: cppcheck on our files only (disjoint bug class per the plan). Report-only.
if command -v cppcheck >/dev/null 2>&1; then
  echo; echo "== cppcheck (2nd opinion, report-only) =="
  cppcheck --enable=warning,performance,portability --inline-suppr --quiet \
    --suppress=missingIncludeSystem --std=c11 \
    "$HERE/src/hackagotchi_dashboard.c" "$HERE/src/cdc1_control.c" 2>&1 | sed "s#$HERE/##" || true
else
  echo; echo "== cppcheck not installed (brew install cppcheck) — skipped =="
fi

exit $gcc_rc
