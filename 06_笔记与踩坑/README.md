---
kb_id: NOTES-GUIDE
kind: overview
domain: project
lifecycle: current
authority: canonical
last_verified: 2026-09-24
---

# 笔记与踩坑

串口 boardlog 由 `recv.py` 写入 `raw_logs/`，该目录默认仅本地保存。排查结论、固定操作清单和少量有里程碑价值的截图/记录可以提交；中间调试文件不要入库。

开发问题按独立记录维护，入口见[开发问题与解决记录](开发问题/README.md)。

记录数据问题时至少写明：记录号、设备、会话、电压、测量轴 X、重力轴 Y、丢帧数和处理结论。
