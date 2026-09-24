"""检查最新或指定原始 CSV 的标签和计数统计，不修改数据。"""
import argparse
import glob
import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(_HERE)
DATA_DIRS = [os.path.join(PROJ, "04_数据集", x) for x in ("formal", "debug_raw", "raw")]
import sys
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import metadata


def latest():
    cands = []
    for directory in DATA_DIRS:
        cands.extend(glob.glob(os.path.join(directory, "*.csv")))
    return max(cands, key=os.path.getmtime) if cands else None


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("csv", nargs="?", help="不填则选三个数据目录中最新的 CSV")
    args = p.parse_args(argv)
    path = args.csv or latest()
    if not path:
        print("找不到 CSV")
        return 1
    meta = metadata.read_meta(path)
    raw = np.atleast_1d(np.loadtxt(path, comments="#", dtype=np.int16))
    print("文件:", path)
    print("记录=%s 设备=%s 工况=%s 标签=%s 质量=%s" %
          (meta.get("record_id", "legacy"), meta.get("device_id", "legacy_unknown"),
           meta.get("observed_condition", "unknown"), meta.get("target_label", "unassigned"),
           meta.get("quality_status", "unknown")))
    print("轴=%s/%s 采样率=%sHz 每帧=%s 供电=%sV" %
          (meta.get("measurement_axis", meta.get("axis", "?")), meta.get("gravity_axis", "?"),
           meta.get("fs_hz", meta.get("fs", "?")), meta.get("frame_n", meta.get("per_frame", "?")),
           meta.get("voltage_measured_v", meta.get("voltage_set_v", "?"))))
    print("样本数 %d  最小 %d  最大 %d  均值 %.1f" %
          (raw.size, raw.min(), raw.max(), raw.mean()))
    print("负样本 %d 个 (%.1f%%)   等于0: %d 个" %
          ((raw < 0).sum(), 100.0 * (raw < 0).mean(), (raw == 0).sum()))
    print("前 40 个原始计数:", raw[:40].tolist())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
