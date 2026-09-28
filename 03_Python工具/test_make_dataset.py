"""训练清单的文件完整性门禁自检；只在临时目录写入文件。"""
import csv
import hashlib
import json
import os
import tempfile

import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import metadata
import make_dataset


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(name, condition):
    print("[PASS]" if condition else "[FAIL]", name)
    return condition


def main():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        formal_dir = os.path.join(tmp, "formal")
        os.makedirs(formal_dir)
        sample = os.path.join(formal_dir, "sample.csv")
        with open(sample, "w", encoding="utf-8") as fp:
            fp.write("# meta_json={}\n1\n2\n")
        manifest = os.path.join(tmp, "manifest.csv")
        row = {field: "" for field in metadata.MANIFEST_FIELDS}
        row.update({
            "file": "formal/sample.csv", "schema_version": str(metadata.SCHEMA_VERSION),
            "data_role": "formal", "device_id": "fanA", "target_label": "normal",
            "label_confidence": "confirmed", "quality_status": "pass",
            "file_sha256": _sha256(sample),
        })
        with open(manifest, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=metadata.MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerow(row)

        output_ok = os.path.join(tmp, "out_ok")
        ok &= check("哈希匹配的正式文件进入训练清单",
                    make_dataset.main(["--manifest", manifest, "--output-dir", output_ok]) == 0)
        with open(os.path.join(output_ok, "summary.json"), encoding="utf-8") as fp:
            ok &= check("匹配文件被选中", json.load(fp)["rows_selected"] == 1)

        with open(sample, "a", encoding="utf-8") as fp:
            fp.write("3\n")
        output_bad = os.path.join(tmp, "out_bad")
        ok &= check("哈希不匹配的文件不阻塞清单生成",
                    make_dataset.main(["--manifest", manifest, "--output-dir", output_bad]) == 0)
        with open(os.path.join(output_bad, "summary.json"), encoding="utf-8") as fp:
            summary = json.load(fp)
            ok &= check("篡改文件被排除", summary["rows_selected"] == 0 and
                        summary["excluded"].get("file_sha256_mismatch") == 1)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
