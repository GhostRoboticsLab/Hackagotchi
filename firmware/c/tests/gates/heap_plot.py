#!/usr/bin/env python3
"""heap_plot.py — visualize the FreeRTOS heap watermark captured during the Gate-1 soak.

The fork emits lines over CDC like:   "heap free=131072 min=124288"  (any line containing
integers after 'free' and 'min' works). Capture them to a file, then:

  ./heap_plot.py soak_heap.log            # plot if matplotlib present, else text summary

Decision (engineering-plan §6): if min-ever-free stays comfortably positive (>= ~4 KB headroom)
with no downward trend -> keep heap_4. A monotonic decline -> a leak. Fragmentation alloc
failures -> consider heap_1.
"""
import re
import sys

FREE = re.compile(r"free[^0-9]*([0-9]+)", re.I)
MINF = re.compile(r"min[^0-9]*([0-9]+)", re.I)


def parse(path):
    free, mins = [], []
    with open(path) as f:
        for ln in f:
            m1, m2 = FREE.search(ln), MINF.search(ln)
            if m1:
                free.append(int(m1.group(1)))
            if m2:
                mins.append(int(m2.group(1)))
    return free, mins


def trend(xs):
    if len(xs) < 2:
        return 0.0
    n = len(xs)
    return (xs[-1] - xs[0]) / (n - 1)  # avg delta per sample


def main():
    if len(sys.argv) < 2:
        print("usage: heap_plot.py <soak_heap.log>")
        return 2
    path = sys.argv[1]
    free, mins = parse(path)
    if not free and not mins:
        print(f"no heap samples found in {path} (expected lines with 'free=' and 'min=')")
        return 2

    print(f"samples: free={len(free)} min={len(mins)}")
    if free:
        print(f"free heap : start={free[0]}  end={free[-1]}  lo={min(free)}  hi={max(free)}  "
              f"trend={trend(free):+.1f} B/sample")
    if mins:
        mn = min(mins)
        print(f"min-ever-free: {mn} B  ({mn/1024:.1f} KB)  "
              + ("OK (>=4KB headroom)" if mn >= 4096 else "⚠️ LOW — risk of exhaustion"))
        if trend(mins) < -1:
            print("⚠️ min-ever-free is DECLINING — possible leak. Investigate before trusting Gate 1.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        out = path + ".png"
        plt.figure(figsize=(10, 4))
        if free:
            plt.plot(free, label="free heap")
        if mins:
            plt.plot(mins, label="min-ever-free")
        plt.axhline(4096, ls="--", lw=0.8, label="4 KB floor")
        plt.xlabel("sample"); plt.ylabel("bytes"); plt.legend(); plt.title("Gate 1 heap watermark")
        plt.tight_layout(); plt.savefig(out)
        print(f"wrote {out}")
    except ImportError:
        print("(matplotlib not installed — text summary only; pip install matplotlib for a plot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
