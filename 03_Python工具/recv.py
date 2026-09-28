# 03_Python工具\recv.py
"""从串口接收固件数据帧，并按统一标签契约落盘。

旧版 ``04_数据集/raw`` 文件保持兼容但不再写入；正式数据写入
``04_数据集/formal``，调试数据写入 ``04_数据集/debug_raw``；板端文本日志写入
``05_演示与输出/boardlog``。
"""

import argparse
import datetime
import hashlib
import os
import re
import sys

import numpy as np
import serial

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "py_common"))
import frames
import metadata

PROJ = os.path.dirname(_HERE)
DEFAULT_PORT = "COM17"
DEFAULT_BAUD = 460800
DEFAULT_FRAMES = 20
AXIS_EXPECT = metadata.MEASUREMENT_AXIS
FORMAL_DIR = os.path.join(PROJ, "04_数据集", "formal")
DEBUG_DIR = os.path.join(PROJ, "04_数据集", "debug_raw")
MANIFEST = os.path.join(PROJ, "04_数据集", "manifest.csv")
LOG_DIR = os.path.join(PROJ, "05_演示与输出", "boardlog")

_CAP_STATS_RE = re.compile(
    r"\bCAP\s+samples=(?P<samples>\d+)\s+break=(?P<breaks>\d+)"
    r"\s+fifo_ovf=(?P<fifo_ovf>\d+)\s+iic_fail=(?P<iic_fail>\d+)"
    r"\s+win_drop=(?P<win_drop>\d+)\s+tx_drop=(?P<tx_drop>\d+)"
    r"\s+tx_err=(?P<tx_err>\d+)\s+batch=(?P<batch>\d+)\b"
)


def build_parser():
    p = argparse.ArgumentParser(description="接收 MPU6050 X 轴振动帧并保存带标签 CSV")
    p.add_argument("--port", default=DEFAULT_PORT)
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    p.add_argument("--data-role", choices=metadata.DATA_ROLES, required=True,
                   help="formal=正式数据，debug=调试数据")
    p.add_argument("--source-type", choices=metadata.SOURCE_TYPES, default="real")
    p.add_argument("--device-id", required=True, help="风扇/被测设备稳定编号，如 fanA")
    p.add_argument("--device-type", default="fan")
    p.add_argument("--session-id")
    p.add_argument("--run-index", type=int, default=1)
    p.add_argument("--record-id")
    p.add_argument("--acquired-at")
    p.add_argument("--observed-condition", choices=metadata.OBSERVED_CONDITIONS,
                   required=True, help="baseline/added_mass/mount_looseness/unknown")
    p.add_argument("--target-label", choices=metadata.TARGET_LABELS,
                   help="默认按 observed-condition 推导，不建议手工覆盖")
    p.add_argument("--label-basis", choices=metadata.LABEL_BASES, default="unknown")
    p.add_argument("--label-confidence", choices=metadata.LABEL_CONFIDENCE, default="unknown")
    p.add_argument("--fault-level", type=int, default=0)
    p.add_argument("--fault-method", default="")
    p.add_argument("--tape-spec-id", default="")
    p.add_argument("--tape-count", type=int, default=0)
    p.add_argument("--tape-mass-mg", type=float)
    p.add_argument("--tape-radius-mm", type=float)
    p.add_argument("--tape-angle-deg", type=float)
    p.add_argument("--loose-fastener-id", default="",
                   help="松动的安装紧固点编号，如 M1")
    p.add_argument("--loosen-turns", type=float,
                   help="从基准紧固位置回退的圈数")
    p.add_argument("--mount-gap-mm", type=float,
                   help="安装点可复现间隙，毫米；与回退圈数至少填一项")
    p.add_argument("--fixture-id", default="", help="刚性夹具的稳定编号，如 rig01")
    p.add_argument("--sensor-module-id", default="", help="MPU6050 模块稳定编号，如 mpu01")
    p.add_argument("--sensor-mount-id", default="", help="模块在被测设备上的测点编号")
    p.add_argument("--installation-orientation-id", default="",
                   help="安装姿态编号；须能唯一解释测量轴和重力参考轴")
    p.add_argument("--reference-gravity-sign", choices=("+1", "-1"),
                   help="静态基准安装时，重力在 Y 参考轴上的符号")
    p.add_argument("--calibration-id", default="uncalibrated",
                   help="应用的标定记录编号；当前未补偿时填写 uncalibrated")
    p.add_argument("--voltage-set-v", type=float, required=True)
    p.add_argument("--voltage-measured-v", type=float)
    p.add_argument("--rpm-measured", type=float)
    p.add_argument("--firmware-build-id", default="",
                   help="实际烧录固件的提交号或可追溯构建标识")
    p.add_argument("--notes", default="")
    return p


def _capture_meta(args):
    meta = metadata.build_capture_meta(args)
    meta["device_type"] = args.device_type
    errors = metadata.validate(meta)
    if errors:
        raise metadata.MetadataError("；".join(errors))
    return meta


def _open_serial(args):
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print("打开串口失败: %s" % exc)
        print("排查: 板子、串口助手占用、端口号是否正确 (%s)" % args.port)
        return None
    ser.dtr = False
    ser.rts = False
    ser.reset_input_buffer()
    return ser


def _parse_board_stats(line):
    """解析固件 CAP 文本帧；计数器的语义是自上电以来的累计值。"""
    match = _CAP_STATS_RE.search(line)
    if not match:
        return None
    values = {key: int(value) for key, value in match.groupdict().items()}
    return {
        "board_stats_scope": "since_boot",
        "board_samples_captured": values["samples"],
        "board_continuity_breaks": values["breaks"],
        "board_fifo_overflow": values["fifo_ovf"],
        "board_iic_read_fail": values["iic_fail"],
        "board_window_drop": values["win_drop"],
        "board_tx_drop": values["tx_drop"],
        "board_tx_err": values["tx_err"],
        "board_max_fifo_batch": values["batch"],
    }


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None, result_out=None, stop_event=None):
    """执行一次采集。

    ``result_out`` 是可选的可变映射，供图形化/批处理调用方取得这一次
    明确生成的文件路径和接收统计。命令行行为和退出码保持不变，不能靠
    "最新文件"推断本次结果。``stop_event`` 由图形界面的强制结束按钮设置。
    """
    args = build_parser().parse_args(argv)
    if args.frames < 1:
        print("--frames 必须大于 0")
        return 2
    try:
        meta = _capture_meta(args)
    except metadata.MetadataError as exc:
        print("标签校验失败: %s" % exc)
        return 2

    ser = _open_serial(args)
    if ser is None:
        return 1
    print("已打开 %s @ %d, 目标 %d 帧，按 Ctrl+C 可提前结束" %
          (args.port, args.baud, args.frames))

    buf = bytearray()
    datas = []
    axis = None
    afs_code = 0
    seq_first = None
    seq_last = 0
    lost = 0
    expected_sample_id = None
    sample_id_gaps = 0
    board_stats = None
    forced_stop = False
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "%s_boardlog.txt" % stamp)
    log_fp = open(log_path, "w", encoding="utf-8")

    try:
        while len(datas) < args.frames:
            if stop_event is not None and stop_event.is_set():
                print("\n[强制停止]")
                forced_stop = True
                break
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                buf += chunk
            while True:
                pos = frames.find_head(buf)
                if pos < 0:
                    if len(buf) > 1:
                        del buf[:len(buf) - 1]
                    break
                if pos > 0:
                    del buf[:pos]
                status, frame, used = frames.parse_frame(buf)
                if status == "more":
                    break
                if status == "bad":
                    del buf[0]
                    continue
                del buf[:used]
                if frame["type"] == frames.TYPE_TEXT:
                    line = frame["text"].rstrip("\r\n")
                    print(line)
                    log_fp.write(line + "\n")
                    log_fp.flush()
                    parsed_stats = _parse_board_stats(line)
                    if parsed_stats is not None:
                        board_stats = parsed_stats
                    continue
                if seq_last and frame["seq"] != seq_last + 1:
                    miss = frame["seq"] - seq_last - 1
                    lost += max(0, miss)
                    print("  !! 丢帧: 期望 %d，实收 %d (丢 %d 帧)" %
                          (seq_last + 1, frame["seq"], miss))
                if (expected_sample_id is not None and
                        frame["first_sample_id"] != expected_sample_id):
                    sample_id_gaps += 1
                    print("  !! 样本不连续: 期望 first_sample_id=%d，实收 %d" %
                          (expected_sample_id, frame["first_sample_id"]))
                if seq_first is None:
                    seq_first = frame["seq"]
                seq_last = frame["seq"]
                expected_sample_id = (frame["first_sample_id"] + frame["n"]) & 0xFFFFFFFF
                axis = frame["axis"]
                afs_code = frame["afs_code"]
                datas.append(frame["data"])
                print("  接收进度 [%2d/%2d] axis=%s seq=%d first=%d n=%d afs=%d" %
                      (len(datas), args.frames, frame["axis"], frame["seq"],
                       frame["first_sample_id"], frame["n"], frame["afs_code"]))
    except KeyboardInterrupt:
        print("\n[手动停止]")
    finally:
        if ser.is_open:
            ser.close()
            print("串口已关闭")
        log_fp.close()
        print("日志已保存: %s" % log_path)

    if forced_stop:
        print("本次采集已取消，不保存部分数据")
        return 1
    if not datas:
        print("没有收到任何帧，不保存")
        return 1
    if axis != AXIS_EXPECT:
        print("注意: 收到的是 %s 轴，期望 %s 轴" % (axis, AXIS_EXPECT))

    all_data = np.concatenate(datas)
    meta.update({
        "measurement_axis": axis,
        "fs_config_hz": frames.FS_HZ,
        "window_samples": int(datas[0].size),
        "window_nominal_ms": 1000.0 * datas[0].size / frames.FS_HZ,
        "capture_samples": int(all_data.size),
        "capture_nominal_ms": 1000.0 * all_data.size / frames.FS_HZ,
        "afs_code": int(afs_code),
        "frames": len(datas),
        "first_seq": int(seq_first),
        "last_seq": int(seq_last),
        "lost_frames": int(lost),
        "sample_id_gaps": int(sample_id_gaps),
        "capture_mode": "fifo_continuous",
    })
    if board_stats is not None:
        meta.update(board_stats)
    errors = metadata.validate(meta, require_capture=False)
    if errors:
        print("采集后元数据校验失败，不保存: %s" % "；".join(errors))
        return 2
    if args.data_role == "formal" and (lost != 0 or sample_id_gaps != 0):
        print("正式数据拒绝写入：存在丢帧或样本不连续")
        return 2
    out_dir = FORMAL_DIR if args.data_role == "formal" else DEBUG_DIR
    os.makedirs(out_dir, exist_ok=True)
    filename = metadata.make_filename(meta, axis, seq_first, seq_last)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as fp:
        metadata.write_header(fp, meta)
        np.savetxt(fp, all_data, fmt="%d")
    file_sha256 = _sha256_file(path)
    if args.data_role == "formal":
        metadata.append_manifest(MANIFEST, os.path.join("formal", filename), meta, file_sha256)

    if result_out is not None:
        result_out.update({
            "path": path,
            "meta": meta,
            "frames": len(datas),
            "lost_frames": lost,
            "sample_id_gaps": sample_id_gaps,
            "board_log_path": log_path,
        })

    print("-" * 56)
    print("共收到 %d 帧，丢帧 %d，样本不连续 %d" %
          (len(datas), lost, sample_id_gaps))
    print("已保存: %s  (%d 个样本)" % (path, all_data.size))
    if args.data_role == "formal":
        print("已登记: %s" % MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
