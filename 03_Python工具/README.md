# Python 工具说明

本目录提供电机振动故障检测项目的 PC 端工具：从 STM32 串口接收加速度数据、保存并校验采集元数据、检查时域与频域结果、分析谐波，以及生成训练/测试划分清单。

请在**项目根目录**执行下面的命令。当前数据契约、目录约定和采集步骤以 [数据集说明](../04_数据集/README.md) 与 [采集操作手册](../04_数据集/采集操作手册.md) 为准。

## 环境与依赖

项目依赖见根目录的 `requirements.txt`：

- Python 3.13（项目默认环境为 `.conda\\python.exe`）
- `numpy`：数据读取、单位换算和 FFT
- `pyserial`：串口接收
- `matplotlib`：频谱绘图

首次配置或依赖缺失时，可执行：

```powershell
.\.conda\python.exe -m pip install -r .\requirements.txt
.\.conda\python.exe -c "import numpy, serial, matplotlib; print('依赖正常')"
```

下文以 `$Python` 表示 Python 解释器；若未使用项目环境，改为实际路径即可。

```powershell
$Python = '.\.conda\python.exe'
```

## 常用流程

```text
开发板串口帧
    │
    ▼
recv.py ──► formal/ 或 debug_raw/ CSV
    │                 │
    │                 ├──► check_raw.py（元数据与样本概览）
    │                 ├──► plot_check.py（时域/频谱图）
    │                 ├──► peak_check.py（与板端同口径的峰值）
    │                 └──► harmonics.py（基频、倍频与转速估计）
    ▼
formal/ + manifest.csv + 质检通过
    │
    ▼
make_dataset.py ──► processed/split_manifest.csv、summary.json
```

新采集数据固定使用 X 轴作为测量轴、Y 轴作为重力轴。`formal` 数据会自动登记到 `04_数据集/manifest.csv`，初始 `quality_status` 为 `pending`；仅完成质检并改为 `pass` 的记录会进入数据集划分。`debug`、`selftest` 和 `calibration` 均写入 `debug_raw/`，不登记训练清单。旧的 `04_数据集/raw/` 只为兼容历史文件而保留。

## 脚本索引

| 文件 | 用途 | 输入与输出 |
| --- | --- | --- |
| `recv.py` | 接收固件串口帧、校验标签并落盘 | 串口 → `formal/` 或 `debug_raw/` 的自描述 CSV；正式数据追加到 `manifest.csv`，板端文本日志写到 `05_演示与输出/boardlog/` |
| `check_raw.py` | 快速检查 CSV 元数据、样本数量、范围和负值比例 | 指定 CSV，或自动选择数据目录中最新 CSV；只读 |
| `plot_check.py` | 绘制首帧时域和单边幅值谱 | 指定 CSV，或自动选择最新 CSV；PNG 写入 `05_演示与输出/` |
| `peak_check.py` | 用板端 FFT 相同的 Hann 窗、10–400 Hz、TOP-5 和避让区规则打印每帧峰值 | 指定 CSV，或自动选择最新 CSV；只读 |
| `harmonics.py` | 谐波族分析：识别机械基频、主要倍频、估算转速与不确定性 | 原始 CSV，或 `--spectrum` 的两列频谱 CSV；`--plot` 时输出 PNG |
| `make_dataset.py` | 按设备留出测试集，避免同一设备的数据泄漏 | `manifest.csv` → `04_数据集/processed/split_manifest.csv` 与 `summary.json` |
| `kb_index.py` | 构建/检查项目知识库索引、链接和正式数据 manifest 一致性 | 写入 `知识库/索引/文档与模块索引.md`、`知识库/_generated/检查报告.md` |
| `py_common/frames.py` | PC 端串口帧协议唯一实现，以及原始 `int16` 到 `g` 的换算 | 被其他脚本导入，不单独运行 |
| `py_common/metadata.py` | schema v3 元数据构造、校验、CSV 文件头和 manifest 读写 | 被其他脚本导入，不单独运行 |
| `config.json` | 数据角色、标签枚举、工况到类别映射和数据路径的可读配置 | 与 `metadata.py` 的枚举保持一致 |
| `test_metadata.py` / `test_harmonics.py` / `test_kb_index.py` | 元数据、谐波分析和知识库索引的自检 | 不依赖 pytest；成功时退出码为 0 |

`peak_check.py.gbk.bak` 是历史编码备份，不参与日常运行。

## 1. 接收数据：`recv.py`

固件以 460800 baud 输出二进制帧。默认端口为 `COM13`、默认采集 20 帧；每帧 1024 个 `int16` 原始计数，采样率为 1 kHz。先关闭串口助手等可能占用端口的程序。

例如，采集一段调试数据：

```powershell
$Port = 'COM13'
& $Python .\03_Python工具\recv.py `
  --port $Port `
  --data-role debug `
  --device-id fanA `
  --session-id fanA_debug_20260925 `
  --run-index 1 `
  --observed-condition unknown `
  --label-basis unknown `
  --label-confidence unknown `
  --voltage-set-v 9 `
  --frames 5 `
  --notes '检查串口、X轴与固定方式'
```

采集一段正式正常基线：

```powershell
& $Python .\03_Python工具\recv.py `
  --port $Port `
  --data-role formal `
  --device-id fanA `
  --session-id fanA_baseline_9V `
  --run-index 1 `
  --observed-condition baseline `
  --label-basis controlled_injection `
  --label-confidence confirmed `
  --fault-level 0 `
  --tape-count 0 `
  --voltage-set-v 9 `
  --frames 20 `
  --notes '正常基线，无胶带'
```

类别由客观工况自动推导，通常不要传入 `--target-label`：

| `observed-condition` | 自动 `target-label` |
| --- | --- |
| `baseline` | `normal` |
| `added_mass` | `unbalance` |
| `mount_looseness` | `looseness` |
| `unknown` | `unassigned` |

正式数据还须满足以下规则，否则程序会拒绝保存：

- 不能使用 `observed-condition unknown`；应明确填写 `--label-basis` 和 `--label-confidence`。
- `added_mass` 需要 `--fault-level 1`（或更高）及 `--tape-count 1`（或更多）。
- `mount_looseness` 需要故障等级、`--fault-method`、`--loose-fastener-id`，以及正数的 `--loosen-turns` 或 `--mount-gap-mm`。
- 真实设备须填写 `--voltage-set-v`。

完整的贴胶带和安装固定处机械松动命令、硬件安全要求及采集后的质检要求，请使用 [采集操作手册](../04_数据集/采集操作手册.md)。

运行 `--help` 可查看所有参数：

```powershell
& $Python .\03_Python工具\recv.py --help
```

## 2. 检查与诊断 CSV

采集完成后，优先用 `recv.py` 打印的实际路径检查，而不是依赖“最新文件”。

```powershell
$Csv = '.\04_数据集\debug_raw\替换为实际文件名.csv'
& $Python .\03_Python工具\check_raw.py $Csv
& $Python .\03_Python工具\plot_check.py $Csv
& $Python .\03_Python工具\peak_check.py $Csv
& $Python .\03_Python工具\harmonics.py $Csv
```

省略 CSV 参数时，`check_raw.py`、`plot_check.py`、`peak_check.py` 和 `harmonics.py` 会在 `formal/`、`debug_raw/`、`raw/` 中选择修改时间最新的 CSV。这个方便用于调试，但不能替代对实际采集文件的确认。

`plot_check.py` 会弹出图窗，并在 `05_演示与输出/` 保存 `*_spectrum.png`。`harmonics.py --plot` 同样会显示并保存标注 `1×/2×/...` 的 `*_harmonics.png`。

谐波分析默认使用 10–400 Hz 的频段、最多 10 阶倍频，并可借助额定转速和供电电压的先验减小“强 2× 被误判为 1×”的风险：

```powershell
# 按指定 9 V 工况分析，并输出带谐波标记的图
& $Python .\03_Python工具\harmonics.py $Csv --supply 9 --plot

# 输入已计算的两列频谱 CSV（频率 Hz、幅值）
& $Python .\03_Python工具\harmonics.py .\spectrum.csv --spectrum

# 关闭供电频段先验
& $Python .\03_Python工具\harmonics.py $Csv --supply none
```

谐波结果是辅助验证，不能单独证明机械 1×；存在只有偶次谐波或峰本底比低时，报告会提示不确定性，应结合独立测速或变电压谱线跟踪确认。

## 3. 生成数据集划分

完成正式文件质检后，在 `manifest.csv` 中把可信记录的 `quality_status` 改为 `pass`，再生成划分：

```powershell
& $Python .\03_Python工具\make_dataset.py --test-device fanB
```

脚本只选择 schema v3、`data_role=formal`、`quality_status=pass`、类别已分配的记录；默认排除 `label_confidence=suspect`。它按 `device_id` 留出一台设备作为测试集，从而避免把同一设备的数据同时放入训练集和测试集。没有指定 `--test-device` 时，至少有两台设备才会自动选择排序最后的设备；设备不足两台时，全部标为训练集。

可用参数：

```powershell
& $Python .\03_Python工具\make_dataset.py --help
& $Python .\03_Python工具\make_dataset.py --include-suspect
& $Python .\03_Python工具\make_dataset.py --output-dir .\04_数据集\processed\experiment_01
```

## 4. 自检与知识库校验

修改 Python 工具或标签契约后，运行对应自检：

```powershell
& $Python .\03_Python工具\test_metadata.py
& $Python .\03_Python工具\test_harmonics.py
& $Python .\03_Python工具\test_kb_index.py
```

改动知识库受管文档、模块登记表或正式数据清单后，必须重新生成并检查知识库索引：

```powershell
& $Python -B .\03_Python工具\kb_index.py build
& $Python -B .\03_Python工具\kb_index.py check
```

`kb_index.py build` 会覆盖两个生成文件；不要手工编辑 `知识库/索引/文档与模块索引.md` 或 `知识库/_generated/检查报告.md`。

## 数据格式与边界

`recv.py` 写出的 CSV 首行是 `# meta_json=...`，其余每行是一个小端 `int16` 加速度原始计数。读取工具通过 `py_common/metadata.py` 读取文件头，并由 `py_common/frames.py` 根据 `afs_code` 完成唯一的原始计数到 `g` 的换算。

串口帧协议也集中在 `frames.py`：帧头为 `0x5A 0x5A`，支持加速度样本帧和板端文本日志帧。若固件侧修改帧结构、采样率、每帧点数、量程或测量轴，应同步修改并验证该模块及相关工具，不能仅改文件名或 CSV 元数据。
