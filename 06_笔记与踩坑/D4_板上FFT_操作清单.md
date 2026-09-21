# D4 操作清单：把 FFT 搬到板上（CMSIS-DSP 1024 点实数 FFT + Hann 窗）

> 配套代码：`00_工程文件\APP\dsp_fft.h`、`00_工程文件\APP\dsp_fft.c`（已按项目习惯写成 GBK 编码）。
> 本清单按"一天 4–6 h"排：第 0–3 步约 1 h，第 4 步约 1 h，第 5–6 步约 1.5 h，第 7–9 步约 1 h，剩下是缓冲。

---

## 今天要交的四样东西

1. Keil 编译通过、能烧录，固件里多了 `dsp_fft.c`；
2. 串口打印出 TOP-5 谱峰（`FFT seq=… / #1 bin=… f=… Hz amp=… mg`）；
3. 一张"板 vs PC"对照记录（同一窗、同一参数，频率差 ≤1 格、主要峰幅值差 ≤10%）；
4. 两个数字：`arm_rfft_fast_f32` 单次耗时（µs）、固件体积增量（Program Size）。

---

## 第 0 步：先备份（2 分钟，别省）

把整个 `00_工程文件` 复制一份到项目外，例如 `C:\Work\备份\00_工程文件_D3完成`。
理由：加 CMSIS-DSP 会动工程文件（`.uvprojx`）和编译选项，改坏了能一键回退，比事后排查便宜得多。

---

## 第 1 步：把 CMSIS-DSP 加进 Keil 工程

**本机实际情况（我已确认）**
- Keil 装在 `C:\Work\MDK5.43`；
- CMSIS 包：`C:\Work\MDK5.43\Packs\ARM\CMSIS\5.8.0`，另有 `ARM\CMSIS-DSP\1.16.2`；
- **两个包都只有源码（`DSP\Source`、`DSP\Include`），没有预编译的 `arm_cortexM4lf_math.lib`**。
  所以"复制一个 .lib 进工程"这条老路子在你机器上走不通，按下面 A 或 B 做。
- 当前工程 `Options for Target → Target`：**ARM Compiler 已是 AC6**、**FPU = Single Precision 已开**、**未勾 Use MicroLIB**、
  Include Paths = `..\..\User;..\..\Drivers;..\..\Drivers\CMSIS\Device\ST\STM32F4xx\Include;..\..\Drivers\CMSIS\Include;..\..\Drivers\ST\STM32F4xx_HAL_Driver\Inc;..\..\Middlewares;..\..\APP`。

### 方案 A（首选）：用 RTE 勾选

1. Keil 菜单 `Project` → `Manage` → `Run-Time Environment...`；
2. 展开 `CMSIS`，勾上 **DSP**（`Core` 一般会被自动带上，让它自动勾）；
3. 右边 `Resolve` 按钮若变红，点一下让它自动解决依赖；
4. `OK`。Keil 会把 DSP 源码加进工程的 RTE 分组，并自动补好 include 路径。

**可能会遇到的坑**：RTE 会带进 CMSIS 5.8.0 的 `Core`，而工程自己已经有一份 `Drivers\CMSIS\Include`，
两份 `core_cm4.h` / `cmsis_compiler.h` 可能撞车（报重复定义或宏未定义）。
处理顺序：
- ① 先只勾 DSP、取消勾 Core，看编译过不过；
- ② 还报错就把 `C:\Work\MDK5.43\Packs\ARM\CMSIS\5.8.0\CMSIS\Core\Include` 手写进 Include Paths（放最后一位），
  让工程原有的 CMSIS 优先被找到。

### 方案 B（RTE 走不通时的退路）：手工加

1. `Options for Target` → `C/C++` → `Include Paths` 追加两行：
   `C:\Work\MDK5.43\Packs\ARM\CMSIS\5.8.0\CMSIS\DSP\Include`
2. 右键工程里新建一个组（如 `Middlewares/CMSIS-DSP`），`Add Existing Files to Group` 添加这些源文件（全在
   `C:\Work\MDK5.43\Packs\ARM\CMSIS\5.8.0\CMSIS\DSP\Source\` 下）：
   - `TransformFunctions\arm_rfft_fast_f32.c`
   - `TransformFunctions\arm_rfft_fast_init_f32.c`
   - `TransformFunctions\arm_cfft_f32.c`
   - `TransformFunctions\arm_cfft_init_f32.c`
   - `TransformFunctions\arm_bitreversal_32.c`（或 `arm_bitreversal2.S`）
   - `ComplexMathFunctions\arm_radix8_butterfly_f32.c`（若报 `undefined arm_radix8_butterfly_f32` 就是缺它）
   - `CommonTables\arm_common_tables.c`
   - `CommonTables\arm_const_structs.c`
3. 链接报 `undefined symbol` 时，把 `Source\TransformFunctions` 与 `Source\CommonTables` 两个目录的文件**整目录加入**，再编译一次。

### 方案 C（最后一招）：先不依赖 DSP

`dsp_fft.c` 里的 `arm_rfft_fast_f32(&g_rfft, g_in, g_out, 0U);` 换成自己写的 1024 点基-2 实数 FFT（约 80 行，
输入输出接口保持一样），今天先把阶段 1/2 跑通，明天再换回 CMSIS-DSP。**不要为了集成库搭进去一整天。**

---

## 第 2 步：把 dsp_fft.c 加进工程（2 分钟）

Keil 左侧 Project 窗口 → 右键 **APP** 组 → `Add Existing Files to Group 'APP'` → 选
`..\..\APP\dsp_fft.c` → 文件类型选 `C Source file`。（`dsp_fft.h` 可加可不加，加进去只是为了在 Keil 里能看到。）

`dsp_fft.h` 里已经自己 `#include "arm_math.h"`，所以 `dsp_fft.c` 不用再额外写什么。

---

## 第 3 步：编译，先只编译不烧录

- 期望 `0 Error(s)`；警告里若出现 `-Winvalid-source-encoding`（usmart.c 那段）属无害，与今天无关；
- 记下 Build Output 里的 `Program Size: Code=… RO-data=… RW-data=… ZI-data=…`，**和加 DSP 之前那次的数字相减**，
  这就是"FFT 花了多少 Flash / RAM"。粗算：Flash 增量主要是旋转因子表（几十 KB 量级）；
  RAM 增量 = 3 个 4 KB 缓冲（`g_win`/`g_in`/`g_out`）+ 2 个约 2 KB 谱数组（`g_amp`/`g_work`）≈ 16 KB，
  外加自检用的 6 KB 静态窗（阶段 1 结束后若把 `dsp_fft_selftest()` 整个删掉可省下），合计约 22 KB。
- F407 有 1 MB Flash / 192 KB RAM，就算整包 DSP 全进也放得下，不必为体积纠结。

---

## 第 4 步：阶段 1 —— 桩信号自检（给算法对答案，不接传感器）

`main.c` 顶部加一行：

```c
#include "dsp_fft.h"
```

`main()` 里 `app_sample_init();` 之后、`while (1)` 之前加两行：

```c
    dsp_fft_init();          /* 算 Hann 窗表 + 初始化 1024 点 FFT 实例, 只调一次 */
    dsp_fft_selftest();      /* 板上造 45Hz/50mg + 90Hz/10mg, 对完答案就把这一行删掉 */
```

串口（460800，串口助手或 `python -m serial.tools.miniterm COM13 460800`）应看到：

```
dsp_fft_init OK: N=1024, df=0.9766 Hz, cpu=168 MHz
---- selftest: 45Hz/50mg + 90Hz/10mg + DC 990mg ----
FFT seq=0 n=1024 mean=990 mg cycles=xxxxx (xxx us)
  #1 bin=46 f=44.92 Hz amp=50 mg
  #2 bin=92 f=89.84 Hz amp=10 mg
---- expect: #1 f=44.92Hz amp=50mg, #2 f=89.84Hz amp=10mg ----
```

> **日志为什么是英文**：`dsp_fft.c` 的 `APP_LOG` 字符串全部用 ASCII 写，中文只留在注释里。两个原因：
> ① 源文件是 GBK 编码，字符串里的中文在 AC6 下会新增 5 条 `-Winvalid-source-encoding` 警告（和 usmart.c 同类，无害但没必要新增）；
> ② 这些行要和 PC 端 `peak_check.py` 的输出逐行 diff，纯 ASCII 不受串口助手编码设置影响。
> 我已用 armclang 对 `dsp_fft.c` 单独做过语法检查：**0 error、0 warning**。
> 若你更想和 `main.c` 里的中文日志统一，说一声我换回中文（代价就是那 5 条警告）。

判定：**频率对上 44.92 / 89.84 Hz 就算通了**（和 PC 端 `plot_check.py` 之前的 44.92 / 89.84 完全一致）；
幅值允许 ±2 mg 的偏差（int16 量化 + 单精度浮点的正常误差）。
如果频率整体偏移 → 查 `df`、`APP_FS_HZ`、以及是不是把 `g_out` 的打包顺序取错了；
如果幅值只有一半 → 十有八九是漏了 Hann 的相干增益 0.5（第 4.4 节的公式）；
如果 0 Hz 附近有一根巨大的线 → 去均值那段被跳过了。

---

## 第 5 步：阶段 2 —— 接真实数据

把 `main.c` 主循环里"满窗就发帧"那段改成：

```c
        if (app_sample_window_ready())          /* 攒满一窗 */
        {
            const sample_window_t *w = app_sample_window_get();
            dsp_fft_result_t fft_res;

            app_sample_pause(1);                /* 处理期间暂停采样, 保证窗内样本等间隔 */
            dsp_fft_run(w, 'Z', &fft_res);      /* 先算 FFT(几百微秒) */
            dsp_fft_print(&fft_res);            /* 再打印(每窗 6 行, 几毫秒) */
            link_frame_send(w, 'Z');            /* 原来的发帧照旧, 供 PC 对拍 */
            app_sample_pause(0);

            app_sample_window_release();
        }
```

**为什么 FFT 和打印必须放进 `pause(1)`/`pause(0)` 之间**：
采样靠 1 ms 的 TIM3 中断置一个 `g_tick` 标志，主循环去清。主循环若被 FFT + 打印占住超过 1 ms，
这一拍没被处理，`g_tick` 会被覆盖，**这一个样本就永久丢了**。这和 Q-04 里 `iic_delay` 从 2 µs 改成 10 µs
导致实际采样率掉到约 600 Hz 是同一类问题。发帧本来就放在 pause 区间里，FFT 跟着一起放最省事。

---

## 第 6 步：阶段 2 —— 与 PC 端逐行对拍

板上打印是"每窗 TOP-5"，PC 端也要用**同一套参数**打印：去均值、`np.hanning`、单边幅值 `2|X|/(N*0.5)`、
只在 10–400 Hz 找峰、取一个峰后左右各清 2 格、取 5 个。
下面这段可直接存成 `03_Python工具\peak_check.py`（读完能直接把两边输出贴在一起比）：

```python
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
```

对拍做法：跑一次采集，板上串口会把 `seq=1..20` 每窗打印一遍；PC 端对同一个 CSV 跑 `peak_check.py`，
**只挑同一个 seq 的两组输出比**（不同窗的数据本来就不同，不能混着比）。比较表：

| seq | 板上 #1 | PC #1 | 频率差 | 板上 #1 幅值 | PC #1 幅值 | 幅值相对差 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | |
| 2 | | | | | | |

验收：主要峰频率差 ≤1 格（0.98 Hz）；主要峰幅值相对差 ≤10%。
对不上时按这个顺序二分：① 是不是同一个 seq；② 轴上是不是都取的 Z；③ 量程/灵敏度是否同源；
④ 窗函数是否一致；⑤ 取峰 guard 是否一致。

---

## 第 7 步：采样时序体检（约 30 分钟，别跳过）

Q-03 记过"稳态每秒约 957 点"。这件事对 FFT 有直接影响：

- 若"暂停"发生在**两次发帧之间**（窗口外），1024 点仍是一段等间隔的连续采样，谱是干净的；
- 若暂停发生在**窗口内部**，这段窗就有时间断点，谱线会展宽、底部抬高，幅值也会不准。

做法（不用示波器）：
1. 在取窗前后各读一次 `app_sample_count()`，打印差值：满窗时差值应该正好是 1024；
   若小于 1024，说明**窗内有样本被丢**（此时先查是不是有别的 printf 占住了主循环）。
2. 在主循环里把 `HAL_GetTick()` 和 `app_sample_count()` 一起打印，算"1024 点实际跨了多少毫秒"：
   理想值 1024 ms。明显偏大（例如 1070 ms）说明暂停落在了窗内，需要把"采样"和"发帧/FFT"真正解耦
   （双缓冲 + 让发帧不阻塞采样），这属于 D3 的遗留问题，**记下来，今天不必修**。

---

## 第 8 步：性能数字（约 20 分钟）

`dsp_fft_print()` 已经打印了 `cycles=… (… us)`，这就是 `arm_rfft_fast_f32` 单次耗时。
把它和 §1.2 的目标（单帧 FFT + 推理 < 10 ms）一起写进记录：目前只有 FFT，没有推理，
真实数据是几百微秒量级（1024 点 rfft 在 168 MHz M4F 上通常 0.1–0.3 ms）。

---

## 第 9 步：沉淀（约 30 分钟）

1. 把今天的原始记录（串口输出原文、对照表、报错与排查）写进 `06_笔记与踩坑\`；
   之后你说一句"记录这个问题和回答"，我再按 §18 的 8 项模板整理成 **Q-05** 并同步 §19 修订记录
   （按约定：改文档前我先把改动点列给你）。
2. `git init` + 首次提交（当前 `C:\Work\嵌入式练习` 还不是仓库）。`.gitignore` 先挡掉：
   `*.o`、`*.axf`、`*.hex`、`*.htm`、`*.lnp`、`*.map`、`Objects/`、`Listings/`、`Output/`、
   `.conda/`、`__pycache__/`、`*.uvguix.*`、`*.uvoptx`、`04_数据集/raw/*.csv`（数据集另想办法）。
3. 今天的"看得见的中间成果"图：把 PC 端频谱图（`plot_check.py` 默认输出到 `05_演示与输出`）留一张，
   文件名带上工况标签，别再用 `notag`。

---

## 报错对照表

| 报错 / 现象 | 大概原因 | 怎么办 |
| --- | --- | --- |
| `cannot open source input file "arm_math.h"` | DSP 的 Include 路径没加 | 走第 1 步方案 A 或 B |
| `undefined symbol arm_bitreversal_32` | 手工加文件时漏了反位序实现 | 加 `arm_bitreversal_32.c` 或 `arm_bitreversal2.S` |
| `undefined symbol arm_radix8_butterfly_f32` | 漏了蝶形运算文件 | 加 `arm_radix8_butterfly_f32.c` |
| `undefined symbol arm_common_tables` / 旋转因子表 | 漏了 `CommonTables` | 加 `arm_common_tables.c`、`arm_const_structs.c` |
| `core_cm4.h` 相关重复定义 / 宏缺失 | RTE 的 CMSIS Core 与工程自带 CMSIS 撞车 | 取消勾 Core，或把 pack 的 Core\Include 加到 Include Paths 末尾 |
| 串口打印 `%f` 出来是空白或乱码 | 浮点打印支持问题（本工程未用 microLIB，但没必要冒险） | 本模块已全部用整数打印（Hz 的百倍整数、mg），不要改回 `%f` |
| 峰频率整体偏大 1.67 倍等 | 实际采样率与 `APP_FS_HZ` 不一致（历史上 `iic_delay` 改 10 µs 出过） | 先量实际采样率（第 7 步），再决定改 `iic_delay` |
| 所有峰都在第 0/1 格 | `g_out` 打包格式取错，或忘了去均值 | 对照第 4.4 节注释 |

---

## 一个需要你确认的口径问题（今天顺手定掉）

规划文档 §4.3（v0.19）写的是"**本项目一律按重力压在 Y 轴处理**"，但实测和现有数据不是这样：

- `main.c` 现在发的是 `link_frame_send(w, 'Z')`；
- `04_数据集\raw` 里三个 CSV 头部都是 `axis=Z`，静止时 Z 轴读数约 17000 格 ≈ 1.04 g。

也就是说：**实际装好后重力压在 Z 轴**，文档的 Y 轴口径已经和现实不符。
`dsp_fft.c` 我按现实写的（默认 Z 轴），调用时也显式传 `'Z'`。建议把 §4.3 / §6.3 的口径改成 Z 轴
（或明确写成"以静止时读数接近 ±1 g 的那个轴为准，当前为 Z"）。
要改的话你说一声，我先列改动点再落地，并在 §19 登记一行。

---

## 退路（今天卡住时按顺序用）

1. DSP 集成超过 1.5 h → 方案 C（自写 FFT），今天先保阶段 1/2 通过；
2. 阶段 2 对不上 → 只对阶段 1（桩信号）也算今天合格，把真实数据对拍挪到明天；
3. 时间不够 → 砍第 7、8 步，保第 4、6、9 步；
4. **不要拉成三天**：宁可交"桩信号通了 + 记录完整"，也不要交"什么都没跑通但在调库"。
