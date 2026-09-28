# 03_Python工具\harmonics.py
"""
功能: 对"测量 + FFT 之后"的振动数据做谐波族(harmonic family)分析 ——
      找出基频 f0(也就是 1× 转速频率), 看清它的各次倍频 k×f0 里哪个最强、哪个第二强,
      再由 f0 推算风扇转速, 并把结论打印出来。

用法:
    python harmonics.py                        # 自动分析 04_数据集\raw 里最新的那个 csv
    python harmonics.py <csv路径>              # 分析指定文件
    python harmonics.py <csv> --plot           # 顺便画频谱图, 标注 1×/2×/3×... 存到 05_演示与输出
    python harmonics.py <谱线csv> --spectrum   # 输入改成"已经 FFT 好的两列数据"(频率Hz, 幅值)
    python harmonics.py <csv> --rpm-measured 3061  # 用同工况 TACH 转速锁定机械 1×
    python harmonics.py <csv> --f0min 45 --f0max 105  # 修改已验证设备的 1× 搜索范围

常用可选参数:
    --fmin 10       分析下限 Hz      --fmax 400     分析上限 Hz
    --f0min 45      机械 1× 候选下限 Hz
    --f0max 105     机械 1× 候选上限 Hz
    --thresh 0.08   峰阈值: 幅值不到"最大峰 × 8%"的不算峰
    --rpm-measured 3061    同工况、同设备的独立 TACH/转速计读数；优先级最高

算法说明见文件末尾。
"""
import argparse
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))                  # 本文件所在目录 = 03_Python工具
sys.path.insert(0, os.path.join(_HERE, "py_common"))                # 让本文件能 import frames.py
import frames                                                        # 帧协议 + int16计数→g 的唯一换算处
import metadata                                                      # 新旧 CSV 元数据兼容层

PROJ    = os.path.dirname(_HERE)                                     # 上一级 = 项目根目录
DATA_DIRS = [os.path.join(PROJ, "04_数据集", x) for x in ("formal", "debug_raw", "raw")]
RAW_DIR = DATA_DIRS[-1]                                               # 兼容旧提示
OUT_DIR = os.path.join(PROJ, "05_演示与输出")                          # 图片输出

DEFAULT_FMIN      = 10.0      # 分析下限 Hz(低于它的多半是重力/零偏造成的低频漂移)
DEFAULT_FMAX      = 400.0     # 分析上限 Hz(规划 §2.4: 1kHz 采样下用到 400Hz 留安全余量)
DEFAULT_F0_MIN    = 45.0      # 本风扇 TACH 已验证的机械 1× 搜索下限
DEFAULT_F0_MAX    = 105.0     # 本风扇 TACH 已验证的机械 1× 搜索上限
DEFAULT_THRESH    = 0.08      # 峰阈值(相对最大峰)
DEFAULT_MAX_ORDER = 10        # 最多看几次倍频
TOL_PCT           = 0.015     # 匹配容差: 允许 k×f0 与实测峰差 1.5%
TOL_CAP           = 8.0       # 但容差最大不超过 8 Hz(防高次倍频乱匹配)
SNR_MIN           = 6.0       # 峰本底比低于这个数就认为"没测到有效振动"
RPM_MATCH_TOL    = 0.05    # TACH 锁定时，允许谱峰相对机械 1× 偏离 5%（至少两个 FFT bin）


# ============================================================ 读数据

def read_meta(path):
    """统一读取新 JSON 头，并兼容旧版 k=v 头。"""
    return metadata.read_meta(path)


def load_csv(path):
    """读 recv.py 存下的 csv: 返回 (元数据字典, 全部 int16 原始计数)
    一行一个数, 整个文件是"帧1的1024点 + 帧2的1024点 + ..."拼起来的"""
    meta = read_meta(path)
    samples = np.loadtxt(path, comments="#", dtype=np.int16,
                         encoding="utf-8-sig")
    return meta, np.atleast_1d(samples).ravel()


def load_spectrum_csv(path):
    """读"已经 FFT 好"的两列数据(频率Hz, 幅值); 逗号分隔或空格分隔都认"""
    delim = None
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            s = line.strip()
            if s and not s.startswith("#"):
                delim = "," if "," in s else None       # 有逗号就按逗号切, 否则按空白切
                break
    data = np.loadtxt(path, comments="#", delimiter=delim,
                      encoding="utf-8-sig")
    if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError("谱线文件需要两列: 频率Hz 幅值")
    f = np.asarray(data[:, 0], dtype=np.float64)
    amp = np.asarray(data[:, 1], dtype=np.float64)
    order = np.argsort(f)                               # 频率从小到大排一遍, 后面的峰检测要求有序
    return f[order], amp[order]


def average_spectrum(samples, fs=frames.FS_HZ, n=frames.MAX_N, afs_code=0):
    """int16 原始计数 → 平均单边幅值谱
    每一帧: 计数→g(去重力直流)→加 Hann 窗→rfft→归一化成单边幅值;
    最后把所有帧的幅值谱取平均 —— 平均能压掉随机噪声, 让真峰更突出(相位是随机的, 但幅值不互相抵消)。
    返回 (频率数组, 幅值数组, 用了几帧)
    """
    nf = int(samples.size // n)
    if nf < 1:
        raise ValueError("样本数不足一帧(%d < %d)" % (samples.size, n))

    acc = np.zeros(n // 2 + 1, dtype=np.float64)
    for i in range(nf):
        g = frames.to_g(samples[i * n:(i + 1) * n], afs_code)   # 计数 → g
        d = g - g.mean()                                        # 去均值: 压掉 0Hz 的直流
        X = np.fft.rfft(d * np.hanning(n))                      # 加窗后做实数 FFT
        acc += 2.0 * np.abs(X) / (n * 0.5)                      # 2.0=单边修正, 0.5=Hann 窗相干增益
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    return f, acc / nf, nf


# ============================================================ 机械 1× 参考

def parse_rpm(value):
    """把命令行或 CSV 中的实测 RPM 转成正浮点数；空值返回 None。"""
    if value in (None, "", "?"):
        return None
    rpm = float(value)
    if not np.isfinite(rpm) or rpm <= 0:
        raise ValueError("实测转速必须是有限的正数 rpm")
    return rpm


# ============================================================ 谐波族分析

def merge_peaks(raw, df):
    """挨得太近的峰(窗主瓣有 2~3 格宽)合并, 留大的那个"""
    merged = []
    for p in raw:
        if merged and (p[0] - merged[-1][0]) < 2.0 * df:
            if p[1] > merged[-1][1]:
                merged[-1] = p
        else:
            merged.append(p)
    return merged


def find_peaks(f, amp, fmin=DEFAULT_FMIN, fmax=DEFAULT_FMAX, rel_thresh=DEFAULT_THRESH):
    """在 fmin~fmax 里找"局部极大值"当峰, 幅值小于 rel_thresh×最大峰 的丢掉(那是本底噪声)
    返回 [(频率, 幅值, 格号), ...], 按频率从小到大"""
    band = (f >= fmin) & (f <= fmax)
    idx = np.where(band)[0]
    if idx.size < 3:
        return []
    top = float(amp[idx].max())
    df = float(f[1] - f[0]) if f.size > 1 else 1.0

    raw = []
    for i in idx[1:-1]:                       # 两端没法比较左右邻居, 跳过
        if amp[i] > amp[i - 1] and amp[i] >= amp[i + 1] and amp[i] >= rel_thresh * top:
            raw.append((float(f[i]), float(amp[i]), int(i)))
    return merge_peaks(raw, df)               # 挨得太近的峰合并


def collect_peaks(f, amp, fmin, fmax, rel_thresh):
    """收集分析带内超过常规阈值的局部峰。"""
    return find_peaks(f, amp, fmin, fmax, rel_thresh)


def match_harmonics(f0, peaks, fmax, tol_base,
                    tol_pct=TOL_PCT, tol_cap=TOL_CAP, max_order=DEFAULT_MAX_ORDER):
    """假设 f0 是基频, 看它的 1×、2×、3×… 在峰表里能不能找到对应的峰
    规则: 某个 k 只匹配"离 k×f0 在容差内、且幅值最大"的那个峰; 一个峰只能被用一次。
    返回 (得分, [(k, 峰), ...]); 得分 = Σ 幅值/k —— 越靠前的谐波越能代表基频, 所以除以 k"""
    used = set()
    matches = []
    for k in range(1, max_order + 1):
        target = k * f0
        if target > fmax:
            break
        tol = min(tol_cap, max(tol_base, tol_pct * target))
        best = -1
        for j, p in enumerate(peaks):
            if j in used:
                continue
            if abs(p[0] - target) <= tol and (best < 0 or p[1] > peaks[best][1]):
                best = j
        if best >= 0:
            used.add(best)
            matches.append((k, peaks[best]))
    return sum(p[1] / k for k, p in matches), matches


def analyze(f, amp, fmin=DEFAULT_FMIN, fmax=DEFAULT_FMAX,
            f0_min=DEFAULT_F0_MIN, f0_max=DEFAULT_F0_MAX,
            rel_thresh=DEFAULT_THRESH, max_order=DEFAULT_MAX_ORDER,
            rpm_measured=None):
    """分析已验证设备的机械 1× 及其谐波。

    未提供 ``rpm_measured`` 时，只能在已验证的机械 1× 区间内选择实际谱峰；
    提供同工况 TACH/转速计读数时，机械 1× 固定为 ``RPM / 60``，频谱只负责
    核对该位置及其倍频，绝不再从子谐波反推转速。
    """
    f = np.asarray(f, dtype=np.float64)
    amp = np.asarray(amp, dtype=np.float64)
    df = float(f[1] - f[0]) if f.size > 1 else 1.0
    measured_rpm = parse_rpm(rpm_measured)
    res = {"f0": None, "f0_peak": None, "rpm": None, "harmonics": [], "missing": [],
           "strongest": None, "second": None, "candidates": [], "snr": 0.0,
           "reliable": False, "n_peaks": 0, "fmin": fmin, "fmax": fmax,
           "f0_min": f0_min, "f0_max": f0_max, "rel_thresh": rel_thresh,
           "max_order": max_order, "df": df, "rpm_measured": measured_rpm,
           "source": None, "one_x_detected": False}
    if f0_min >= f0_max:
        raise ValueError("机械 1× 候选范围必须满足 f0min < f0max")

    peaks = collect_peaks(f, amp, fmin, fmax, rel_thresh)
    res["n_peaks"] = len(peaks)
    if not peaks and measured_rpm is None:
        return res
    band = (f >= fmin) & (f <= fmax)
    noise = float(np.median(amp[band])) if band.any() else 0.0
    res["snr"] = (max(p[1] for p in peaks) / noise) if peaks and noise > 0 else 0.0
    res["reliable"] = bool(res["snr"] >= SNR_MIN)

    candidates = [p for p in peaks if f0_min <= p[0] <= f0_max]
    if measured_rpm is not None:
        f0 = measured_rpm / 60.0
        if not f0_min <= f0 <= f0_max:
            raise ValueError("实测转速 %.0f rpm 对应 %.2f Hz，不在 %.1f~%.1f Hz 的已验证机械 1×范围内"
                             % (measured_rpm, f0, f0_min, f0_max))
        tolerance = max(2.0 * df, RPM_MATCH_TOL * f0)
        near = [p for p in peaks if abs(p[0] - f0) <= tolerance]
        f0_peak = max(near, key=lambda p: p[1]) if near else None
        res["source"] = "tach"
    else:
        if not candidates:
            return res
        # 机械 1×已由 TACH 确认为约 50~100 Hz；在该窗口内直接选实测峰，
        # 避免旧版梳状评分把 36.6 Hz 一类子谐波回推成所谓“基频”。
        f0_peak = max(candidates, key=lambda p: p[1])
        f0 = f0_peak[0]
        res["source"] = "spectrum"

    _, matches = match_harmonics(f0, peaks, fmax, 2.0 * df, max_order=max_order)
    res["f0"] = f0
    res["f0_peak"] = f0_peak[0] if f0_peak else None
    res["rpm"] = measured_rpm if measured_rpm is not None else f0 * 60.0
    res["one_x_detected"] = bool(f0_peak)
    for candidate in sorted(candidates, key=lambda p: -p[1])[:3]:
        score, candidate_matches = match_harmonics(candidate[0], peaks, fmax, 2.0 * df,
                                                    max_order=max_order)
        res["candidates"].append({"f0": candidate[0], "amp": candidate[1],
                                  "score": score, "n": len(candidate_matches)})

    amp1 = next((p[1] for k, p in matches if k == 1), None)
    for k, p in matches:
        res["harmonics"].append({"k": k, "f_theory": k * f0, "f_peak": p[0], "amp": p[1],
                                  "ratio": (100.0 * p[1] / amp1) if amp1 else float("nan")})
    res["harmonics"].sort(key=lambda h: h["k"])
    matched_k = {h["k"] for h in res["harmonics"]}
    res["missing"] = [k for k in range(1, max_order + 1)
                      if k * f0 <= fmax and k not in matched_k]
    by_amp = sorted(res["harmonics"], key=lambda h: -h["amp"])
    res["strongest"] = by_amp[0] if by_amp else None
    res["second"] = by_amp[1] if len(by_amp) > 1 else None
    return res


# ============================================================ 打印报告

def format_report(csv_path, meta, f, amp, nf, result):
    """把结论字典排成给人看的一段文字"""
    r = result
    axis = meta.get("measurement_axis", meta.get("axis", "?"))
    fs = meta.get("fs_config_hz", meta.get("fs_hz", meta.get("fs", "-")))
    per_frame = meta.get("window_samples", meta.get("frame_n", meta.get("per_frame", "-")))
    nf_txt = ("%d 帧" % nf) if nf else "外部谱线"
    L = []
    L.append("================= 谐波族分析 =================")
    L.append("文件        : %s" % csv_path)
    L.append("记录/工况   : %s / %s -> %s   设备 %s" %
             (meta.get("record_id", "legacy"), meta.get("observed_condition", "unknown"),
              meta.get("target_label", "unassigned"), meta.get("device_id", "legacy_unknown")))
    L.append("轴号        : %s        采样率 %s Hz        每帧 %s 点 (平均 %s)"
             % (axis, fs, per_frame, nf_txt))
    L.append("频率分辨率  : %.3f Hz/格        分析频段 %.1f~%.1f Hz        峰阈值 %.1f%% 最大峰"
             % (r["df"], r["fmin"], r["fmax"], 100.0 * r["rel_thresh"]))

    L.append("机械 1×范围 : %.1f~%.1f Hz（本设备 TACH 已验证约 50~100 Hz）"
             % (r["f0_min"], r["f0_max"]))

    if r["f0"] is None:
        L.append("")
        L.append("[结果] 在已验证的机械 1× 范围内没有找到可用谱峰。")
        L.append("  · 先确认本次 CSV 与 TACH 是否为同一设备、同一供电/工况；")
        L.append("  · 若已录入实测 RPM，请检查其是否与本次采集同步；")
        L.append("  · 仅在更换设备或有新的 TACH 证据后，才调整 --f0min/--f0max。")
        return "\n".join(L)

    ks = "/".join("%d×" % h["k"] for h in r["harmonics"])
    L.append("")
    L.append("[基频 f0]")
    if not r["reliable"]:
        L.append("  警告      : 峰本底比只有 %.1f, 这一段几乎没有振动 —— 下面的基频和转速不可信"
                 % r["snr"])
    if r["source"] == "tach":
        L.append("  机械 1×   : %.2f Hz    （由同工况实测 TACH %.0f rpm 锁定）"
                 % (r["f0"], r["rpm_measured"]))
        if r["one_x_detected"]:
            L.append("  1× 实测峰 : %.2f Hz    （与 TACH 相差 %.2f Hz）"
                     % (r["f0_peak"], abs(r["f0_peak"] - r["f0"])))
        else:
            L.append("  1× 实测峰 : 未检出（TACH 仍是机械转速的权威值）")
        L.append("  实测转速  : %.0f rpm" % r["rpm"])
    else:
        L.append("  基频峰    : %.2f Hz    （已验证机械 1×范围内幅值最高的实际谱峰）" % r["f0"])
        L.append("  估计转速  : %.0f rpm    （基频峰 × 60；需同工况 TACH 才能确认）" % r["rpm"])

    L.append("")
    L.append("[倍频强弱]")
    s1, s2 = r["strongest"], r["second"]
    if s1:
        L.append("  最强倍频  : %2d×  %7.2f Hz    幅值 %.5f g    (相对 1× : %.1f%%)"
                 % (s1["k"], s1["f_peak"], s1["amp"], s1["ratio"]))
    if s2:
        L.append("  第二强倍频: %2d×  %7.2f Hz    幅值 %.5f g    (相对 1× : %.1f%%)"
                 % (s2["k"], s2["f_peak"], s2["amp"], s2["ratio"]))
    else:
        L.append("  第二强倍频: 无(这一族里只找到 1 个峰)")

    L.append("")
    L.append("[谐波族明细]   k×f0 与实测峰对照")
    L.append("   %-4s %12s %12s %12s %10s" % ("k", "理论频率", "实测峰频", "幅值(g)", "相对 1×"))
    for h in r["harmonics"]:
        L.append("   %-4s %9.2f Hz %9.2f Hz %12.5f %9.1f%%"
                 % ("%d×" % h["k"], h["f_theory"], h["f_peak"], h["amp"], h["ratio"]))
    if r["missing"]:
        miss = ", ".join("%d× = %.2f Hz" % (k, k * r["f0"]) for k in r["missing"])
        L.append("   没匹配到峰: %s  (这些倍频处没有超过阈值的峰)" % miss)

    L.append("")
    L.append("[机械 1×候选]   只列已验证范围内的实际谱峰；不再把其子谐波反推为基频")
    top = r["candidates"][0]["amp"] if r["candidates"] else 1.0
    for i, c in enumerate(r["candidates"], 1):
        L.append("  %d) %8.2f Hz   幅值 %.5f g（相对最高 %.1f%%）   匹配 %d 个峰"
                 % (i, c["f0"], c["amp"], 100.0 * c["amp"] / top if top > 0 else 0.0, c["n"]))

    L.append("")
    L.append("[提示]")
    if r["reliable"]:
        L.append("  · 峰本底比 %.1f (最强峰 / 频段幅值中位数), ≥ %.0f 视为信号可信"
                 % (r["snr"], SNR_MIN))
    else:
        L.append("  · 警告: 峰本底比只有 %.1f (< %.0f), 频谱里没有明显谐波, 上面的基频和转速不可信"
                 % (r["snr"], SNR_MIN))
    if r["source"] != "tach":
        L.append("  · 当前没有同工况 RPM：此处是频谱估计，不能替代独立测速。")
    L.append("  · 本风扇的 6 V/12 V TACH 机械 1×已实测为约 51.02/91.74 Hz；"
             "36.6 Hz 一类低频峰不再参与默认基频候选。")
    L.append("  · 采集时填写 rpm_measured（同设备、同供电、同工况的 TACH/转速计读数），"
             "工具会以 RPM/60 为机械 1×，再核对频谱。")
    return "\n".join(L)


# ============================================================ 画图(可选)

def plot_result(csv_path, f, amp, result, out_dir=OUT_DIR):
    """把频谱画出来, 并在每个 k×f0 的位置画竖虚线 —— 用眼睛确认"这些峰确实是一族" """
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.axvspan(result["f0_min"], result["f0_max"], color="tab:green", alpha=0.08,
               label="已验证机械 1×范围")
    ax.plot(f, amp, lw=0.8, color="tab:blue")
    for h in result["harmonics"]:
        ax.axvline(h["f_theory"], color="tab:red", ls="--", lw=0.7, alpha=0.7)
        ax.annotate("%d×" % h["k"], xy=(h["f_theory"], h["amp"]),
                    xytext=(3, 4), textcoords="offset points", color="tab:red", fontsize=9)
    ax.set_title("harmonic family: f0 = %.2f Hz  →  %.0f rpm" % (result["f0"], result["rpm"]))
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("amplitude (g)")
    ax.set_xlim(0, result["fmax"] * 1.05)
    ax.grid(True)
    ax.legend(loc="upper right")
    plt.tight_layout()

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    png = os.path.join(out_dir, os.path.splitext(os.path.basename(csv_path))[0] + "_harmonics.png")
    plt.savefig(png, dpi=120)
    print("图已保存  : %s" % png)
    plt.show()


# ============================================================ 主流程

def build_parser():
    p = argparse.ArgumentParser(description="谐波族分析: 找基频 f0 → 判断哪个倍频最强 → 推算转速")
    p.add_argument("csv", nargs="?", help="csv 路径; 不填则自动用 04_数据集\\raw 里最新的那个")
    p.add_argument("--fmin", type=float, default=DEFAULT_FMIN, help="分析下限 Hz (默认 %g)" % DEFAULT_FMIN)
    p.add_argument("--fmax", type=float, default=DEFAULT_FMAX, help="分析上限 Hz (默认 %g)" % DEFAULT_FMAX)
    p.add_argument("--f0min", type=float, default=DEFAULT_F0_MIN,
                   help="机械 1×候选下限 Hz (默认 %g)" % DEFAULT_F0_MIN)
    p.add_argument("--f0max", type=float, default=DEFAULT_F0_MAX, help="候选基频上限 Hz (默认 %g)" % DEFAULT_F0_MAX)
    p.add_argument("--thresh", type=float, default=DEFAULT_THRESH, help="峰阈值 = 最大峰幅值的比例 (默认 %g)" % DEFAULT_THRESH)
    p.add_argument("--max-order", dest="max_order", type=int, default=DEFAULT_MAX_ORDER,
                   help="最多找几次倍频 (默认 %d)" % DEFAULT_MAX_ORDER)
    p.add_argument("--rpm-measured", type=float,
                   help="同工况 TACH/转速计的实测 RPM；提供后以 RPM/60 锁定机械 1×")
    p.add_argument("--spectrum", action="store_true", help="输入是已经 FFT 好的两列数据(频率Hz,幅值)")
    p.add_argument("--plot", action="store_true", help="顺便画频谱图并标注 k×f0, 存到 05_演示与输出")
    return p


def pick_latest_csv():
    """没给路径时，在正式、调试、旧版目录中挑最新 CSV。"""
    cands = []
    for directory in DATA_DIRS:
        if os.path.isdir(directory):
            cands.extend(os.path.join(directory, x) for x in os.listdir(directory)
                         if x.lower().endswith(".csv"))
    return max(cands, key=os.path.getmtime) if cands else None


def main():
    args = build_parser().parse_args()

    csv_path = args.csv or pick_latest_csv()
    if not csv_path:
        print("没给 csv 路径, 也在 %s 下没找到 csv —— 先跑 recv.py 采一段数据" % RAW_DIR)
        return 1
    if not os.path.isfile(csv_path):
        print("找不到文件: %s" % csv_path)
        return 1

    if args.spectrum:
        f, amp = load_spectrum_csv(csv_path)
        meta, nf = {"axis": "-", "fs": "-", "per_frame": "-"}, None
    else:
        meta, samples = load_csv(csv_path)
        fs = int(meta.get("fs_config_hz", meta.get("fs_hz", meta.get("fs", frames.FS_HZ))))
        n = int(meta.get("window_samples", meta.get("frame_n", meta.get("per_frame", frames.MAX_N))))
        afs_code = int(meta.get("afs_code", 0))
        f, amp, nf = average_spectrum(samples, fs, n, afs_code)

    rpm_measured = args.rpm_measured
    if rpm_measured is None and not args.spectrum:
        rpm_measured = meta.get("rpm_measured")
    result = analyze(f, amp, fmin=args.fmin, fmax=args.fmax,
                     f0_min=args.f0min, f0_max=args.f0max,
                     rel_thresh=args.thresh, max_order=args.max_order,
                     rpm_measured=rpm_measured)
    print(format_report(csv_path, meta, f, amp, nf, result))

    if args.plot and result["f0"] is not None:
        plot_result(csv_path, f, amp, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ============================================================ 当前算法说明
#
# 机械 1×以同工况 TACH/转速计为最高优先级：f0 = RPM / 60。未提供实测 RPM 时，
# 只在本风扇已验证的 45~105 Hz 范围内选择实际谱峰；绝不再从 36.6 Hz 等子谐波
# 回推基频。下面保留的旧注释仅说明已移除的历史算法，不是当前行为。
#
# ============================================================ 已废止的历史算法说明
#
# 1) 为什么不直接把"最大峰"当基频?
#    风扇的频谱是"一族"峰: f0 的 1 倍、2 倍、3 倍…都在。最强的那根不一定就是 1×:
#    不平衡时 1× 最强, 松动/不对中时 2× 最强, 叶片通过频率又可能是叶片数倍。
#    所以不能只看谁最大, 要看"哪个频率能同时罩住好几根峰" —— 这就是梳状(comb)打分。
#
# 2) 梳状打分: 对每个候选 f0 算 得分 = Σ A(k×f0) / k
#    A(k×f0) 是 k×f0 附近那个峰的幅值(容差取 1.5%, 最大 8 Hz);
#    除以 k 是因为"第几次谐波"越靠前越说明它就是基频。
#    若不除 k, 任何 f0/2 的候选都能把同样的峰当成偶数次谐波凑进来, 反而占便宜。
#
# 3) 供电频段先验(本次修改): 铭牌 2300~3500 rpm 是 12V 满供电的值。
#    实际供电在 6/9/12V 之间切换, 转速近似按 V/12 比例变化, 于是
#        12V: 38.3~58.3 Hz    9V: 约 25.3~49.0 Hz    6V: 约 16.9~32.7 Hz
#    (两端各放宽 SUPPLY_TOL=12% 罩住非线性与个体差异)
#    最终得分 = 梳状得分 × 频段先验:
#      · f0 落在某个应有频段内           → ×BAND_BONUS(1.6), 救回"很弱但合理"的 1×
#      · f0 不在频段内、而 f0/2 在频段内  → ×HARM2_PENALTY(0.5), 压住"幅值高的 2×"
#       (小型无刷风扇常见: 4 极/2 对极, 电磁力频率正好 = 2× 机械频率, 所以 2× 比 1× 强)
#    另外频段内单独用更宽松的 BAND_THRESH=1% 找峰, 免得很弱的 1× 连候选都进不去。
#    电压来源: --supply auto 先从文件名(fan6v/fan9v/fan12v)猜, 猜不到就三个电压都试;
#    也可以 --supply 9 强制, 或 --supply none 完全关闭(退回旧版纯梳状打分)。
#
# 4) 拟合: 命中 1×/2×/3×/4× 之后, 用这些峰做幅值加权最小二乘, 反推更准的 f0
#    —— 因为峰不一定正好落在格子上, 单个峰的读数有 ±半格误差, 用整族一起估更稳。
#
# 5) 转速换算: 转速(rpm) = f0(Hz) × 60。f0 就是转子的转动频率(1×)。
#
# 6) 歧义(必须知道): 只看一张频谱, f0 和 f0/2 在数学上都说得通 ——
#    若真实转速的 1× 很弱、2× 最强, 频段先验能把 f0/2 拉回来; 但先验依赖"供电电压"这一前提。
#    最硬的证据是变电压实测: 6V/9V/12V 各测一段, 跟着电压成比例移动的峰才是同一族。
