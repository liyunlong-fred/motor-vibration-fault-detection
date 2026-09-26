---
kb_id: FORMAL-DATA-DIRECTORY
kind: reference
domain: data
lifecycle: current
authority: canonical
last_verified: 2026-09-25
source_paths:
  - 03_Python工具/config.json
  - 03_Python工具/py_common/metadata.py
  - 04_数据集/manifest.csv
---

# 正式原始数据（formal）

这里仅存放可审计的正式原始采集 CSV。每份数据都应由 `03_Python工具/recv.py --data-role formal` 写入：文件首行包含 `# meta_json=...`，并在上级 `manifest.csv` 追加同一记录的索引行。

当前目录尚没有正式 CSV；`.gitkeep` 用于保留空目录。不要将调试、合成、未知工况或历史 `raw/` 文件复制到这里，也不要手工改写 CSV 的元数据头或文件名。

采集完成后先执行数据检查，再只在 `manifest.csv` 中更新该记录的 `quality_status` 与 `quality_reason`：

- `pending`：待判断，不能训练；
- `pass`：样本、标签和现场记录均可信，可被 `make_dataset.py` 选入；
- `reject`：丢帧、位移、串口异常或标签不确定，必须说明原因。

标签字段、质检标准和采集命令见上级 [数据集说明](../README.md) 与 [采集操作手册](../采集操作手册.md)。
