"""标签契约自检；只在系统临时目录写文件。"""
import argparse
import json
import os
import tempfile

import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import metadata


def ns(**overrides):
    values = dict(
        observed_condition="baseline", target_label=None, acquired_at="2026-09-23T12:00:00+08:00",
        session_id="s1", record_id="r1", device_id="fanA", run_index=1,
        data_role="formal", source_type="real", label_basis="controlled_injection",
        label_confidence="confirmed", fault_level=0, fault_method="", tape_spec_id="",
        tape_count=0, tape_mass_mg=None, tape_radius_mm=None, tape_angle_deg=None,
        loose_fastener_id="", loosen_turns=None, mount_gap_mm=None,
        fixture_id="rig01", sensor_module_id="mpu01", sensor_mount_id="fan_frame_top",
        installation_orientation_id="x_measure_y_gravity", reference_gravity_sign="+1",
        calibration_id="uncalibrated", firmware_build_id="bb64fdf",
        voltage_set_v=9.0, voltage_measured_v=None, rpm_measured=None,
        notes="",
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def check(name, condition):
    print("[PASS]" if condition else "[FAIL]", name)
    return condition


def main():
    ok = True
    with open(os.path.join(_HERE, "config.json"), encoding="utf-8") as fp:
        config = json.load(fp)
    ok &= check("config 与 metadata 的 schema/枚举一致",
                config["schema_version"] == metadata.SCHEMA_VERSION and
                config["axes"]["measurement_axis"] == metadata.MEASUREMENT_AXIS and
                config["axes"]["reference_gravity_axis"] == metadata.REFERENCE_GRAVITY_AXIS and
                tuple(config["axes"]["reference_gravity_sign_values"]) == ("+1", "-1") and
                tuple(config["observed_conditions"]) == metadata.OBSERVED_CONDITIONS and
                tuple(config["target_labels"]) == metadata.TARGET_LABELS and
                tuple(config["label_bases"]) == metadata.LABEL_BASES and
                all(metadata.derive_target_label(condition) == target
                    for condition, target in config["target_from_condition"].items()))
    m = metadata.build_capture_meta(ns())
    ok &= check("baseline 自动映射 normal", m["target_label"] == "normal")
    ok &= check("schema 已升级到 v4", m["schema_version"] == 4)
    ok &= check("X/Y 参考轴固定", m["measurement_axis"] == "X" and
                m["reference_gravity_axis"] == "Y" and m["reference_gravity_sign"] == "+1")
    ok &= check("正式元数据通过校验", not metadata.validate(m))
    bad = metadata.build_capture_meta(ns(observed_condition="added_mass", fault_level=1,
                                         fault_method="tape_mass", tape_spec_id="tape01",
                                         tape_count=0))
    ok &= check("added_mass 缺少胶带数量会失败", bool(metadata.validate(bad)))
    loose_bad = metadata.build_capture_meta(ns(
        observed_condition="mount_looseness", fault_level=1,
        fault_method="fastener_backoff", loose_fastener_id="M1"))
    ok &= check("mount_looseness 缺少量化值会失败", bool(metadata.validate(loose_bad)))
    loose = metadata.build_capture_meta(ns(
        observed_condition="mount_looseness", fault_level=1,
        fault_method="fastener_backoff", loose_fastener_id="M1", loosen_turns=0.25))
    ok &= check("mount_looseness 自动映射并通过校验",
                loose["target_label"] == "looseness" and not metadata.validate(loose))
    mismatch = metadata.build_capture_meta(ns(
        observed_condition="mount_looseness", target_label="normal", fault_level=1,
        fault_method="fastener_backoff", loose_fastener_id="M1", loosen_turns=0.25))
    ok &= check("工况与目标类别不一致会失败", bool(metadata.validate(mismatch)))
    old_schema = dict(m, schema_version=3)
    ok &= check("旧 schema 不能按正式契约通过", bool(metadata.validate(old_schema)))
    baseline_bad = metadata.build_capture_meta(ns(fault_level=1))
    ok &= check("baseline 混入故障等级会失败", bool(metadata.validate(baseline_bad)))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sample.csv")
        with open(path, "w", encoding="utf-8") as fp:
            metadata.write_header(fp, m)
            fp.write("1\n2\n")
        loaded = metadata.read_meta(path)
        ok &= check("meta_json 往返", loaded["record_id"] == "r1" and loaded["schema_version"] == 4 and
                    "quality_status" not in loaded)
        manifest = os.path.join(tmp, "manifest.csv")
        metadata.append_manifest(manifest, "formal/sample.csv", m, "a" * 64)
        rows = metadata.load_manifest(manifest)
        ok &= check("正式记录写入 manifest", len(rows) == 1 and rows[0]["file"] == "formal/sample.csv" and
                    rows[0]["quality_status"] == "pending" and rows[0]["file_sha256"] == "a" * 64)
        old = os.path.join(tmp, "legacy.csv")
        with open(old, "w", encoding="utf-8") as fp:
            fp.write("# tag=fan9v_normal axis=X fs=1000 per_frame=1024 frames=1\n1\n")
        legacy = metadata.read_meta(old)
        ok &= check("旧头兼容且标为 legacy debug", legacy["schema_version"] == 1 and legacy["data_role"] == "debug")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
