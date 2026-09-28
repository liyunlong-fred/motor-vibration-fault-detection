"""数据集元数据与标签契约。

标签不再使用 ``fan9v_normal`` 这种自由字符串，而是把客观工况、模型
类别、证据可信度和采集条件分开保存。本模块是 Python 侧唯一的元数据
解析/校验/落盘入口；串口帧解析仍由 frames.py 负责。
"""

import csv
import datetime as _datetime
import json
import os
import re


SCHEMA_VERSION = 4
MEASUREMENT_AXIS = "X"
REFERENCE_GRAVITY_AXIS = "Y"

DATA_ROLES = ("formal", "debug", "selftest", "calibration")
SOURCE_TYPES = ("real", "synthetic")
OBSERVED_CONDITIONS = ("baseline", "added_mass", "mount_looseness", "unknown")
TARGET_LABELS = ("normal", "unbalance", "looseness", "unassigned")
LABEL_BASES = ("controlled_injection", "unknown")
LABEL_CONFIDENCE = ("confirmed", "suspect", "unknown")
QUALITY_STATUSES = ("pending", "pass", "reject")

MANIFEST_FIELDS = [
    "file", "record_id", "schema_version", "data_role", "source_type",
    "device_id", "device_type", "session_id", "acquired_at", "observed_condition",
    "target_label", "label_basis", "label_confidence", "fault_level",
    "fault_method", "tape_spec_id", "tape_count", "tape_mass_mg",
    "tape_radius_mm", "tape_angle_deg", "loose_fastener_id", "loosen_turns",
    "mount_gap_mm", "fixture_id", "sensor_module_id", "sensor_mount_id",
    "installation_orientation_id", "measurement_axis", "reference_gravity_axis",
    "reference_gravity_sign", "calibration_id", "voltage_set_v", "voltage_measured_v",
    "rpm_measured", "fs_config_hz", "window_samples", "window_nominal_ms",
    "capture_samples", "capture_nominal_ms", "afs_code", "frames", "first_seq",
    "last_seq", "lost_frames", "sample_id_gaps", "capture_mode", "firmware_build_id",
    "board_stats_scope", "board_samples_captured", "board_continuity_breaks",
    "board_fifo_overflow", "board_iic_read_fail", "board_window_drop",
    "board_tx_drop", "board_tx_err", "board_max_fifo_batch", "quality_status",
    "quality_reason", "dataset_split", "file_sha256", "notes",
]

# These fields describe review and curation after acquisition.  They deliberately
# live only in manifest.csv; a CSV header is immutable capture evidence.
HEADER_EXCLUDED_FIELDS = {
    "file", "quality_status", "quality_reason", "dataset_split", "file_sha256",
}

_FLOAT_FIELDS = {
    "voltage_set_v", "voltage_measured_v", "rpm_measured", "tape_mass_mg",
    "tape_radius_mm", "tape_angle_deg", "loosen_turns", "mount_gap_mm",
    "window_nominal_ms", "capture_nominal_ms",
}
_INT_FIELDS = {
    "schema_version", "fault_level", "tape_count", "fs_config_hz", "window_samples",
    "capture_samples", "afs_code", "frames", "first_seq", "last_seq", "lost_frames",
    "sample_id_gaps", "board_samples_captured", "board_continuity_breaks",
    "board_fifo_overflow", "board_iic_read_fail", "board_window_drop",
    "board_tx_drop", "board_tx_err", "board_max_fifo_batch",
}


class MetadataError(ValueError):
    """元数据缺失或字段值不在受控范围内。"""


def _now_iso():
    return _datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _to_scalar(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text.lower() in ("none", "null", "na", "n/a", "-"):
        return None
    return text


def normalise(meta):
    """复制并统一字段类型，保留未知扩展字段以便向后兼容。"""
    out = {k: _to_scalar(v) for k, v in dict(meta).items()}
    for key in _INT_FIELDS:
        if out.get(key) is not None:
            try:
                out[key] = int(out[key])
            except (TypeError, ValueError):
                pass
    for key in _FLOAT_FIELDS:
        if out.get(key) is not None:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                pass
    return out


def derive_target_label(observed_condition):
    """从客观工况给出默认模型标签；unknown 不允许被自动猜成故障。"""
    return {
        "baseline": "normal",
        "added_mass": "unbalance",
        "mount_looseness": "looseness",
    }.get(observed_condition, "unassigned")


def build_capture_meta(args):
    """从 argparse Namespace 生成一次采集的元数据。"""
    condition = args.observed_condition
    target = args.target_label or derive_target_label(condition)
    stamp = args.acquired_at or _now_iso()
    session_id = args.session_id or stamp.replace("+", "_").replace(":", "")
    record_id = args.record_id or "%s_%s_r%03d" % (
        stamp.replace("-", "").replace(":", "").replace("+", "_").replace(".", ""),
        args.device_id,
        int(args.run_index),
    )
    return normalise({
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "data_role": args.data_role,
        "source_type": args.source_type,
        "device_id": args.device_id,
        "device_type": getattr(args, "device_type", None),
        "session_id": session_id,
        "acquired_at": stamp,
        "observed_condition": condition,
        "target_label": target,
        "label_basis": args.label_basis,
        "label_confidence": args.label_confidence,
        "fault_level": args.fault_level,
        "fault_method": args.fault_method,
        "tape_spec_id": args.tape_spec_id,
        "tape_count": args.tape_count,
        "tape_mass_mg": args.tape_mass_mg,
        "tape_radius_mm": args.tape_radius_mm,
        "tape_angle_deg": args.tape_angle_deg,
        "loose_fastener_id": getattr(args, "loose_fastener_id", None),
        "loosen_turns": getattr(args, "loosen_turns", None),
        "mount_gap_mm": getattr(args, "mount_gap_mm", None),
        "measurement_axis": MEASUREMENT_AXIS,
        "reference_gravity_axis": REFERENCE_GRAVITY_AXIS,
        "reference_gravity_sign": getattr(args, "reference_gravity_sign", None),
        "fixture_id": getattr(args, "fixture_id", None),
        "sensor_module_id": getattr(args, "sensor_module_id", None),
        "sensor_mount_id": getattr(args, "sensor_mount_id", None),
        "installation_orientation_id": getattr(args, "installation_orientation_id", None),
        "calibration_id": getattr(args, "calibration_id", None),
        "voltage_set_v": args.voltage_set_v,
        "voltage_measured_v": args.voltage_measured_v,
        "rpm_measured": args.rpm_measured,
        "firmware_build_id": getattr(args, "firmware_build_id", None),
        "notes": args.notes,
    })


def validate(meta, require_capture=True):
    """返回问题列表；空列表表示通过。"""
    m = normalise(meta)
    errors = []
    required = (
        "schema_version", "record_id", "data_role", "source_type", "device_id", "session_id",
        "observed_condition", "target_label", "label_basis", "label_confidence",
        "measurement_axis", "reference_gravity_axis",
    )
    for key in required:
        if m.get(key) in (None, ""):
            errors.append("缺少 %s" % key)
    if m.get("schema_version") not in (None, "") and m.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version 必须为 %d" % SCHEMA_VERSION)
    checks = {
        "data_role": DATA_ROLES,
        "source_type": SOURCE_TYPES,
        "observed_condition": OBSERVED_CONDITIONS,
        "target_label": TARGET_LABELS,
        "label_basis": LABEL_BASES,
        "label_confidence": LABEL_CONFIDENCE,
    }
    for key, allowed in checks.items():
        if m.get(key) not in (None, "") and m[key] not in allowed:
            errors.append("%s=%r 不在 %s" % (key, m[key], ",".join(allowed)))
    expected_target = derive_target_label(m.get("observed_condition"))
    if m.get("target_label") not in (None, "") and m["target_label"] != expected_target:
        errors.append("%s 必须映射为 target_label=%s" %
                      (m.get("observed_condition"), expected_target))
    if m.get("measurement_axis") != MEASUREMENT_AXIS:
        errors.append("measurement_axis 必须为 X")
    if m.get("reference_gravity_axis") != REFERENCE_GRAVITY_AXIS:
        errors.append("reference_gravity_axis 必须为 Y")
    if m.get("reference_gravity_sign") not in (None, "", "+1", "-1"):
        errors.append("reference_gravity_sign 必须为 +1 或 -1")
    if m.get("source_type") == "real" and m.get("voltage_set_v") is None:
        errors.append("真实风扇必须填写 voltage_set_v")
    if m.get("observed_condition") == "added_mass":
        if m.get("fault_level") is None or int(m["fault_level"]) < 1:
            errors.append("added_mass 必须填写 fault_level>=1")
        if m.get("tape_count") is None or int(m["tape_count"]) < 1:
            errors.append("added_mass 必须填写 tape_count>=1")
        if m.get("fault_method") != "tape_mass":
            errors.append("added_mass 的 fault_method 必须为 tape_mass")
        if not m.get("tape_spec_id"):
            errors.append("added_mass 必须填写 tape_spec_id")
    if m.get("observed_condition") == "mount_looseness":
        if m.get("fault_level") is None or int(m["fault_level"]) < 1:
            errors.append("mount_looseness 必须填写 fault_level>=1")
        if not m.get("fault_method"):
            errors.append("mount_looseness 必须填写 fault_method")
        if not m.get("loose_fastener_id"):
            errors.append("mount_looseness 必须填写 loose_fastener_id")
        loosen_turns = m.get("loosen_turns")
        mount_gap_mm = m.get("mount_gap_mm")
        if not ((isinstance(loosen_turns, (int, float)) and loosen_turns > 0) or
                (isinstance(mount_gap_mm, (int, float)) and mount_gap_mm > 0)):
            errors.append("mount_looseness 必须填写 loosen_turns>0 或 mount_gap_mm>0")
    if require_capture and m.get("data_role") == "formal":
        if m.get("observed_condition") == "unknown":
            errors.append("formal 数据不能使用 observed_condition=unknown")
        if m.get("label_basis") == "unknown":
            errors.append("formal 数据必须说明 label_basis")
        if m.get("label_confidence") == "unknown":
            errors.append("formal 数据必须说明 label_confidence")
        for key in ("fixture_id", "sensor_module_id", "sensor_mount_id",
                    "installation_orientation_id", "reference_gravity_sign",
                    "calibration_id", "firmware_build_id"):
            if m.get(key) in (None, ""):
                errors.append("formal 数据必须填写 %s" % key)
        if m.get("observed_condition") == "baseline":
            if m.get("fault_level") != 0:
                errors.append("baseline 必须填写 fault_level=0")
            if m.get("fault_method") or m.get("tape_spec_id") or m.get("tape_count", 0) != 0:
                errors.append("baseline 不能填写胶带或故障注入字段")
            if m.get("loose_fastener_id") or m.get("loosen_turns") or m.get("mount_gap_mm"):
                errors.append("baseline 不能填写松动注入字段")
    return errors


def _legacy_meta_from_line(line):
    result = {}
    for token in line.lstrip("#").strip().split():
        if "=" in token:
            key, value = token.split("=", 1)
            result[key] = value
    if "tag" in result:
        tag = result["tag"]
        result.setdefault("schema_version", 1)
        result.setdefault("data_role", "debug")
        result.setdefault("source_type", "real")
        result.setdefault("device_id", "legacy_unknown")
        result.setdefault("session_id", "legacy")
        result.setdefault("observed_condition", "unknown")
        result.setdefault("target_label", "unassigned")
        result.setdefault("label_basis", "unknown")
        result.setdefault("label_confidence", "unknown")
        result.setdefault("legacy_tag", tag)
    return result


def read_meta(path):
    """读取新JSON头；若没有则兼容旧版 ``# k=v`` 头。"""
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            if not line.startswith("#"):
                break
            text = line[1:].strip()
            if text.startswith("meta_json="):
                try:
                    return normalise(json.loads(text[len("meta_json="):]))
                except json.JSONDecodeError as exc:
                    raise MetadataError("meta_json 无法解析: %s" % exc)
            legacy = _legacy_meta_from_line(line)
            if legacy:
                return normalise(legacy)
    return {}


def write_header(fp, meta):
    """把元数据写成CSV注释行，np.loadtxt会自动忽略。"""
    clean = {k: v for k, v in normalise(meta).items()
             if v is not None and k not in HEADER_EXCLUDED_FIELDS}
    fp.write("# meta_json=" + json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + "\n")


def make_filename(meta, axis, first_seq, last_seq):
    def safe(value):
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value))
    voltage = meta.get("voltage_set_v")
    voltage_text = "na" if voltage is None else ("%gV" % float(voltage))
    return "%s_%s_%s_%s_%s_r%04d-%04d.csv" % (
        safe(meta.get("record_id", "record")),
        safe(meta.get("device_id", "unknown")),
        safe(meta.get("observed_condition", "unknown")),
        voltage_text,
        safe(axis),
        int(first_seq),
        int(last_seq),
    )


def append_manifest(manifest_path, relative_file, meta, file_sha256):
    """只把正式采集写入清单；debug数据由文件头自描述但不进入训练索引。"""
    if meta.get("data_role") != "formal":
        return
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    exists = os.path.isfile(manifest_path) and os.path.getsize(manifest_path) > 0
    row = {key: "" if meta.get(key) is None else meta.get(key) for key in MANIFEST_FIELDS}
    row["file"] = relative_file.replace("\\", "/")
    row["quality_status"] = "pending"
    row["quality_reason"] = ""
    row["dataset_split"] = ""
    row["file_sha256"] = file_sha256
    with open(manifest_path, "a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=MANIFEST_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_manifest(path):
    with open(path, newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))
