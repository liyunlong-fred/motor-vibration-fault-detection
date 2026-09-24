"""从正式数据清单生成可复现的 train/test 划分清单。

不随机拆同一段窗口；优先按 device_id 留出一台风扇，避免设备泄漏。
实际特征提取仍可在此清单基础上单独扩展。
"""
import argparse
import csv
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import metadata

PROJ = os.path.dirname(_HERE)
MANIFEST = os.path.join(PROJ, "04_数据集", "manifest.csv")
DEFAULT_OUT = os.path.join(PROJ, "04_数据集", "processed")


def build_parser():
    p = argparse.ArgumentParser(description="按设备/会话生成数据集划分清单")
    p.add_argument("--manifest", default=MANIFEST)
    p.add_argument("--output-dir", default=DEFAULT_OUT)
    p.add_argument("--test-device", help="指定留出的测试设备，如 fanB")
    p.add_argument("--include-suspect", action="store_true",
                   help="默认排除 label_confidence=suspect，开启后纳入")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not os.path.isfile(args.manifest):
        print("找不到清单: %s" % args.manifest)
        return 1
    with open(args.manifest, newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        manifest_fields = list(reader.fieldnames or [])
        rows = list(reader)
    selected = []
    excluded = {}
    for row in rows:
        if row.get("data_role") != "formal" or row.get("quality_status") != "pass":
            excluded["not_formal_or_not_pass"] = excluded.get("not_formal_or_not_pass", 0) + 1
            continue
        if str(row.get("schema_version", "")).strip() != str(metadata.SCHEMA_VERSION):
            excluded["schema_mismatch"] = excluded.get("schema_mismatch", 0) + 1
            continue
        if row.get("target_label") in ("", "unassigned", None):
            excluded["unassigned"] = excluded.get("unassigned", 0) + 1
            continue
        if row.get("label_confidence") == "suspect" and not args.include_suspect:
            excluded["suspect"] = excluded.get("suspect", 0) + 1
            continue
        selected.append(dict(row))
    devices = sorted({r.get("device_id", "unknown") for r in selected})
    if args.test_device:
        if args.test_device not in devices:
            print("--test-device 不在可用设备中: %s" % args.test_device)
            return 2
        test_device = args.test_device
    else:
        test_device = devices[-1] if len(devices) >= 2 else None
    if test_device is None:
        print("可用设备少于 2 台，当前全部标为 train；补齐第二台设备后再划分测试集")
    for row in selected:
        row["dataset_split"] = "test" if test_device and row.get("device_id") == test_device else "train"

    os.makedirs(args.output_dir, exist_ok=True)
    out_csv = os.path.join(args.output_dir, "split_manifest.csv")
    fields = manifest_fields or (list(rows[0].keys()) if rows else [])
    if "dataset_split" not in fields:
        fields.append("dataset_split")
    with open(out_csv, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    summary = {
        "source_manifest": os.path.relpath(args.manifest, PROJ).replace("\\", "/"),
        "test_device": test_device,
        "devices": devices,
        "rows_total": len(rows),
        "rows_selected": len(selected),
        "train": sum(r["dataset_split"] == "train" for r in selected),
        "test": sum(r["dataset_split"] == "test" for r in selected),
        "excluded": excluded,
    }
    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    print("已生成: %s" % out_csv)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
