# 03_Python工具\plot_check.py
"""读取正式/调试/旧版 CSV，检查时域和频谱。"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import frames
import metadata

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

PROJ = os.path.dirname(_HERE)
DATA_DIRS = [os.path.join(PROJ, "04_数据集", x) for x in ("formal", "debug_raw", "raw")]
OUT_DIR = os.path.join(PROJ, "05_演示与输出")


def latest_csv():
    cands = []
    for directory in DATA_DIRS:
        if os.path.isdir(directory):
            cands.extend(os.path.join(directory, x) for x in os.listdir(directory)
                         if x.lower().endswith(".csv"))
    return max(cands, key=os.path.getmtime) if cands else None


def top_peaks(f, amp, count=2, fmin=10.0, fmax=500.0, guard=5):
    idx = np.where((f >= fmin) & (f <= fmax))[0]
    a = amp.copy()
    out = []
    for _ in range(count):
        if not len(idx):
            break
        k = idx[int(np.argmax(a[idx]))]
        out.append((float(f[k]), float(a[k]), int(k)))
        a[max(0, k - guard):k + guard + 1] = 0.0
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    csv_path = argv[0] if argv else latest_csv()
    if not csv_path:
        print("三个数据目录中都没有 csv，请先运行 recv.py")
        return 1
    meta = metadata.read_meta(csv_path)
    fs = int(meta.get("fs_hz", meta.get("fs", frames.FS_HZ)))
    n = int(meta.get("frame_n", meta.get("per_frame", frames.MAX_N)))
    afs_code = int(meta.get("afs_code", 0))
    axis = meta.get("measurement_axis", meta.get("axis", "?"))
    raw = np.atleast_1d(np.loadtxt(csv_path, comments="#", dtype=np.int16))
    if raw.size < n:
        print("样本数不足一帧(%d < %d)" % (raw.size, n))
        return 1
    g = frames.to_g(raw[:n].astype(np.float64), afs_code)
    g_mean = g.mean()
    d = g - g_mean
    ac_rms = float(np.sqrt(np.mean(d * d)))
    ac_pp = float(d.max() - d.min())
    print("文件      : %s" % csv_path)
    print("记录      : %s | 设备 %s | 工况 %s | 标签 %s | 质量 %s" %
          (meta.get("record_id", "legacy"), meta.get("device_id", "legacy_unknown"),
           meta.get("observed_condition", "unknown"), meta.get("target_label", "unassigned"),
           meta.get("quality_status", "unknown")))
    print("轴号      : %s (测量轴 X，重力轴 Y)" % axis)
    print("采样率    : %d Hz   每帧 %d 点   频率分辨率 %.3f Hz/格" % (fs, n, fs / n))
    print("供电      : %s V" % meta.get("voltage_measured_v", meta.get("voltage_set_v", "?")))
    print("交流成分  : RMS %.5f g   峰峰值 %.5f g" % (ac_rms, ac_pp))
    if ac_pp < 1e-4:
        print("!! 警告: 这一轴几乎没有交流成分")
        return 1
    w = np.hanning(n)
    X = np.fft.rfft(d * w)
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = 2.0 * np.abs(X) / (n * 0.5)
    peaks = top_peaks(f, amp, 2, 10.0, fs / 2.0)
    print("量程码    : %d (%s, 灵敏度 %.0f 格/g)" %
          (afs_code, frames.AFS_NAME.get(afs_code, "?"), frames.SENS.get(afs_code, 0)))
    print("窗内均值  : %.5f g (已减去)" % g_mean)
    for i, (pf, pa, pk) in enumerate(peaks):
        print("第%d峰    : %8.2f Hz   幅值 %.4f g   (bin %d)" % (i + 1, pf, pa, pk))
    if len(peaks) == 2 and peaks[1][1] > 0:
        print("幅值比    : %.2f : 1" % (peaks[0][1] / peaks[1][1]))

    t = np.arange(n) / fs
    fig, ax = plt.subplots(2, 1, figsize=(10, 7))
    ax[0].plot(t[:int(0.1 * fs)] * 1000.0, g[:int(0.1 * fs)])
    ax[0].set_title("%s axis time domain (first 100 ms)" % axis)
    ax[0].set_xlabel("time (ms)")
    ax[0].set_ylabel("accel (g)")
    ax[0].grid(True)
    ax[1].plot(f, amp)
    ax[1].set_title("single-sided amplitude spectrum (N=%d, Hann)" % n)
    ax[1].set_xlabel("frequency (Hz)")
    ax[1].set_ylabel("amplitude (g)")
    ax[1].set_xlim(0, 500)
    ax[1].grid(True)
    plt.tight_layout()
    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(csv_path))[0] + "_spectrum.png")
    plt.savefig(png, dpi=120)
    print("图已保存  : %s" % png)
    plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
