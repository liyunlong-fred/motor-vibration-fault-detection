---
kb_id: DATASET-CONTRACT
kind: reference
domain: data
lifecycle: current
authority: canonical
last_verified: 2026-09-24
source_paths:
  - 03_Python工具/config.json
  - 03_Python工具/py_common/metadata.py
  - 04_数据集/manifest.csv
---

# 数据集目录与标签契约

操作手册：采集操作手册.md。其中以统一采集窗口为准，说明全部标签、调试/正式/自检/标定模式、现场安全边界和采集后质检步骤。采集矩阵与数据划分的设计依据见[数据集设计与采集计划](数据集设计与采集计划.md)。

正式原始数据放在 `formal/`，每个文件头有一行 `# meta_json=...`，并在根目录 `manifest.csv` 登记。文件头是不可变的采集事实；`manifest.csv` 是质检、数据划分与文件 SHA-256 的唯一权威来源。调试数据放在本地 `debug_raw/`；旧版 `raw/` 只作为历史兼容目录，不再写入新数据。

当前契约版本为 schema v4。它把第三类由轴承异常改为安装固定处机械松动，并补齐夹具、传感器、安装姿态、标定和固件构建溯源；旧 schema v1/v2/v3 文件只保留为历史或调试证据，不重写标签，也不与 v4 正式数据混合训练。

关键字段：

| 字段 | 用途 |
| --- | --- |
| `observed_condition` | 客观工况：`baseline`、`added_mass`、`mount_looseness`、`unknown` |
| `target_label` | 模型标签：`normal`、`unbalance`、`looseness`、`unassigned` |
| `label_basis` / `label_confidence` | 标签依据和可信度；当前正式三类只接受可确认的基线或受控注入 |
| `loose_fastener_id` | 发生松动的安装紧固点编号，例如 `M1` |
| `loosen_turns` / `mount_gap_mm` | 从基准紧固位置回退的圈数或安装点间隙；松动工况至少量化一项 |
| `device_id` / `session_id` | 防止同一设备/会话泄漏到测试集 |
| `measurement_axis` / `reference_gravity_axis` / `reference_gravity_sign` | 固定为 X / Y；后两项描述静态基准安装时重力在 Y 上的符号，不代表运行中的“重力通道” |
| `fixture_id` / `sensor_module_id` / `sensor_mount_id` / `installation_orientation_id` | 正式采集必填，用于区分夹具、模块、测点和安装姿态的系统性差异 |
| `calibration_id` | 应用的标定记录；当前未接入补偿时明确填写 `uncalibrated` |
| `firmware_build_id` | 实际烧录固件的提交号或可追溯构建标识 |
| `fs_config_hz` / `window_samples` / `window_nominal_ms` | 固件配置值与单窗名义长度；不把名义 1 kHz 写成实测采样率 |
| `capture_samples` / `capture_nominal_ms` | 本文件样本数与名义采集时长 |
| `lost_frames` / `sample_id_gaps` / `board_*` | PC 接收完整性及最后收到的板端累计统计；板端统计范围为自上电以来 |
| `quality_status` / `quality_reason` / `dataset_split` / `file_sha256` | 只存在于 `manifest.csv`；`pending` → 检查后改为 `pass` 或 `reject` |

`session_id` 表示一次不改变夹具、模块、测点、安装姿态和供电配置的连续实验区段，不按类别命名。计划内的“基线→故障→恢复基线”可使用同一会话并递增 `run_index`；任何这些条件变化都必须新建会话。

三类默认映射为 `baseline → normal`、`added_mass → unbalance`、`mount_looseness → looseness`。机械松动仅指风扇与实验底座之间的安装固定异常；底板与桌面必须始终刚性固定，不能把整机在桌面滑移或软垫晃动当作松动样本。轴承异常不作为扩展类别保留。

历史文件不要改头或重命名。训练前运行：

```powershell
python -B 03_Python工具\make_dataset.py
```

脚本只选当前 schema v4、`formal + quality_status=pass` 且文件 SHA-256 与 manifest 一致的记录，默认排除 `label_confidence=suspect`，并按设备留出测试集。
