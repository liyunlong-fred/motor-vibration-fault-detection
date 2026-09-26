---
kb_id: KNOWLEDGE-BASE-GUIDE
kind: overview
domain: project
lifecycle: current
authority: supporting
last_verified: 2026-09-25
source_paths:
  - 知识库/00_导航.md
  - 知识库/10_当前状态.md
  - 知识库/20_系统地图.md
  - 03_Python工具/kb_index.py
---

# 项目知识库

本目录是 Obsidian 与 Codex 共用的项目导航和证据索引，不复制源码、原始数据或第三方资料。快速导航请从 [00_导航](00_导航.md) 开始；当前事实优先看 [当前状态](10_当前状态.md)，模块边界看 [系统地图](20_系统地图.md)。

| 位置 | 用途 |
| --- | --- |
| `00_导航.md`～`40_问题与实验索引.md` | 当前导航、状态、架构、决策和问题/实验索引 |
| `索引/` | 关键模块和附件登记表；`文档与模块索引.md` 由脚本生成 |
| `_generated/` | 结构检查报告；由脚本生成，不手工编辑 |
| `模板/` | 新建决策、实验或排查记录的 frontmatter 模板 |

受管 Markdown 必须有 `kb_id`、`kind`、`domain`、`lifecycle`、`authority` 和 `last_verified`。修改受管文档、登记表或正式数据清单后，在项目根目录运行：

```powershell
python -B 03_Python工具\kb_index.py build
python -B 03_Python工具\kb_index.py check
```

历史快照不能伪装成当前结论；只有源码、配置、测试、日志、manifest 或可复现实验支持的事项才可标为完成。
