"""构建并校验项目 Obsidian/Codex 知识库索引。

只使用 Python 标准库；只扫描受管 Markdown 和两个显式登记表，不遍历
HAL/CMSIS 或原始数据内容。生成文件不可手工编辑。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "知识库"
INDEX_PATH = KB_DIR / "索引" / "文档与模块索引.md"
REPORT_PATH = KB_DIR / "_generated" / "检查报告.md"
MODULE_REGISTRY = KB_DIR / "索引" / "关键模块登记.json"
ATTACHMENT_REGISTRY = KB_DIR / "索引" / "附件登记.json"
MANIFEST_PATH = ROOT / "04_数据集" / "manifest.csv"
FORMAL_DIR = ROOT / "04_数据集" / "formal"

REQUIRED_PROPERTIES = (
    "kb_id",
    "kind",
    "domain",
    "lifecycle",
    "authority",
    "last_verified",
)
ALLOWED = {
    "kind": {
        "overview",
        "design",
        "decision",
        "procedure",
        "experiment",
        "troubleshooting",
        "snapshot",
        "reference",
    },
    "domain": {"project", "hardware", "firmware", "dsp", "data", "ml", "tooling"},
    "lifecycle": {"current", "draft", "snapshot", "superseded", "archived"},
    "authority": {"canonical", "supporting", "reference"},
}

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write(content.rstrip() + "\n")


def normalise_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def managed_markdown_paths() -> list[Path]:
    paths: set[Path] = set()

    root_readme = ROOT / "README.md"
    if root_readme.is_file():
        paths.add(root_readme)

    docs_dir = ROOT / "01_文档"
    if docs_dir.is_dir():
        for path in docs_dir.rglob("*.md"):
            if "GY521mpu-6050资料" not in path.parts:
                paths.add(path)

    dataset_dir = ROOT / "04_数据集"
    if dataset_dir.is_dir():
        paths.update(dataset_dir.rglob("*.md"))

    output_readme = ROOT / "05_演示与输出" / "README.md"
    if output_readme.is_file():
        paths.add(output_readme)

    notes_dir = ROOT / "06_笔记与踩坑"
    if notes_dir.is_dir():
        for path in notes_dir.rglob("*.md"):
            if ".obsidian" not in path.parts:
                paths.add(path)

    if KB_DIR.is_dir():
        for path in KB_DIR.rglob("*.md"):
            if "模板" in path.parts or "_generated" in path.parts:
                continue
            if path == INDEX_PATH:
                continue
            paths.add(path)

    return sorted(paths, key=lambda item: rel(item).casefold())


def parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}

    result: dict[str, object] = {}
    current_list: str | None = None
    for raw in lines[1:end]:
        if raw.startswith("  - ") and current_list:
            value = parse_scalar(raw[4:])
            existing = result.setdefault(current_list, [])
            if isinstance(existing, list):
                existing.append(value)
            continue
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value:
            result[key] = parse_scalar(value)
            current_list = None
        else:
            result[key] = []
            current_list = key
    return result


def title_of(text: str, path: Path) -> str:
    match = TITLE_RE.search(text)
    return match.group(1).strip() if match else path.stem


def load_registry(path: Path, label: str, issues: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        issues.append(f"缺少{label}：{rel(path)}")
        return []
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        issues.append(f"{label}无法解析：{rel(path)}（{exc}）")
        return []
    if not isinstance(data, list):
        issues.append(f"{label}顶层必须是数组：{rel(path)}")
        return []

    rows: list[dict[str, str]] = []
    required = {"id", "name", "domain", "path", "role"}
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            issues.append(f"{label}第 {index} 项不是对象")
            continue
        missing = sorted(required - set(item))
        if missing:
            issues.append(f"{label}第 {index} 项缺少：{', '.join(missing)}")
            continue
        row = {str(key): str(value) for key, value in item.items()}
        rows.append(row)
        target = ROOT / row["path"]
        if not target.is_file():
            issues.append(f"{label}路径不存在：{row['path']}")
    return rows


def markdown_relative_link(from_dir: Path, target: Path, label: str) -> str:
    relative = Path(os.path.relpath(target, from_dir)).as_posix()
    return f"[{label}](<{relative}>)"


def resolve_markdown_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith(("#", "http://", "https://", "mailto:", "obsidian://")):
        return None
    if " " in target and not target.startswith(("./", "../")):
        target = target.split(" ", 1)[0]
    target = unquote(target.split("#", 1)[0].split("?", 1)[0]).replace("\\", "/")
    if not target:
        return None
    path = (source.parent / target).resolve()
    if path.suffix:
        return path
    md_path = path.with_suffix(".md")
    return md_path if md_path.exists() else path


def collect_link_targets(
    docs: list[Path], modules: list[dict[str, str]], attachments: list[dict[str, str]]
) -> list[Path]:
    targets = set(docs)
    targets.update(ROOT / row["path"] for row in modules)
    targets.update(ROOT / row["path"] for row in attachments)
    if KB_DIR.is_dir():
        targets.update(KB_DIR.rglob("*.base"))
    return sorted(targets)


def check_links(
    docs: list[Path], modules: list[dict[str, str]], attachments: list[dict[str, str]]
) -> list[str]:
    issues: list[str] = []
    targets = collect_link_targets(docs, modules, attachments)
    by_name: dict[str, list[Path]] = defaultdict(list)
    for target in targets:
        by_name[target.name.casefold()].append(target)
        by_name[target.stem.casefold()].append(target)

    for path in docs:
        text = read_text(path)
        for raw_target in MARKDOWN_LINK_RE.findall(text):
            resolved = resolve_markdown_target(path, raw_target)
            if resolved is not None and not resolved.exists():
                issues.append(f"失效 Markdown 链接：{rel(path)} -> {raw_target}")

        for raw_target in WIKILINK_RE.findall(text):
            target = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
            if not target:
                continue
            target = target.replace("\\", "/")
            if "/" in target:
                candidate = ROOT / target
                if not candidate.suffix:
                    candidate = candidate.with_suffix(".md")
                if not candidate.exists():
                    issues.append(f"失效 Wikilink：{rel(path)} -> {raw_target}")
                continue
            matches = by_name.get(target.casefold(), [])
            if not matches and not Path(target).suffix:
                matches = by_name.get((target + ".md").casefold(), [])
            if not matches:
                issues.append(f"失效 Wikilink：{rel(path)} -> {raw_target}")
            elif len({item.resolve() for item in matches}) > 1:
                issues.append(f"歧义 Wikilink：{rel(path)} -> {raw_target}")
    return issues


def check_manifest() -> tuple[list[str], int]:
    issues: list[str] = []
    actual = {
        path.relative_to(ROOT / "04_数据集").as_posix()
        for path in FORMAL_DIR.glob("*.csv")
        if path.is_file()
    }
    listed: set[str] = set()

    if not MANIFEST_PATH.is_file():
        return ["缺少数据集 manifest：04_数据集/manifest.csv"], len(actual)

    try:
        with MANIFEST_PATH.open(newline="", encoding="utf-8-sig") as fp:
            rows = list(csv.DictReader(fp))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [f"manifest 无法读取：{exc}"], len(actual)

    for row_number, row in enumerate(rows, start=2):
        value = (row.get("file") or "").strip().replace("\\", "/")
        if not value:
            issues.append(f"manifest 第 {row_number} 行缺少 file")
            continue
        if value.startswith("04_数据集/"):
            value = value[len("04_数据集/") :]
        listed.add(value)
        if not (ROOT / "04_数据集" / value).is_file():
            issues.append(f"manifest 登记文件不存在：{value}")

    for value in sorted(actual - listed):
        issues.append(f"formal 文件未登记 manifest：{value}")
    return issues, len(actual)


def nested_obsidian_dirs() -> list[Path]:
    found: list[Path] = []
    for top in ROOT.iterdir():
        if not top.is_dir() or top.name in {".git", ".conda", ".obsidian"}:
            continue
        for path in top.rglob(".obsidian"):
            if path.is_dir():
                found.append(path)
    return sorted(found)


def validate() -> tuple[list[str], list[dict[str, object]], list[dict[str, str]], list[dict[str, str]], int]:
    issues: list[str] = []
    docs = managed_markdown_paths()
    records: list[dict[str, object]] = []
    ids: dict[str, list[str]] = defaultdict(list)
    digests: dict[str, list[str]] = defaultdict(list)

    for path in docs:
        try:
            text = read_text(path)
        except UnicodeDecodeError as exc:
            issues.append(f"Markdown 不是 UTF-8：{rel(path)}（{exc}）")
            continue
        properties = parse_frontmatter(text)
        missing = [key for key in REQUIRED_PROPERTIES if not properties.get(key)]
        if missing:
            issues.append(f"缺少知识库属性：{rel(path)}（{', '.join(missing)}）")
        for key, allowed in ALLOWED.items():
            value = properties.get(key)
            if value and value not in allowed:
                issues.append(f"属性值无效：{rel(path)} {key}={value}")
        if properties.get("lifecycle") == "snapshot" and not properties.get("as_of"):
            issues.append(f"快照缺少 as_of：{rel(path)}")
        if properties.get("lifecycle") == "snapshot" and properties.get("authority") == "canonical":
            issues.append(f"历史快照不能标为 canonical：{rel(path)}")

        kb_id = str(properties.get("kb_id") or "")
        if kb_id:
            ids[kb_id].append(rel(path))
        digest = hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()
        digests[digest].append(rel(path))

        source_paths = properties.get("source_paths", [])
        if isinstance(source_paths, str):
            source_paths = [source_paths]
        if isinstance(source_paths, list):
            for value in source_paths:
                if value and not (ROOT / str(value)).exists():
                    issues.append(f"source_paths 不存在：{rel(path)} -> {value}")

        records.append(
            {
                "path": path,
                "title": title_of(text, path),
                "properties": properties,
            }
        )

    for kb_id, paths in sorted(ids.items()):
        if len(paths) > 1:
            issues.append(f"重复 kb_id={kb_id}：{', '.join(paths)}")
    for paths in sorted(digests.values()):
        if len(paths) > 1:
            issues.append(f"规范化后内容重复：{', '.join(paths)}")

    modules = load_registry(MODULE_REGISTRY, "关键模块登记", issues)
    attachments = load_registry(ATTACHMENT_REGISTRY, "附件登记", issues)

    registry_ids: dict[str, list[str]] = defaultdict(list)
    for row in modules:
        registry_ids[row["id"]].append("关键模块登记")
    for row in attachments:
        registry_ids[row["id"]].append("附件登记")
    for kb_id in ids:
        registry_ids[kb_id].append("Markdown")
    for item_id, sources in sorted(registry_ids.items()):
        if len(sources) > 1:
            issues.append(f"跨登记表 ID 重复={item_id}：{', '.join(sources)}")

    issues.extend(check_links(docs, modules, attachments))
    manifest_issues, formal_count = check_manifest()
    issues.extend(manifest_issues)

    for path in nested_obsidian_dirs():
        issues.append(f"发现嵌套 Vault：{rel(path)}")

    return sorted(set(issues)), records, modules, attachments, formal_count


def render_index(
    records: list[dict[str, object]], modules: list[dict[str, str]], attachments: list[dict[str, str]]
) -> str:
    lines = [
        "# 文档与模块索引",
        "",
        "> 由 `python -B 03_Python工具/kb_index.py build` 生成，请勿手工编辑。",
        "",
        "## 受管文档",
        "",
        "| 文档 | 类型 | 领域 | 生命周期 | 权威级别 | 最后核实 |",
        "|---|---|---|---|---|---|",
    ]
    for record in sorted(records, key=lambda item: rel(item["path"]).casefold()):
        path = record["path"]
        properties = record["properties"]
        link = markdown_relative_link(INDEX_PATH.parent, path, str(record["title"]))
        lines.append(
            "| {link} | {kind} | {domain} | {lifecycle} | {authority} | {verified} |".format(
                link=link,
                kind=properties.get("kind", ""),
                domain=properties.get("domain", ""),
                lifecycle=properties.get("lifecycle", ""),
                authority=properties.get("authority", ""),
                verified=properties.get("last_verified", ""),
            )
        )

    lines.extend(
        [
            "",
            "## 关键模块",
            "",
            "| 模块 | 领域 | 责任 |",
            "|---|---|---|",
        ]
    )
    for row in sorted(modules, key=lambda item: (item["domain"], item["name"])):
        link = markdown_relative_link(INDEX_PATH.parent, ROOT / row["path"], row["name"])
        lines.append(f"| {link} | {row['domain']} | {row['role']} |")

    lines.extend(
        [
            "",
            "## 重要附件",
            "",
            "| 附件 | 领域 | 用途 | 分发策略 |",
            "|---|---|---|---|",
        ]
    )
    for row in sorted(attachments, key=lambda item: (item["domain"], item["name"])):
        link = markdown_relative_link(INDEX_PATH.parent, ROOT / row["path"], row["name"])
        lines.append(
            f"| {link} | {row['domain']} | {row['role']} | {row.get('distribution', '')} |"
        )
    return "\n".join(lines)


def render_report(
    issues: list[str], records: list[dict[str, object]], modules: list[dict[str, str]],
    attachments: list[dict[str, str]], formal_count: int
) -> str:
    lines = [
        "# 知识库检查报告",
        "",
        "> 由 `python -B 03_Python工具/kb_index.py build` 生成，请勿手工编辑。",
        "",
        f"- 状态：{'通过' if not issues else '发现问题'}",
        f"- 受管文档：{len(records)}",
        f"- 关键模块：{len(modules)}",
        f"- 重要附件：{len(attachments)}",
        f"- formal CSV：{formal_count}",
        f"- 问题数：{len(issues)}",
        "",
        "## 检查结果",
        "",
    ]
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- 未发现结构、索引、链接或 manifest 一致性问题。")
    return "\n".join(lines)


def expected_outputs() -> tuple[list[str], str, str]:
    issues, records, modules, attachments, formal_count = validate()
    return (
        issues,
        render_index(records, modules, attachments),
        render_report(issues, records, modules, attachments, formal_count),
    )


def command_build() -> int:
    issues, index_content, report_content = expected_outputs()
    write_text(INDEX_PATH, index_content)
    write_text(REPORT_PATH, report_content)
    print(f"已生成 {rel(INDEX_PATH)}")
    print(f"已生成 {rel(REPORT_PATH)}")
    if issues:
        for issue in issues:
            print(f"[ERROR] {issue}")
        return 1
    print("[PASS] 知识库构建与结构检查通过")
    return 0


def command_check() -> int:
    issues, index_content, report_content = expected_outputs()
    if not INDEX_PATH.is_file():
        issues.append(f"缺少生成索引：{rel(INDEX_PATH)}")
    elif normalise_text(read_text(INDEX_PATH)) != normalise_text(index_content):
        issues.append(f"生成索引已过期：{rel(INDEX_PATH)}")
    if not REPORT_PATH.is_file():
        issues.append(f"缺少检查报告：{rel(REPORT_PATH)}")
    elif normalise_text(read_text(REPORT_PATH)) != normalise_text(report_content):
        issues.append(f"检查报告已过期：{rel(REPORT_PATH)}")

    if issues:
        for issue in sorted(set(issues)):
            print(f"[FAIL] {issue}")
        return 1
    print("[PASS] 知识库索引、链接、登记表与 manifest 一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建或校验 STM32 项目知识库")
    parser.add_argument("command", choices=("build", "check"))
    args = parser.parse_args(argv)
    return command_build() if args.command == "build" else command_check()


if __name__ == "__main__":
    raise SystemExit(main())
