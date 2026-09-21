# 03_Python工具\test_harmonics.py
"""
功能: harmonics.py 的自检脚本 —— 用"已知基频的合成信号"验证工具找基频找得准不准
用法: python test_harmonics.py
说明: 不依赖 pytest, 只用 numpy。全部通过则退出码 0, 有任何一条失败则退出码 1。
      为什么要先写这个: 真实风扇的真实转速我们并不知道, 所以没法判断工具算得对不对;
      合成信号的基频是我们自己定的, 工具必须把这个已知答案找回来, 才说明算法可信。
"""
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 让本脚本能 import 同目录的 harmonics.py
import harmonics

FS = 1000          # 采样率 Hz, 与固件一致
N = 1024           # 每帧点数, 与固件一致
FRAMES = 20        # 帧数

_results = []      # [(用例名, 是否通过, 补充信息), ...]


def check(name, ok, detail=""):
    """记录一条自检结果并立刻打印"""
    _results.append((name, bool(ok), detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("    " + detail) if detail else ""))


def make_counts(f0, amps, noise=0.004, frames=FRAMES, n=N, fs=FS, seed=1):
    """造一段"已知基频"的加速度信号, 并换成固件那种 int16 原始计数
    f0   : 基频 Hz
    amps : {倍频 k: 幅值(g)}, 例如 {1: 0.5, 2: 0.1} 表示 1× 是 0.5g、2× 是 0.1g
    noise: 噪声标准差(g)
    返回 : int16 计数数组(长度 frames*n), 可直接喂给 harmonics.average_spectrum()
    """
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(frames):
        t = np.arange(n) / fs
        x = np.zeros(n)
        for k, a in amps.items():
            # 每帧给一个随机相位: 模拟"每次采集相位对不上", 检验平均谱不会把峰平均掉
            x += a * np.sin(2.0 * np.pi * k * f0 * t + rng.uniform(0.0, 2.0 * np.pi))
        x += rng.normal(0.0, noise, n)
        out.append(x)
    sig = np.concatenate(out)
    return np.clip(np.round(sig * 16384.0), -32768, 32767).astype(np.int16)   # afs_code=0 → 16384 格/g


def analyze_counts(counts, **kw):
    """计数 → 平均谱 → 谐波族分析, 走的是和 harmonics.py 主流程完全相同的代码路径"""
    f, amp, nf = harmonics.average_spectrum(counts, FS, N)
    return harmonics.analyze(f, amp, **kw), f, amp


# ---------------------------------------------------------------- 用例

def case_1_two_harmonics():
    """T1: 45 Hz 基频 + 90 Hz 二次谐波(幅值 5:1) —— 规划文档里合成桩函数的那组数"""
    print("T1  45Hz 基频 + 90Hz 二次谐波 (幅值比 5:1)")
    counts = make_counts(45.0, {1: 0.50, 2: 0.10})
    r, _, _ = analyze_counts(counts)

    check("T1.1 基频 ≈ 45 Hz", r["f0"] is not None and abs(r["f0"] - 45.0) <= 1.0,
          "实测 f0 = %.2f Hz" % (r["f0"] if r["f0"] else -1.0))
    check("T1.2 最强倍频是 1×", r["strongest"] is not None and r["strongest"]["k"] == 1,
          "最强 = %s" % (r["strongest"]["k"] if r["strongest"] else None))
    check("T1.3 第二强倍频是 2×", r["second"] is not None and r["second"]["k"] == 2,
          "第二强 = %s" % (r["second"]["k"] if r["second"] else None))
    check("T1.4 转速 ≈ 2700 rpm", abs(r["rpm"] - 45.0 * 60.0) <= 60.0, "实测 %.0f rpm" % r["rpm"])
    check("T1.5 信号可信", r["reliable"] is True, "峰本底比 %.1f" % r["snr"])


def case_2_fan_like_1x_and_4x():
    """T2: 模仿实测那台风扇 —— 1× 最强、4× 第二强, 2×/3× 很弱"""
    print("T2  78.8Hz 基频: 1×(1.00) 2×(0.12) 3×(0.06) 4×(0.83)")
    counts = make_counts(78.8, {1: 1.00, 2: 0.12, 3: 0.06, 4: 0.83})
    r, _, _ = analyze_counts(counts)

    check("T2.1 基频 ≈ 78.8 Hz", r["f0"] is not None and abs(r["f0"] - 78.8) <= 1.5,
          "实测 f0 = %.2f Hz" % (r["f0"] if r["f0"] else -1.0))
    check("T2.2 最强倍频是 1×", r["strongest"] is not None and r["strongest"]["k"] == 1,
          "最强 = %s×" % (r["strongest"]["k"] if r["strongest"] else None))
    check("T2.3 第二强倍频是 4×", r["second"] is not None and r["second"]["k"] == 4,
          "第二强 = %s×" % (r["second"]["k"] if r["second"] else None))
    check("T2.4 转速 ≈ 4728 rpm", abs(r["rpm"] - 78.8 * 60.0) <= 90.0, "实测 %.0f rpm" % r["rpm"])


def case_3_even_only_ambiguity():
    """T3: 只有偶数倍频(2× 最强、没有 1×) —— 数学上 39.4 Hz 和 78.8 Hz 都能解释,
           工具必须把这层歧义写进报告, 不能默不作声地给一个转速"""
    print("T3  只有偶数倍频: 2×(1.00) 4×(0.12) 6×(0.06) 8×(0.83)")
    counts = make_counts(39.4, {2: 1.00, 4: 0.12, 6: 0.06, 8: 0.83})
    r, f, amp = analyze_counts(counts)

    check("T3.1 找到了能罩住这些峰的基频族", r["f0"] is not None, "f0 = %.2f Hz" % (r["f0"] if r["f0"] else -1.0))
    check("T3.2 谐波阶层数 ≥ 2", len(r["harmonics"]) >= 2, "匹配到 %d 个峰" % len(r["harmonics"]))

    meta = {"axis": "Z", "fs": str(FS), "per_frame": str(N), "afs_code": "0"}
    text = harmonics.format_report("syn_39.4.csv", meta, f, amp, FRAMES, r)
    check("T3.3 报告里写明了 f0 与 f0/2 无法区分", ("一半" in text) and ("2×" in text),
          "报告含歧义提示")

    half = r["f0"] / 2.0
    check("T3.4 报告给出的另一半可能 ≈ 39.4 Hz", abs(half - 39.4) <= 1.5, "f0/2 = %.2f Hz" % half)
    check("T3.5 候选基频表里列出了 f0/2 这个假设",
          r["half"] is not None and abs(r["half"]["f0"] - 39.4) <= 1.5 and ("假设)" in text),
          "half 候选 = %.2f Hz" % (r["half"]["f0"] if r["half"] else -1.0))


def case_4_pure_noise():
    """T4: 只有噪声没有振动 —— 工具必须说"不可信", 不能硬编一个转速出来"""
    print("T4  纯噪声(无任何谐波)")
    counts = make_counts(0.0, {}, noise=0.02)
    r, _, _ = analyze_counts(counts)

    check("T4.1 标记为不可信", r["reliable"] is False, "峰本底比 %.1f" % r["snr"])


def case_5_csv_roundtrip():
    """T5: 走完整文件链路 —— 按 recv.py 的格式写 csv, 再让工具读回来分析
    临时文件就写在本脚本旁边的小目录里, 测完删掉(不污染 04_数据集)"""
    print("T5  按 recv.py 格式落盘的 csv 能正确读回")
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest_tmp")
    if not os.path.isdir(tmp):
        os.makedirs(tmp)
    try:
        path = os.path.join(tmp, "20260921_120000_notag_Z_syn45.csv")
        counts = make_counts(45.0, {1: 0.50, 2: 0.10})
        with open(path, "w", encoding="utf-8") as fp:
            fp.write("# axis=Z fs=%d afs_code=0 per_frame=%d frames=%d first_seq=1 last_seq=%d\n"
                     % (FS, N, FRAMES, FRAMES))
            fp.write("\n".join(str(int(v)) for v in counts))

        meta, samples = harmonics.load_csv(path)
        check("T5.1 读到元数据 fs/per_frame", meta.get("fs") == str(FS) and meta.get("per_frame") == str(N),
              "meta = %s" % meta)
        check("T5.2 读到的样本数与写出的一致", samples.size == counts.size,
              "%d vs %d" % (samples.size, counts.size))

        f, amp, nf = harmonics.average_spectrum(samples, int(meta["fs"]), int(meta["per_frame"]),
                                                int(meta["afs_code"]))
        check("T5.3 平均了 20 帧", nf == FRAMES, "nf = %d" % nf)
        r = harmonics.analyze(f, amp)
        check("T5.4 基频 ≈ 45 Hz", r["f0"] is not None and abs(r["f0"] - 45.0) <= 1.0,
              "f0 = %.2f Hz" % (r["f0"] if r["f0"] else -1.0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)      # 自检不留垃圾


def main():
    print("harmonics.py 自检 (合成信号, 已知基频)")
    print("-" * 64)
    case_1_two_harmonics()
    case_2_fan_like_1x_and_4x()
    case_3_even_only_ambiguity()
    case_4_pure_noise()
    case_5_csv_roundtrip()
    print("-" * 64)

    bad = [x for x in _results if not x[1]]
    print("共 %d 项检查, 通过 %d 项, 失败 %d 项" % (len(_results), len(_results) - len(bad), len(bad)))
    for name, _, detail in bad:
        print("  失败: %s   %s" % (name, detail))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
