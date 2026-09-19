# 03_Python工具\plot_check.py
"""
功能: 读 recv.py 存下的 CSV, 做 FFT 并在图上校验频率刻度
用法: python plot_check.py [csv路径]   不带参数则自动选 04_数据集\raw 下最新的 csv
"""
import os
import sys
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_common"))
import frames

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

PROJ    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJ, "04_数据集", "raw")
OUT_DIR = os.path.join(PROJ, "05_演示与输出")

def read_meta(path):
    """读文件开头 '#' 注释里的 k=v 元数据"""
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

def top_peaks(f, amp, count=2, fmin=10.0, fmax=500.0, guard=5):
    """找出幅值最大的 count 个峰, 每找到一个就把它附近 guard 格清零, 避免重复取同一峰"""
    idx = np.where((f >= fmin) & (f <= fmax))[0]
    a   = amp.copy()
    out = []
    for _ in range(count):
        k = idx[int(np.argmax(a[idx]))]
        out.append((float(f[k]), float(a[k]), int(k)))
        a[max(0, k - guard): k + guard + 1] = 0.0
    return out

def main():
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        if not os.path.isdir(RAW_DIR):
            print("找不到目录: %s" % RAW_DIR)
            return
        cands = [os.path.join(RAW_DIR, x) for x in os.listdir(RAW_DIR) if x.lower().endswith(".csv")]
        if not cands:
            print("%s 下没有 csv, 先运行 recv.py" % RAW_DIR)
            return
        csv_path = max(cands, key=os.path.getmtime)

    meta    = read_meta(csv_path)
    fs      = int(meta.get("fs", frames.FS_HZ))
    n       = int(meta.get("per_frame", frames.MAX_N))
    afs_code = int(meta.get("afs_code", 0))
    axis    = meta.get("axis", "?")

    raw = np.loadtxt(csv_path, comments="#", dtype=np.int16)
    if raw.size < n:
        print("样本数不足一帧(%d < %d)" % (raw.size, n))
        return

    win_raw = raw[:n].astype(np.float64)         # 取第一窗
    g       = frames.to_g(win_raw, afs_code)     # int16 计数 -> g
    g_mean  = g.mean()
    d       = g - g_mean                         # 去均值: 压掉重力造成的 0Hz 直流

    w   = np.hanning(n)                          # Hann 窗, 相干增益 0.5
    X   = np.fft.rfft(d * w)
    f   = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = 2.0 * np.abs(X) / (n * 0.5)            # 单边幅值, 已做窗增益校正

    peaks = top_peaks(f, amp, 2, 10.0, fs / 2.0)

    print("文件      : %s" % csv_path)
    print("轴号      : %s" % axis)
    print("采样率    : %d Hz   每帧 %d 点   频率分辨率 %.3f Hz/格" % (fs, n, fs / n))
    print("量程码    : %d  (%s, 灵敏度 %.0f 格/g)"
          % (afs_code, frames.AFS_NAME.get(afs_code, "?"), frames.SENS.get(afs_code, 0)))
    print("窗内均值  : %.5f g  (已减去)" % g_mean)
    for i, (pf, pa, pk) in enumerate(peaks):
        print("第%d峰    : %8.2f Hz   幅值 %.4f g   (bin %d)" % (i + 1, pf, pa, pk))
    if len(peaks) == 2 and peaks[1][1] > 0:
        print("幅值比    : %.2f : 1" % (peaks[0][1] / peaks[1][1]))
    print("对照      : 合成信号应出现 45Hz 与 90Hz, 幅值比约 5:1")

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
    ax[1].set_xlim(0, 200)
    ax[1].grid(True)

    plt.tight_layout()

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    png = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(csv_path))[0] + "_spectrum.png")
    plt.savefig(png, dpi=120)
    print("图已保存  : %s" % png)
    plt.show()

if __name__ == "__main__":
    main()