---
kb_id: OUTPUT-GUIDE
kind: reference
domain: tooling
lifecycle: current
authority: supporting
last_verified: 2026-09-24
---

# 演示与输出

这里保存可复现的里程碑图、频谱图、报告和板端串口日志。临时调试输出请放在 `debug/`（已忽略），不要把大量中间 PNG 混入仓库。

`boardlog/` 专门保存 `recv.py` 接收的板端文本日志，用于板上 FFT 与 PC 端对拍追溯。该目录默认仅本地保存；需要作为里程碑证据提交时，应从中挑选对应日志并在实验记录中注明文件名。

`plot_check.py` 和 `harmonics.py` 默认会从 `formal/`、`debug_raw/`、旧 `raw/` 中选择最新 CSV；提交结果时同时保留对应的记录号和 `manifest.csv` 行。
