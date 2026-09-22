# 03_Python工具\peak_check.py —— 与板上 dsp_fft_print() 同口径的 TOP-5 峰打印
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_common"))
import frames

FMIN, FMAX, GUARD, TOPN = 10.0, 400.0, 2, 5


def read_meta(path):
    meta = {}
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            if not line.startswith("#"):
                break
            for kv in line.lstrip("#").split():
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    meta[k] = v
    return meta


def top_peaks(win_g, fs, n):
    raw = win_g
    mean_g = raw.mean()
    X = np.fft.rfft((raw - mean_g) * np.hanning(n))
    amp = 2.0 * np.abs(X) / (n * 0.5)

    df = fs / n
    kmin = int(np.ceil(FMIN / df))
    kmax = min(len(amp) - 1, int(FMAX / df))

    work = amp.copy()
    out = []
    for _ in range(TOPN):
        k = int(np.argmax(work[kmin:kmax + 1])) + kmin
        if work[k] <= 0:
            break
        out.append((k, k * df, work[k]))
        work[max(0, k - GUARD):k + GUARD + 1] = 0.0
    return mean_g, out


def main(path):
    meta = read_meta(path)
    fs = float(meta.get("fs", frames.FS_HZ))
    n = int(meta.get("per_frame", frames.MAX_N))
    afs = int(meta.get("afs_code", 0))
    nframe = int(meta.get("frames", 1))
    first = int(meta.get("first_seq", 1))

    d = np.loadtxt(path, comments="#")
    if d.ndim == 2:
        d = d[:, 0]
    g = frames.to_g(d, afs)

    for j in range(nframe):
        seq = first + j
        win = g[j * n:(j + 1) * n]
        if len(win) < n:
            break
        mean_g, peaks = top_peaks(win, fs, n)
        print("PC  seq=%d n=%d mean=%d mg" % (seq, n, round(mean_g * 1000)))
        for i, (k, f, a) in enumerate(peaks):
            print("  #%d bin=%d f=%.2f Hz amp=%d mg" % (i + 1, k, f, round(a * 1000)))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        raw_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_数据集", "raw")
        latest = max(
            (os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".csv")),
            key=os.path.getmtime,
        )
        print("分析:", latest)
        main(latest)