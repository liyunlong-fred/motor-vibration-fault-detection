# Project knowledge routing

- Treat source code, configuration, test output, and dataset manifests as evidence for current behavior.
- Read `知识库/10_当前状态.md` when a task depends on current progress, blockers, or next steps.
- Read `知识库/20_系统地图.md` for architecture, sampling, FFT, serial-link, or module-boundary changes.
- For dataset or label changes, read `04_数据集/README.md`, `03_Python工具/config.json`, and `04_数据集/manifest.csv`.
- Read `01_文档/HANDOFF.md` only for the 2026-09-22 historical snapshot; do not treat its counts or Git state as current.
- Read the relevant sections of `01_文档/项目规划/` for goals and design rationale, not as proof of implementation.
- Use `知识库/30_决策索引.md` for established decisions and `知识库/40_问题与实验索引.md` for prior investigations.
- Small spelling, comment, or local refactors do not require loading the knowledge base.
- Update knowledge notes only when public behavior, wiring, data contracts, verified project state, or reproducible procedures change.
- Never rewrite historical snapshots or experiment evidence to make them look current; append a dated correction or update the current-state page instead.
- Do not edit generated index files by hand. After changing managed knowledge files or registries, run:
  `python -B 03_Python工具/kb_index.py build`
  and `python -B 03_Python工具/kb_index.py check`.
- A planned item becomes completed only when a source file, manifest entry, test result, log, or other reproducible evidence supports it.
