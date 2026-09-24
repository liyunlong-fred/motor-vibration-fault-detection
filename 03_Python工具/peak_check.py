# 03_Python工具\peak_check.py —— 与板上 dsp_fft_print() 同口径的 TOP-5 峰打印
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import frames
import metadata

FMIN, FMAX, GUARD, TOPN = 10.0, 400.0, 2, 5
PROJ = os.path.dirname(_HERE)
DATA_DIRS = [os.path.join(PROJ, "04_数据集", x) for x in ("formal", "debug_raw", "raw")]


def latest_csv():
    cands = []
    for directory in DATA_DIRS:
        if os.path.isdir(directory):
            cands.extend(os.path.join(directory, f) for f in os.listdir(directory)
                         if f.lower().endswith(".csv"))
    return max(cands, key=os.path.getmtime) if cands else None


def top_peaks(win_g, fs, n):
    mean_g = win_g.mean()
    X = np.fft.rfft((win_g - mean_g) * np.hanning(n))
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
    if not path:
        print("三个数据目录中都没有 csv，请先运行 recv.py")
        return 1
    meta = metadata.read_meta(path)
    fs = float(meta.get("fs_hz", meta.get("fs", frames.FS_HZ)))
    n = int(meta.get("frame_n", meta.get("per_frame", frames.MAX_N)))
    afs = int(meta.get("afs_code", 0))
    nframe = int(meta.get("frames", 1))
    first = int(meta.get("first_seq", 1))
    print("记录=%s 设备=%s 工况=%s 标签=%s 质量=%s" %
          (meta.get("record_id", "legacy"), meta.get("device_id", "legacy_unknown"),
           meta.get("observed_condition", "unknown"), meta.get("target_label", "unassigned"),
           meta.get("quality_status", "unknown")))
    d = np.atleast_1d(np.loadtxt(path, comments="#"))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else latest_csv()))
