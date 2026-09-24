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
    python harmonics.py <csv> --supply 9       # 强制按 9V 的应有频段分析
    python harmonics.py <csv> --supply auto    # 默认: 先看文件名里有没有 fan6v/9v/12v, 没有就三个电压都试
    python harmonics.py <csv> --supply none    # 关闭频段先验, 退回旧版纯梳状打分
    python harmonics.py <csv> --rpm-range 0:0  # 关掉铭牌转速核对

常用可选参数:
    --fmin 10       分析下限 Hz      --fmax 400     分析上限 Hz
    --f0max 120     候选基频的上限 Hz(转速上限 = 这个数 × 60)
    --thresh 0.08   峰阈值: 幅值不到"最大峰 × 8%"的不算峰
    --rpm-range 2300:3500   12V 满供电下的铭牌转速范围(6/9V 由它按 V/12 折算)
    --supply auto   供电电压: auto / 6 / 9 / 12 / 6,9,12 / none

算法说明见文件末尾。
"""
import argparse
import os
import re
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
DEFAULT_F0_MAX    = 120.0     # 候选基频上限 Hz → 转速上限 7200 rpm
DEFAULT_THRESH    = 0.08      # 峰阈值(相对最大峰)
DEFAULT_MAX_ORDER = 10        # 最多看几次倍频
DEFAULT_RPM_RANGE = "2300:3500"   # 已购 6cm 12V 风扇"12V 满供电"铭牌转速(规划 §4.2 / 附录 A)
DEFAULT_SUPPLY    = "auto"        # 供电电压: auto=从文件名猜, 猜不到就把 6/9/12V 都试
TOL_PCT           = 0.015     # 匹配容差: 允许 k×f0 与实测峰差 1.5%
TOL_CAP           = 8.0       # 但容差最大不超过 8 Hz(防高次倍频乱匹配)
SNR_MIN           = 6.0       # 峰本底比低于这个数就认为"没测到有效振动"

# ---- 供电电压 → 应有基频频段(本次修改的核心)---------------------------------
# 铭牌 2300~3500 rpm 是"12V 满供电"下的转速; 实际供电在 6/9/12V 之间切换,
# 直流小风扇在正常工作区转速近似与供电电压成正比, 所以 V 伏下:
#     转速 ≈ 12V 铭牌转速 × V/12      →      1× 频率 ≈ 转速 / 60
SUPPLY_VOLTAGES = (6.0, 9.0, 12.0)    # 实际会切换到的供电电压
SUPPLY_TOL      = 0.12    # 线性折算只是近似(低压端更不准 + 个体差异), 频段两端再各放宽 12%
BAND_BONUS      = 1.6     # 候选基频落在某个电压的应有频段内 → 得分加成
HARM2_PENALTY   = 0.5     # 候选基频不在任何频段、但它的 1/2 在频段内 → 它更像 2×, 得分打折
BAND_THRESH     = 0.01    # 频段内单独用的更宽松峰阈值(1%), 免得"很弱的 1×"连候选都进不了


# ============================================================ 读数据

def read_meta(path):
    """统一读取新 JSON 头，并兼容旧版 k=v 头。"""
    return metadata.read_meta(path)


def load_csv(path):
    """读 recv.py 存下的 csv: 返回 (元数据字典, 全部 int16 原始计数)
    一行一个数, 整个文件是"帧1的1024点 + 帧2的1024点 + ..."拼起来的"""
    meta = read_meta(path)
    samples = np.loadtxt(path, comments="#", dtype=np.int16)
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
    data = np.loadtxt(path, comments="#", delimiter=delim)
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


# ============================================================ 供电电压 → 应有频段

def supply_bands(rpm_range, voltages=SUPPLY_VOLTAGES, extra_tol=SUPPLY_TOL):
    """把"12V 铭牌转速范围"折算成每个供电电压下"应有的 1× 频段"
    转速 ≈ 12V 铭牌转速 × (V/12); f = rpm/60; 两端各自放宽 extra_tol 以罩住非线性与个体差异。
    返回 {电压: (f_lo, f_hi)}; rpm_range 为空或 voltages 为空则返回 {}"""
    if not rpm_range or not voltages:
        return {}
    lo_rpm, hi_rpm = rpm_range
    out = {}
    for v in voltages:
        k = float(v) / 12.0
        out[float(v)] = (lo_rpm * k / 60.0 * (1.0 - extra_tol),
                         hi_rpm * k / 60.0 * (1.0 + extra_tol))
    return out


def bands_of(freq, bands):
    """freq 落在哪些电压的应有频段里(频段之间会重叠, 可能命中不止一个)"""
    return [v for v, (lo, hi) in bands.items() if lo <= freq <= hi]


def in_band(freq, bands):
    return bool(bands_of(freq, bands))


def band_factor(f0, bands):
    """频段先验(评分用的权重): 救回"很弱但合理"的 1×, 压住"幅值高的 2×"
    · f0 落在任何应有频段内            → ×BAND_BONUS   (它才像是真正的机械 1×)
    · f0 不在频段内, 但 f0/2 在频段内   → ×HARM2_PENALTY (它更像某个 1× 的 2×, 例如电频率=2×机械频率)
    · 其余                             → ×1.0"""
    if not bands:
        return 1.0
    if in_band(f0, bands):
        return BAND_BONUS
    if in_band(f0 / 2.0, bands):
        return HARM2_PENALTY
    return 1.0


_SUPPLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*v", re.I)


def guess_supply_from_name(path):
    """从文件名里猜供电电压(数据命名约定形如 ..._fan9v_...); 猜不到返回 []
    只认离 6/9/12V 最近、误差在 20% 以内的数字, 免得把别的数字(如电压上限)当成风扇供电"""
    name = os.path.basename(path or "")
    hits = []
    for m in _SUPPLY_RE.finditer(name):
        v = float(m.group(1))
        near = min(SUPPLY_VOLTAGES, key=lambda x: abs(x - v))
        if abs(near - v) <= 0.2 * near:
            hits.append(near)
    return sorted(set(hits))


def parse_supply(text, csv_path=None):
    """--supply 的解析:
    'auto'/''      → 先看文件名里有没有 fan6v/9v/12v, 没有就把 6/9/12V 全试
    'none'/'off'   → [] 关闭频段先验(退回旧版纯梳状打分)
    '9' / '6,9,12' → 指定电压(可多个); None 表示"用全部已配置电压" """
    t = (text or "auto").strip().lower()
    if t in ("none", "off"):
        return []
    if t in ("", "auto"):
        g = guess_supply_from_name(csv_path) if csv_path else []
        return g or list(SUPPLY_VOLTAGES)
    vals = []
    for part in t.replace("/", ",").split(","):
        part = part.strip()
        if part:
            vals.append(float(part))
    return vals or None


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


def collect_peaks(f, amp, fmin, fmax, rel_thresh, bands):
    """正常阈值的峰, 再补上"频段内放宽阈值"的峰
    —— 真实 1× 可能很弱(不到最大峰的 8%), 只在频段内把它放进来, 别让它在候选阶段就被丢掉"""
    df = float(f[1] - f[0]) if f.size > 1 else 1.0
    peaks = find_peaks(f, amp, fmin, fmax, rel_thresh)
    if bands:
        relaxed = find_peaks(f, amp, fmin, fmax, min(rel_thresh, BAND_THRESH))
        peaks = merge_peaks(sorted(peaks + [p for p in relaxed if in_band(p[0], bands)],
                                   key=lambda p: p[0]), df)
    return peaks


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


def refine_f0(matches):
    """用匹配上的这些谐波峰反过来拟合更准的 f0: 幅值加权最小二乘
    目标: 找 f0 让 k×f0 尽量贴近实测峰频; 峰越大幅值越可信, 权重越大"""
    num = 0.0
    den = 0.0
    for k, p in matches:
        w = p[1]
        num += w * k * p[0]
        den += w * k * k
    return (num / den) if den > 0 else None


def parse_rpm_range(text):
    """'2300:3500' → (2300.0, 3500.0);  '0:0' 或空 → None(关闭核对)"""
    if not text:
        return None
    a, _, b = text.partition(":")
    lo, hi = float(a), float(b or a)
    return None if (lo <= 0 and hi <= 0) else (min(lo, hi), max(lo, hi))


def analyze(f, amp, fmin=DEFAULT_FMIN, fmax=DEFAULT_FMAX, f0_max=DEFAULT_F0_MAX,
            rel_thresh=DEFAULT_THRESH, max_order=DEFAULT_MAX_ORDER, rpm_range=None,
            supply=None, supply_tol=SUPPLY_TOL):
    """谐波族分析主函数: 谱线进 → 结论字典出(打印和画图都用这个字典)

    rpm_range: "12V 满供电"下的铭牌转速范围 (lo, hi); 传 None 就关闭频段先验(与旧版一致)
    supply   : 只采用这些供电电压的应有频段, 如 [9.0]; None = 全部 SUPPLY_VOLTAGES;
               传 [] = 不采用任何频段(等价于关闭先验)
    """
    f = np.asarray(f, dtype=np.float64)
    amp = np.asarray(amp, dtype=np.float64)
    df = float(f[1] - f[0]) if f.size > 1 else 1.0

    voltages = list(SUPPLY_VOLTAGES) if supply is None else list(supply)
    bands = supply_bands(rpm_range, voltages, supply_tol) if (rpm_range and voltages) else {}

    res = {"f0": None, "f0_peak": None, "rpm": None, "harmonics": [], "missing": [],
           "strongest": None, "second": None, "candidates": [], "half": None,
           "snr": 0.0, "reliable": False, "rpm_checks": [], "rpm_range": rpm_range,
           "n_peaks": 0,
           "fmin": fmin, "fmax": fmax, "f0_max": f0_max,
           "rel_thresh": rel_thresh, "max_order": max_order, "df": df,
           "bands": bands, "supply": voltages,
           "f0_band": [], "half_band": [], "suspect_2x": False}

    peaks = collect_peaks(f, amp, fmin, fmax, rel_thresh, bands)
    res["n_peaks"] = len(peaks)
    if not peaks:
        return res

    band = (f >= fmin) & (f <= fmax)
    noise = float(np.median(amp[band])) if band.any() else 0.0
    res["snr"] = (max(p[1] for p in peaks) / noise) if noise > 0 else float("inf")
    res["reliable"] = bool(res["snr"] >= SNR_MIN)

    # 候选基频 = 频段内每一个峰都可能才是 1×(频率不超过 f0_max)
    # 得分 = 梳状得分 × 频段先验:
    #   · 落在 6/9/12V 应有频段内 → ×BAND_BONUS, 让"很弱但更合理"的 1× 能和强峰抗衡
    #   · 不在频段内、却是某个频段内基频的 2× → ×HARM2_PENALTY, 压住"幅值高的 2×"
    scored = []
    for p in peaks:
        if fmin <= p[0] <= f0_max:
            s_comb, m = match_harmonics(p[0], peaks, fmax, 2.0 * df, max_order=max_order)
            fac = band_factor(p[0], bands)
            scored.append((p[0], s_comb * fac, s_comb, fac, m))
    if not scored:
        return res
    scored.sort(key=lambda x: (-x[1], x[0]))            # 得分高的在前; 得分一样取频率低的

    # 拿冠军候选再迭代拟合两次, 得到更准的 f0
    f0, matches = scored[0][0], scored[0][4]
    f0_peak = scored[0][0]
    for _ in range(2):
        s, m = match_harmonics(f0, peaks, fmax, 2.0 * df, max_order=max_order)
        if not m:
            break
        f0_new = refine_f0(m)
        if f0_new is None:
            break
        f0, matches = f0_new, m

    res["f0"] = f0
    res["f0_peak"] = f0_peak
    res["rpm"] = f0 * 60.0
    res["f0_band"] = bands_of(f0, bands)
    res["half_band"] = bands_of(f0 / 2.0, bands) if bands else []
    res["suspect_2x"] = bool(bands and not res["f0_band"] and res["half_band"])

    amp1 = next((p[1] for k, p in matches if k == 1), None)          # 1× 的幅值, 当相对基准
    for k, p in matches:
        res["harmonics"].append({
            "k": k, "f_theory": k * f0, "f_peak": p[0], "amp": p[1],
            "ratio": (100.0 * p[1] / amp1) if amp1 else float("nan"),
        })
    res["harmonics"].sort(key=lambda h: h["k"])
    matched_k = {h["k"] for h in res["harmonics"]}
    res["missing"] = [k for k in range(1, max_order + 1)
                      if k * f0 <= fmax and k not in matched_k]

    by_amp = sorted(res["harmonics"], key=lambda h: -h["amp"])       # 按幅值排名
    res["strongest"] = by_amp[0] if by_amp else None
    res["second"] = by_amp[1] if len(by_amp) > 1 else None

    # 候选基频列表(给用户看"还有别的可能"), 冠军位置换成拟合后的 f0
    top_score = match_harmonics(f0, peaks, fmax, 2.0 * df, max_order=max_order)[0]
    res["candidates"] = [{"f0": f0, "score": top_score * band_factor(f0, bands),
                          "comb": top_score, "factor": band_factor(f0, bands),
                          "n": len(matches), "band": res["f0_band"]}]
    for c_f0, c_total, c_comb, c_fac, c_m in scored:
        if abs(c_f0 - f0_peak) <= 2.0 * df:                          # 与冠军是同一个峰, 跳过
            continue
        res["candidates"].append({"f0": c_f0, "score": c_total, "comb": c_comb,
                                  "factor": c_fac, "n": len(c_m),
                                  "band": bands_of(c_f0, bands)})
        if len(res["candidates"]) >= 3:
            break

    # "把最强峰当成 2×"这个假设也要摆出来: 它的基频就是 f0/2
    # 单看一张频谱, f0 与 f0/2 都能解释同一批峰, 所以要给个分数让人自己看
    if f0 / 2.0 >= fmin:
        s_half, m_half = match_harmonics(f0 / 2.0, peaks, fmax, 2.0 * df, max_order=max_order)
        if m_half:
            res["half"] = {"f0": f0 / 2.0, "score": s_half, "n": len(m_half),
                           "band": bands_of(f0 / 2.0, bands)}

    # 转速核对: f0、f0/2、2×f0 各自落在哪些电压的应有频段里
    res["rpm_range"] = rpm_range
    if rpm_range:
        lo_r, hi_r = rpm_range
        for name, fac in (("f0", 1.0), ("f0/2", 0.5), ("2×f0", 2.0)):
            freq = f0 * fac
            rpm = freq * 60.0
            hit = bands_of(freq, bands)
            if bands:                                    # 有频段就按频段判
                ok = bool(hit)
            else:                                        # 没频段(如 --supply none)退回名义范围
                ok = bool(lo_r <= rpm <= hi_r)
            res["rpm_checks"].append({"name": name, "f": freq, "rpm": rpm,
                                      "in_range": ok, "bands": hit})
    return res


# ============================================================ 打印报告

def format_report(csv_path, meta, f, amp, nf, result):
    """把结论字典排成给人看的一段文字"""
    r = result
    axis = meta.get("measurement_axis", meta.get("axis", "?"))
    fs = meta.get("fs_hz", meta.get("fs", "-"))
    per_frame = meta.get("frame_n", meta.get("per_frame", "-"))
    nf_txt = ("%d 帧" % nf) if nf else "外部谱线"
    L = []
    L.append("================= 谐波族分析 =================")
    L.append("文件        : %s" % csv_path)
    L.append("记录/工况   : %s / %s -> %s   设备 %s   质量 %s" %
             (meta.get("record_id", "legacy"), meta.get("observed_condition", "unknown"),
              meta.get("target_label", "unassigned"), meta.get("device_id", "legacy_unknown"),
              meta.get("quality_status", "unknown")))
    L.append("轴号        : %s        采样率 %s Hz        每帧 %s 点 (平均 %s)"
             % (axis, fs, per_frame, nf_txt))
    L.append("频率分辨率  : %.3f Hz/格        分析频段 %.1f~%.1f Hz        峰阈值 %.1f%% 最大峰"
             % (r["df"], r["fmin"], r["fmax"], 100.0 * r["rel_thresh"]))

    if r["bands"]:
        band_txt = "   ".join("%gV 应有 1× %.1f~%.1f Hz" % (v, lo, hi)
                              for v, (lo, hi) in sorted(r["bands"].items()))
        L.append("供电频段    : %s" % band_txt)
        L.append("              (由 12V 铭牌 %s rpm 按 V/12 折算, 两端放宽 %.0f%%)"
                 % ("%.0f:%.0f" % r["rpm_range"] if r["rpm_range"] else "-", 100.0 * SUPPLY_TOL))
    else:
        L.append("供电频段    : 已关闭(只用梳状打分, 不做 6/9/12V 频段先验)")

    if r["f0"] is None:
        L.append("")
        L.append("[结果] 没有找到谐波族。可能原因:")
        L.append("  · 频段 %.1f~%.1f Hz 里没有超过阈值的峰 → 试试 --thresh 0.03 放松阈值"
                 % (r["fmin"], r["fmax"]))
        L.append("  · 基频超过了 --f0max %.0f Hz → 试试把 --f0max 调大" % r["f0_max"])
        L.append("  · 数据本身没有振动(先看时域波形) ")
        return "\n".join(L)

    ks = "/".join("%d×" % h["k"] for h in r["harmonics"])
    L.append("")
    L.append("[基频 f0]")
    if not r["reliable"]:
        L.append("  警告      : 峰本底比只有 %.1f, 这一段几乎没有振动 —— 下面的基频和转速不可信"
                 % r["snr"])
    L.append("  基频      : %.2f Hz    (由 %s 共 %d 个谐波峰拟合得出)"
             % (r["f0"], ks, len(r["harmonics"])))
    L.append("  1× 实测峰 : %.2f Hz    (与拟合基频相差 %.2f Hz)"
             % (r["f0_peak"], abs(r["f0_peak"] - r["f0"])))
    L.append("  推测转速  : %.0f rpm    (基频 × 60)" % r["rpm"])

    if r["bands"]:
        if r["f0_band"]:
            L.append("  频段核对  : f0 落在 %s 应有频段内 → 与供电电压自洽"
                     % "/".join("%gV" % v for v in r["f0_band"]))
        elif r["half_band"]:
            L.append("  频段核对  : f0 不在任何应有频段内, 但 f0/2 落在 %s 频段内"
                     " → 高度怀疑把 2× 当成了 1×" % "/".join("%gV" % v for v in r["half_band"]))
        else:
            L.append("  频段核对  : f0 与 f0/2 都不在应有频段内 → 核对供电电压/风机状态")

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
    L.append("[候选基频]   得分 = (Σ 幅值/k) × 频段先验; 频段内 ×%.1f, 疑为 2× ×%.1f"
             % (BAND_BONUS, HARM2_PENALTY))
    top = r["candidates"][0]["score"] if r["candidates"] else 1.0
    for i, c in enumerate(r["candidates"], 1):
        tag = ""
        if r["bands"]:
            if c["band"]:
                tag = "   [%s 频段]" % "/".join("%gV" % v for v in c["band"])
            elif bands_of(c["f0"] / 2.0, r["bands"]):
                tag = "   [疑为 2×]"
        L.append("  %d) %8.2f Hz   得分 %.3f   匹配 %d 个峰%s"
                 % (i, c["f0"], (c["score"] / top) if top > 0 else 0.0, c["n"], tag))
    if r["half"]:
        hb = r["half"]
        tag = ("   [%s 频段]" % "/".join("%gV" % v for v in hb["band"])) if hb.get("band") else ""
        L.append("  假设) %6.2f Hz   得分 %.3f   匹配 %d 个峰   ← f0 的一半: 把最强峰当成 2× 时%s"
                 % (hb["f0"], (hb["score"] / top) if top > 0 else 0.0, hb["n"], tag))

    L.append("")
    L.append("[提示]")
    if r["reliable"]:
        L.append("  · 峰本底比 %.1f (最强峰 / 频段幅值中位数), ≥ %.0f 视为信号可信"
                 % (r["snr"], SNR_MIN))
    else:
        L.append("  · 警告: 峰本底比只有 %.1f (< %.0f), 频谱里没有明显谐波, 上面的基频和转速不可信"
                 % (r["snr"], SNR_MIN))
    if r["bands"]:
        L.append("  · 供电约束: 铭牌转速 2300~3500 rpm 是 12V 满供电的值; 6/9V 供电时 1× 要按"
                 " 电压比例下移, 所以工具把落在 6/9/12V 应有频段内的候选加权 ×%.1f,"
                 % BAND_BONUS)
        L.append("    把“频段内基频的 2×”加权 ×%.1f —— 这样很弱但合理的 1× 不会被幅值高的 2× 顶掉。"
                 % HARM2_PENALTY)
        if r["rpm_checks"]:
            L.append("  · 转速核对(按频段):")
            for c in r["rpm_checks"]:
                if c["bands"]:
                    note = "在 %s 频段内" % "/".join("%gV" % v for v in c["bands"])
                else:
                    note = "不在任何频段"
                L.append("      %-5s %7.2f Hz → %6.0f rpm   %s" % (c["name"], c["f"], c["rpm"], note))
        if r["suspect_2x"]:
            L.append("      警告: 当前 f0 不在应有频段内, 而 f0/2 在 —— 极可能把 2× 当成了 1×;")
            L.append("            真实基频约为 %.2f Hz (%.0f rpm)。" % (r["f0"] / 2.0, r["rpm"] / 2.0))
    else:
        L.append("  · 单张频谱无法区分 f0 与 f0/2: 如果真实转速的 1× 很弱、2× 主导, 那么上面这个基频"
                 "其实是 2×, 真实基频只有它的一半(%.2f Hz, %.0f rpm)。"
                 % (r["f0"] / 2.0, r["rpm"] / 2.0))
        L.append("  · 打开供电约束可自动缓解这个歧义: 用 --supply auto/6/9/12 或默认的 --rpm-range")
    if r["bands"]:
        L.append("  · 判据回顾: 电源在 6V/9V/12V 之间切换、各测一段, 跟着电压成比例移动的那根才是"
                 "机械 1×; 固定不动的多半是结构共振。")
    return "\n".join(L)


# ============================================================ 画图(可选)

def plot_result(csv_path, f, amp, result, out_dir=OUT_DIR):
    """把频谱画出来, 并在每个 k×f0 的位置画竖虚线 —— 用眼睛确认"这些峰确实是一族" """
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(11, 5))
    for v, (lo, hi) in sorted(result.get("bands", {}).items()):
        ax.axvspan(lo, hi, color="tab:green", alpha=0.08)          # 该电压下 1× 应有的频段
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
    p.add_argument("--f0max", type=float, default=DEFAULT_F0_MAX, help="候选基频上限 Hz (默认 %g)" % DEFAULT_F0_MAX)
    p.add_argument("--thresh", type=float, default=DEFAULT_THRESH, help="峰阈值 = 最大峰幅值的比例 (默认 %g)" % DEFAULT_THRESH)
    p.add_argument("--max-order", dest="max_order", type=int, default=DEFAULT_MAX_ORDER,
                   help="最多找几次倍频 (默认 %d)" % DEFAULT_MAX_ORDER)
    p.add_argument("--rpm-range", dest="rpm_range", default=DEFAULT_RPM_RANGE,
                   help='12V 满供电下的铭牌转速范围, 如 2300:3500; 传 0:0 关闭 (默认 %s)' % DEFAULT_RPM_RANGE)
    p.add_argument("--supply", dest="supply", default=DEFAULT_SUPPLY,
                   help='供电电压: auto(默认, 先从文件名猜)/6/9/12/6,9,12/none(关闭频段先验)')
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
        fs = int(meta.get("fs_hz", meta.get("fs", frames.FS_HZ)))
        n = int(meta.get("frame_n", meta.get("per_frame", frames.MAX_N)))
        afs_code = int(meta.get("afs_code", 0))
        f, amp, nf = average_spectrum(samples, fs, n, afs_code)

    supply_text = args.supply
    if not args.spectrum and supply_text == DEFAULT_SUPPLY:
        explicit = meta.get("voltage_measured_v", meta.get("voltage_set_v"))
        if explicit not in (None, "", "?"):
            supply_text = str(explicit)
    result = analyze(f, amp, fmin=args.fmin, fmax=args.fmax, f0_max=args.f0max,
                     rel_thresh=args.thresh, max_order=args.max_order,
                     rpm_range=parse_rpm_range(args.rpm_range),
                     supply=parse_supply(supply_text, csv_path))
    print(format_report(csv_path, meta, f, amp, nf, result))

    if args.plot and result["f0"] is not None:
        plot_result(csv_path, f, amp, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ============================================================ 算法说明
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
