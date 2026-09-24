"""kb_index.py 的标准库自检，不修改项目文件。"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("kb_index", HERE / "kb_index.py")
kb_index = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(kb_index)


def managed_note(kb_id: str, extra: str = "") -> str:
    return f"""---
kb_id: {kb_id}
kind: overview
domain: project
lifecycle: current
authority: supporting
last_verified: 2026-09-24
---

# Test

{extra}
"""


def configure_root(root: Path) -> None:
    kb_index.ROOT = root
    kb_index.KB_DIR = root / "知识库"
    kb_index.INDEX_PATH = kb_index.KB_DIR / "索引" / "文档与模块索引.md"
    kb_index.REPORT_PATH = kb_index.KB_DIR / "_generated" / "检查报告.md"
    kb_index.MODULE_REGISTRY = kb_index.KB_DIR / "索引" / "关键模块登记.json"
    kb_index.ATTACHMENT_REGISTRY = kb_index.KB_DIR / "索引" / "附件登记.json"
    kb_index.MANIFEST_PATH = root / "04_数据集" / "manifest.csv"
    kb_index.FORMAL_DIR = root / "04_数据集" / "formal"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    properties = kb_index.parse_frontmatter(
        managed_note("TEST", "") .replace("last_verified: 2026-09-24", "source_paths:\n  - a.txt")
    )
    checks.append(("frontmatter 列表解析", properties.get("source_paths") == ["a.txt"]))

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        configure_root(root)
        (root / "01_文档").mkdir(parents=True)
        (root / "04_数据集" / "formal").mkdir(parents=True)
        (root / "06_笔记与踩坑" / "旧Vault" / ".obsidian").mkdir(parents=True)
        (root / "知识库" / "索引").mkdir(parents=True)

        (root / "README.md").write_text(
            managed_note("DUPLICATE", "[broken](missing.md)"), encoding="utf-8"
        )
        (root / "01_文档" / "duplicate.md").write_text(
            managed_note("DUPLICATE", ""), encoding="utf-8"
        )
        (root / "04_数据集" / "formal" / "sample.csv").write_text("1\n", encoding="utf-8")
        (root / "04_数据集" / "manifest.csv").write_text("file\n", encoding="utf-8")
        (root / "知识库" / "索引" / "关键模块登记.json").write_text("[]\n", encoding="utf-8")
        (root / "知识库" / "索引" / "附件登记.json").write_text("[]\n", encoding="utf-8")

        issues, *_ = kb_index.validate()
        checks.extend(
            [
                ("重复 kb_id", any("重复 kb_id" in issue for issue in issues)),
                ("断链", any("失效 Markdown 链接" in issue for issue in issues)),
                ("manifest 漏登记", any("未登记 manifest" in issue for issue in issues)),
                ("嵌套 Vault", any("嵌套 Vault" in issue for issue in issues)),
            ]
        )

    ok = True
    for name, passed in checks:
        print("[PASS]" if passed else "[FAIL]", name)
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
