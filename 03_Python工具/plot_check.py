# 03_Python工具\plot_check.py
"""
功能: 读 recv.py 存下的 CSV, 做 FFT 并在图上校验频率刻度
用法: python plot_check.py [csv路径]   不带参数则自动选 04_数据集\raw 下最新的 csv
"""
import os
import sys
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_common"))   # 取得 frames.py 的路径，并将其插到搜索列表的最前面
import frames   # 导入 frames.py

# 设置 matplotlib 的全局字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]   # 不带衬线字体 = 微软雅黑
plt.rcParams["axes.unicode_minus"] = False              # 负号用 ASCII 的 “ - ”，防止用 unicode 的负号在中文下无法识别

PROJ    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 向上翻两个目录，找到项目根目录
RAW_DIR = os.path.join(PROJ, "04_数据集", "raw")                         # 在根目录找到原始数据文件夹
OUT_DIR = os.path.join(PROJ, "05_演示与输出")                            # 在根目录找到结果输出文件夹

def read_meta(path):
    """读文件开头 '#' 注释里的 k=v 元数据"""
    meta = {}   # 空字典
    with open(path, "r", encoding="utf-8") as fp:       # 根据路径 path 以只读、UTF-8打开
        for line in fp:                                 # 按行抓取数据
            if not line.startswith("#"):                # 是否以 “#” 开头，不是就跳出循环
                break
            for kv in line.lstrip("#").split():         # 去掉 “#”，按任意空白切分存放在字符串 kv 中，切分后有几块就循环几次
                if "=" in kv:                           # 是否有 “=”
                    k, v = kv.split("=", 1)             # 拆分键和值（仅按第一个 “=” 拆分）
                    meta[k] = v                         # 将键值存入字典
    return meta


def top_peaks(f, amp, count=2, fmin=10.0, fmax=500.0, guard=5):
    """ f、amp——数据的频率和幅值数组(根据下标对齐), 在fmin <= f <= fmax范围内, 
        找出幅值最大的 count 个峰, 每找到一个就把它附近 guard 格清零, 避免重复取同一峰"""
    idx = np.where((f >= fmin) & (f <= fmax))[0]            # 找出数组 f 中所有满足 fmin <= f <= fmax 的元素下标，保存到 idx 中
    a   = amp.copy()                                        # 复制一份数据
    out = []                                                # 空列表
    for _ in range(count):
        k = idx[int(np.argmax(a[idx]))]                     # a[idx]——取出属于范围内的频率的幅值；np.argmax(...)——找出最大值；idx[...]根据最大值反向找出其对应的频率（在）
        out.append((float(f[k]), float(a[k]), int(k)))      # 将频率、幅值、序号
        a[max(0, k - guard): k + guard + 1] = 0.0
    return out

def main():
    # 有命令行参数就用参数指定的文件；没有就自动挑 04_数据集\raw 里修改时间最新的那个 CSV。
    if len(sys.argv) > 1:                                       # 命令行有参数
        csv_path = sys.argv[1]
    else:
        if not os.path.isdir(RAW_DIR):
            print("找不到目录: %s" % RAW_DIR)                    # raw 文件夹下也没有文件
            return

        # 列出 RAW_DIR 目录下所有以 .csv 结尾的文件，并把它们拼成完整路径，存到列表 cands 中。
        cands = [os.path.join(RAW_DIR, x) for x in os.listdir(RAW_DIR) if x.lower().endswith(".csv")]
        
        # 如果没有存有原始数据的 csv
        if not cands:
            print("%s 下没有 csv, 请先运行 recv.py" % RAW_DIR)   # 
            return
        
        # 选择最新文件
        csv_path = max(cands, key=os.path.getmtime)

    meta    = read_meta(csv_path)                           # 获取文件开头注释里的各个参数
    fs      = int(meta.get("fs", frames.FS_HZ))             # 采样率（不存在会返回默认值，下同）
    n       = int(meta.get("per_frame", frames.MAX_N))      # 样本数
    afs_code = int(meta.get("afs_code", 0))                 # 量程码
    axis    = meta.get("axis", "?")                         # 轴号
    tag     = meta.get("tag", "?")                          # 工况标签(recv.py 写进文件头的 tag= 键); 老文件没这个键就显示 ?

    raw = np.loadtxt(csv_path, comments="#", dtype=np.int16)
    if raw.size < n:
        print("样本数不足一帧(%d < %d)" % (raw.size, n))
        return

    win_raw = raw[:n].astype(np.float64)         # 取第一窗，转 float
    g       = frames.to_g(win_raw, afs_code)     # int16 计数 -> 真实加速度（单位 g ）
    g_mean  = g.mean()                           # 计算均值
    d       = g - g_mean                         # 去均值: 压掉重力造成的 0Hz 直流
    
    # 判断时域信号幅度大小是否正常
    ac_rms = float(np.sqrt(np.mean(d * d)))          # 去均值后的有效值
    ac_pp  = float(d.max() - d.min())                # 峰峰值
    print("交流成分  : RMS %.5f g   峰峰值 %.5f g" % (ac_rms, ac_pp))
    if ac_pp < 1e-4:                                 # 小于 0.1 mg 视为死数据
        print("!! 警告: 这一轴几乎没有交流成分(峰峰值 < 0.1 mg)")
        print("   常见原因: 发错轴(振动不在这一轴上) / 桩函数没输出 / 传感器读失败")
        return
    
    # 计算：加窗、FFT、频率轴、单边幅值
    w   = np.hanning(n)                          # Hann 窗, 相干增益 = 0.5
    X   = np.fft.rfft(d * w)                     # 加窗进行 FFT
    f   = np.fft.rfftfreq(n, d=1.0 / fs)         # FFT结果的频率（与幅值一一对应）
    amp = 2.0 * np.abs(X) / (n * 0.5)            # 单边幅值: “2.0”——单边幅度修正; “n”——归一化; “0.5”——窗增益修正

    peaks = top_peaks(f, amp, 2, 10.0, fs / 2.0)    # 找 10 Hz 到奈奎斯特频率（采样率/2）的峰值

    # 打印信息
    print("文件      : %s" % csv_path)
    print("工况      : %s" % tag)
    print("轴号      : %s" % axis)
    print("采样率    : %d Hz   每帧 %d 点   频率分辨率 %.3f Hz/格" % (fs, n, fs / n))
    print("量程码    : %d  (%s, 灵敏度 %.0f 格/g)"
          % (afs_code, frames.AFS_NAME.get(afs_code, "?"), frames.SENS.get(afs_code, 0)))
    print("窗内均值  : %.5f g  (已减去)" % g_mean)
    for i, (pf, pa, pk) in enumerate(peaks):
        print("第%d峰    : %8.2f Hz   幅值 %.4f g   (bin %d)" % (i + 1, pf, pa, pk))
    if len(peaks) == 2 and peaks[1][1] > 0:     # 防止除零
        print("幅值比    : %.2f : 1" % (peaks[0][1] / peaks[1][1]))
    print("对照      : 合成信号应出现 45Hz 与 90Hz, 幅值比约 5:1")

    # 画出时域波形和频谱（放一张图）
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

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    png = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(csv_path))[0] + "_spectrum.png")
    plt.savefig(png, dpi=120)
    print("图已保存  : %s" % png)
    plt.show()

if __name__ == "__main__":
    main()