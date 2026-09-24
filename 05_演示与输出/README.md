---
kb_id: OUTPUT-GUIDE
kind: reference
domain: tooling
lifecycle: current
authority: supporting
last_verified: 2026-09-24
---

# 演示与输出

这里保存可复现的里程碑图、频谱图和报告。临时调试输出请放在 `debug/`（已忽略），不要把大量中间 PNG 或日志混入仓库。

`plot_check.py` 和 `harmonics.py` 默认会从 `formal/`、`debug_raw/`、旧 `raw/` 中选择最新 CSV；提交结果时同时保留对应的记录号和 `manifest.csv` 行。
