---
kb_id: PROJECT-README
kind: overview
domain: project
lifecycle: current
authority: supporting
last_verified: 2026-09-24
---

# 电机振动故障检测

项目使用 STM32 + MPU6050 采集风扇外壳振动，在本地完成频谱/谐波分析并为后续三分类模型准备数据。

当前三分类目标为正常 / 不平衡 / 安装固定处机械松动。X 为振动测量轴，Y 为重力轴；正式数据写入 `04_数据集/formal/` 并登记 `manifest.csv`，调试数据写入本地 `04_数据集/debug_raw/`。标签使用结构化 schema v3：客观工况、模型标签、证据依据和可信度分开保存，并量化机械松动的紧固点与回退圈数或间隙。轴承异常不在本项目范围内。

数据采集操作请先阅读：[`04_数据集/采集操作手册.md`](04_数据集/采集操作手册.md)。

常用入口：

```powershell
python -B 03_Python工具\test_metadata.py
python -B 03_Python工具\recv.py --help
python -B 03_Python工具\make_dataset.py
```

项目目标与方案在 [01_文档/项目规划/README.md](01_文档/项目规划/README.md) 维护；当前进度不要从历史交接快照推断。

知识库入口：[`知识库/00_导航.md`](知识库/00_导航.md)。当前进度以
[`知识库/10_当前状态.md`](知识库/10_当前状态.md) 为准；`HANDOFF.md` 是历史快照，不代表实时状态。

知识库索引命令：

```powershell
python -B 03_Python工具\kb_index.py build
python -B 03_Python工具\kb_index.py check
```
