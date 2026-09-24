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

操作手册：采集操作手册.md。其中包含面向新操作者的 PowerShell 命令、调试/正式切换方法和采集后检查步骤。采集矩阵与数据划分的设计依据见[数据集设计与采集计划](数据集设计与采集计划.md)。

正式原始数据放在 `formal/`，每个文件头有一行 `# meta_json=...`，并在根目录 `manifest.csv` 登记。调试数据放在本地 `debug_raw/`；旧版 `raw/` 只作为历史兼容目录，不再写入新数据。

当前契约版本为 schema v3。它把第三类由轴承异常改为安装固定处机械松动；旧 schema v1/v2 文件只保留为历史或调试证据，不重写标签，也不与 v3 正式数据混合训练。

关键字段：

| 字段 | 用途 |
| --- | --- |
| `observed_condition` | 客观工况：`baseline`、`added_mass`、`mount_looseness`、`unknown` |
| `target_label` | 模型标签：`normal`、`unbalance`、`looseness`、`unassigned` |
| `label_basis` / `label_confidence` | 标签依据和可信度；当前正式三类只接受可确认的基线或受控注入 |
| `loose_fastener_id` | 发生松动的安装紧固点编号，例如 `M1` |
| `loosen_turns` / `mount_gap_mm` | 从基准紧固位置回退的圈数或安装点间隙；松动工况至少量化一项 |
| `device_id` / `session_id` | 防止同一设备/会话泄漏到测试集 |
| `measurement_axis` / `gravity_axis` | 固定为 X / Y |
| `quality_status` | `pending` → 检查后改为 `pass` 或 `reject` |

采集表单不包含夹具版本、传感器编号、传感器安装点。安装方式仍要保持稳定；临时变化写入 `notes` 并开始新的 `session_id`。

三类默认映射为 `baseline → normal`、`added_mass → unbalance`、`mount_looseness → looseness`。机械松动仅指风扇与实验底座之间的安装固定异常；底板与桌面必须始终刚性固定，不能把整机在桌面滑移或软垫晃动当作松动样本。轴承异常不作为扩展类别保留。

历史文件不要改头或重命名。训练前运行：

```powershell
python -B 03_Python工具\make_dataset.py
```

脚本只选当前 schema v3、`formal + quality_status=pass` 的记录，默认排除 `label_confidence=suspect`，并按设备留出测试集。
