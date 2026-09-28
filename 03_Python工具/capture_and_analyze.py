"""交互式采集、分析与质检入口。

运行本脚本后填写采集事实，程序会复用 recv.py 接收本次串口数据；只有
明确返回的 CSV 会被传给检查、频谱、峰值和谐波分析，绝不以“最新文件”
作为输入。正式数据仍遵守 schema v4：自动登记为 pending，必须由操作者
在看过结果并确认现场事实后再标记 pass 或 reject。
"""

from __future__ import annotations

import contextlib
import csv
import os
import queue
import sys
import tempfile
import threading
import traceback
from pathlib import Path

import numpy as np

# Conda 的 Windows 布局把 Tcl/Tk 放在 ``Library/lib``。工程路径含中文时，
# Tcl 有时无法从 Python 可执行文件路径反推出该目录，导致 init.tcl 找不到。
# 在导入 tkinter、创建窗口前明确给出本环境的真实目录，且不覆盖用户已有设置。
_TCL_DIR = Path(sys.prefix) / "Library" / "lib" / "tcl8.6"
_TK_DIR = Path(sys.prefix) / "Library" / "lib" / "tk8.6"
if (_TCL_DIR / "init.tcl").is_file() and (_TK_DIR / "tk.tcl").is_file():
    os.environ.setdefault("TCL_LIBRARY", str(_TCL_DIR))
    os.environ.setdefault("TK_LIBRARY", str(_TK_DIR))

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "py_common"))

import frames
import harmonics
import metadata
import peak_check
import recv

OUTPUT_DIR = PROJ / "05_演示与输出" / "debug"

# 与既有 plot_check.py 保持一致，避免 Windows 上保存结果图时中文变成方块。
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False


class QueueWriter:
    """把 recv.py 的终端进度安全地转交给 Tk 主线程。"""

    def __init__(self, events: queue.Queue):
        self.events = events

    def write(self, text: str) -> int:
        if text:
            self.events.put(("log", text))
        return len(text)

    def flush(self) -> None:
        pass


def _float_or_none(value):
    text = str(value).strip()
    return None if not text else float(text)


def _top_peaks_from_spectrum(freq, amp, count=5, fmin=10.0, fmax=400.0, guard=2):
    """与 peak_check 的频段和避让规则一致，分析平均谱供汇总显示。"""
    usable = np.where((freq >= fmin) & (freq <= fmax))[0]
    work = np.asarray(amp, dtype=float).copy()
    out = []
    for _ in range(count):
        if not usable.size:
            break
        index = int(usable[int(np.argmax(work[usable]))])
        if work[index] <= 0:
            break
        out.append((index, float(freq[index]), float(work[index])))
        work[max(0, index - guard):index + guard + 1] = 0.0
    return out


def analyse_capture(csv_path: str) -> dict:
    """执行本次 CSV 的全部只读分析，返回供 GUI 和报告共用的结构化结果。"""
    path = Path(csv_path)
    meta = metadata.read_meta(path)
    # recv.py writes UTF-8 JSON metadata (which may contain Chinese) in comment
    # lines.  NumPy otherwise falls back to the Windows ANSI/GBK codec here.
    raw = np.atleast_1d(np.loadtxt(path, comments="#", dtype=np.int16,
                                  encoding="utf-8-sig"))
    fs = int(meta.get("fs_config_hz", frames.FS_HZ))
    n = int(meta.get("window_samples", frames.MAX_N))
    afs_code = int(meta.get("afs_code", 0))
    frame_count = min(int(meta.get("frames", 1)), raw.size // n)
    if frame_count < 1:
        raise ValueError("CSV 不包含完整采样窗，无法分析")

    g = frames.to_g(raw[:frame_count * n], afs_code)
    per_window = []
    for index in range(frame_count):
        win = g[index * n:(index + 1) * n]
        centered = win - win.mean()
        _, peaks = peak_check.top_peaks(win, fs, n)
        per_window.append({
            "index": index + 1,
            "rms_g": float(np.sqrt(np.mean(centered * centered))),
            "pp_g": float(centered.max() - centered.min()),
            "top_frequency_hz": float(peaks[0][1]) if peaks else None,
            "top_amplitude_g": float(peaks[0][2]) if peaks else None,
            "peaks": peaks,
        })

    freq, avg_amp, averaged_frames = harmonics.average_spectrum(raw, fs, n, afs_code)
    harmonic = harmonics.analyze(
        freq, avg_amp,
        rpm_measured=meta.get("rpm_measured"),
    )
    spectrum_peaks = _top_peaks_from_spectrum(freq, avg_amp)

    gate = []
    axis = meta.get("measurement_axis")
    if axis != metadata.MEASUREMENT_AXIS:
        gate.append("失败：收到 %s 轴，正式测量轴必须为 X" % (axis or "未知"))
    if int(meta.get("lost_frames", 0)) != 0:
        gate.append("失败：检测到 %s 个丢帧" % meta.get("lost_frames"))
    if int(meta.get("sample_id_gaps", 0)) != 0:
        gate.append("失败：检测到 %s 处样本不连续" % meta.get("sample_id_gaps"))
    for key, label in (
        ("board_continuity_breaks", "板端连续性中断"),
        ("board_fifo_overflow", "FIFO 溢出"),
        ("board_iic_read_fail", "IIC 读取失败"),
        ("board_window_drop", "窗口丢弃"),
        ("board_tx_drop", "发送丢弃"),
        ("board_tx_err", "发送错误"),
    ):
        if meta.get(key) not in (None, "") and int(meta[key]) != 0:
            gate.append("警告：%s=%s（板端为自上电累计值）" % (label, meta[key]))
    if not any(item.startswith("失败") for item in gate):
        gate.insert(0, "技术完整性门槛通过：X 轴、丢帧和样本连续性正常")
    if meta.get("board_stats_scope") != "since_boot":
        gate.append("提示：本次未收到 CAP 板端累计统计，必要时复位后延长调试采集确认")
    if meta.get("data_role") == "formal":
        gate.append("正式数据仍为 pending：请结合现场是否位移、标签是否可信后再人工质检")

    return {
        "path": str(path), "meta": meta, "raw": raw, "g": g, "fs": fs, "n": n,
        "frame_count": frame_count, "per_window": per_window, "freq": freq,
        "avg_amp": avg_amp, "averaged_frames": averaged_frames,
        "spectrum_peaks": spectrum_peaks, "harmonic": harmonic, "gate": gate,
    }


def make_report_text(result: dict) -> str:
    meta = result["meta"]
    windows = result["per_window"]
    rms = [item["rms_g"] for item in windows]
    pp = [item["pp_g"] for item in windows]
    lines = [
        "================ 采集后自动分析 ================",
        "文件：%s" % result["path"],
        "记录：%s    模式：%s" % (meta.get("record_id"), meta.get("data_role")),
        "工况：%s → %s    设备：%s" % (
            meta.get("observed_condition"), meta.get("target_label"), meta.get("device_id")),
        "样本：%d（%d 窗 × %d 点）  采样率：%d Hz" % (
            result["g"].size, result["frame_count"], result["n"], result["fs"]),
        "窗口交流 RMS：中位 %.5f g，范围 %.5f～%.5f g" % (
            float(np.median(rms)), min(rms), max(rms)),
        "窗口交流峰峰值：中位 %.5f g，范围 %.5f～%.5f g" % (
            float(np.median(pp)), min(pp), max(pp)),
        "",
        "[技术完整性与人工质检提示]",
        *["- " + item for item in result["gate"]],
        "",
        "[平均谱 TOP-5（10～400 Hz）]",
    ]
    for rank, (_, freq, amp) in enumerate(result["spectrum_peaks"], 1):
        lines.append("%d. %7.2f Hz   %.5f g" % (rank, freq, amp))
    lines += ["", harmonics.format_report(
        result["path"], meta, result["freq"], result["avg_amp"],
        result["averaged_frames"], result["harmonic"])]
    return "\n".join(lines)


def build_dashboard(result: dict) -> Figure:
    """生成一张可嵌入窗口、也可保存的三联结果图。"""
    fig = Figure(figsize=(11, 8), dpi=110)
    fig.subplots_adjust(hspace=0.48, left=0.09, right=0.93, top=0.92, bottom=0.08)
    ax_time, ax_spectrum, ax_trend = fig.subplots(3, 1)
    g, fs, n = result["g"], result["fs"], result["n"]
    first = g[:n]
    shown = min(n, max(1, int(0.1 * fs)))
    time_ms = np.arange(shown) / fs * 1000.0
    ax_time.plot(time_ms, first[:shown], color="#1967d2", linewidth=0.9)
    ax_time.set_title("首窗时域（前 100 ms）")
    ax_time.set_xlabel("时间 (ms)")
    ax_time.set_ylabel("加速度 (g)")
    ax_time.grid(True, alpha=0.3)

    freq, amp = result["freq"], result["avg_amp"]
    ax_spectrum.plot(freq, amp, color="#d93025", linewidth=1.0)
    ax_spectrum.set_title("全段平均单边幅值谱（Hann 窗）")
    ax_spectrum.set_xlim(0, min(500, fs / 2))
    ax_spectrum.set_xlabel("频率 (Hz)")
    ax_spectrum.set_ylabel("幅值 (g)")
    ax_spectrum.grid(True, alpha=0.3)
    for _, peak_freq, peak_amp in result["spectrum_peaks"][:3]:
        ax_spectrum.annotate("%.1f Hz" % peak_freq, (peak_freq, peak_amp),
                             xytext=(0, 7), textcoords="offset points",
                             ha="center", fontsize=8)

    window = np.arange(1, result["frame_count"] + 1)
    top_freq = [item["top_frequency_hz"] or np.nan for item in result["per_window"]]
    rms_mg = [item["rms_g"] * 1000.0 for item in result["per_window"]]
    ax_trend.plot(window, top_freq, marker="o", color="#188038", label="主峰频率")
    ax_trend.set_title("逐窗稳定性：主峰频率与交流 RMS")
    ax_trend.set_xlabel("窗口序号")
    ax_trend.set_ylabel("主峰频率 (Hz)", color="#188038")
    ax_trend.tick_params(axis="y", labelcolor="#188038")
    ax_trend.grid(True, alpha=0.3)
    right = ax_trend.twinx()
    right.plot(window, rms_mg, marker="s", color="#9334e6", label="RMS")
    right.set_ylabel("交流 RMS (mg)", color="#9334e6")
    right.tick_params(axis="y", labelcolor="#9334e6")
    fig.suptitle("电机振动采集结果：%s" % result["meta"].get("record_id", "本次采集"))
    return fig


def update_manifest_quality(csv_path: str, status: str, reason: str) -> None:
    """只更新对应正式记录的可编辑 manifest 字段，不改 CSV 不可变文件头。"""
    if status not in metadata.QUALITY_STATUSES:
        raise ValueError("未知质检状态：%s" % status)
    path = Path(csv_path)
    meta = metadata.read_meta(path)
    if meta.get("data_role") != "formal":
        raise ValueError("只有 formal 采集会登记 manifest，调试/自检/标定无需质检")
    manifest_path = PROJ / "04_数据集" / "manifest.csv"
    relative = "formal/" + path.name
    with manifest_path.open(newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        fields = reader.fieldnames
        rows = list(reader)
    found = False
    for row in rows:
        if row.get("file") == relative and row.get("record_id") == str(meta.get("record_id")):
            row["quality_status"] = status
            row["quality_reason"] = reason.strip()
            found = True
            break
    if not found or not fields:
        raise ValueError("manifest 中找不到本次正式采集记录，未作修改")
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False,
                                     dir=manifest_path.parent, prefix="manifest_", suffix=".tmp") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        temp_path = fp.name
    os.replace(temp_path, manifest_path)


class CaptureApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("电机振动：采集与分析")
        self.minsize(900, 700)
        self.events: queue.Queue = queue.Queue()
        self.current_result = None
        self.stop_event = None
        self._closing = False
        self._entries = {}
        self._build_variables()
        self._build_ui()
        self.after(100, self._drain_events)

    def _build_variables(self):
        defaults = {
            "data_role": "debug", "port": recv.DEFAULT_PORT, "baud": str(recv.DEFAULT_BAUD),
            "frames": str(recv.DEFAULT_FRAMES), "source_type": "real", "device_id": "fanA",
            "device_type": "fan", "session_id": "fanA_rig01_9V_20260928", "run_index": "1",
            "observed_condition": "unknown", "label_basis": "unknown",
            "label_confidence": "unknown", "voltage_set_v": "9", "voltage_measured_v": "",
            "rpm_measured": "", "fault_level": "0", "fault_method": "",
            "tape_spec_id": "", "tape_count": "0", "tape_mass_mg": "",
            "tape_radius_mm": "", "tape_angle_deg": "", "loose_fastener_id": "",
            "loosen_turns": "", "mount_gap_mm": "", "fixture_id": "rig01",
            # 当前固定工装的稳定编号；变更模块、测点或姿态时必须先修改。
            "sensor_module_id": "mpu01", "sensor_mount_id": "fan_frame_top_left",
            "installation_orientation_id": "x_measure_y_gravity",
            "reference_gravity_sign": "+1", "calibration_id": "uncalibrated",
            "firmware_build_id": "", "notes": "", "quality_status": "pending",
            "quality_reason": "", "hardware_ready": False,
        }
        self.vars = {name: tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=value)
                     for name, value in defaults.items()}

    def _entry(self, parent, row, label, name, width=28):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        widget = ttk.Entry(parent, textvariable=self.vars[name], width=width)
        widget.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        self._entries[name] = widget
        return widget

    def _combo(self, parent, row, label, name, values, width=26):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        widget = ttk.Combobox(parent, textvariable=self.vars[name], values=values, state="readonly", width=width)
        widget.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        self._entries[name] = widget
        return widget

    def _build_ui(self):
        ttk.Label(self, text="填写采集事实 → 自动接收 → 自动分析本次 CSV",
                  font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
        ttk.Label(self, text="正式数据先登记为 pending；频谱分析是辅助判断，不能代替现场标签和 TACH 对拍。",
                  foreground="#555555").pack(anchor="w", padx=12, pady=(0, 8))
        book = ttk.Notebook(self)
        book.pack(fill="both", expand=True, padx=12, pady=4)

        basic = ttk.Frame(book, padding=8)
        condition = ttk.Frame(book, padding=8)
        provenance = ttk.Frame(book, padding=8)
        runtime = ttk.Frame(book, padding=8)
        book.add(basic, text="1. 基本信息")
        book.add(condition, text="2. 工况与标签")
        book.add(provenance, text="3. 溯源信息")
        book.add(runtime, text="4. 采集与日志")
        for page in (basic, condition, provenance):
            page.columnconfigure(1, weight=1)

        self._combo(basic, 0, "采集模式", "data_role", metadata.DATA_ROLES)
        self._combo(basic, 1, "数据来源", "source_type", metadata.SOURCE_TYPES)
        self._entry(basic, 2, "串口", "port")
        self._entry(basic, 3, "波特率", "baud")
        self._entry(basic, 4, "采集帧数", "frames")
        self._entry(basic, 5, "设备编号", "device_id")
        self._entry(basic, 6, "设备类型", "device_type")
        self._entry(basic, 7, "会话编号（同一连续实验共用）", "session_id")
        self._entry(basic, 8, "本会话运行序号", "run_index")
        self._entry(basic, 9, "设定电压 V", "voltage_set_v")
        self._entry(basic, 10, "实测电压 V（可选）", "voltage_measured_v")
        self._entry(basic, 11, "实测转速 RPM（可选）", "rpm_measured")

        self._combo(condition, 0, "客观工况", "observed_condition", metadata.OBSERVED_CONDITIONS)
        self._combo(condition, 1, "标签依据", "label_basis", metadata.LABEL_BASES)
        self._combo(condition, 2, "标签可信度", "label_confidence", metadata.LABEL_CONFIDENCE)
        ttk.Label(condition, text="模型标签会由客观工况自动推导，不能手填覆盖。", foreground="#555555").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=6, pady=8)
        self.tape_group = ttk.LabelFrame(condition, text="贴胶带不平衡（仅 added_mass）", padding=6)
        self.tape_group.grid(row=4, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self.tape_group.columnconfigure(1, weight=1)
        self._entry(self.tape_group, 0, "故障等级", "fault_level")
        self._entry(self.tape_group, 1, "胶带规格编号", "tape_spec_id")
        self._entry(self.tape_group, 2, "胶带数量", "tape_count")
        self._entry(self.tape_group, 3, "总质量 mg（可选）", "tape_mass_mg")
        self._entry(self.tape_group, 4, "半径 mm（可选）", "tape_radius_mm")
        self._entry(self.tape_group, 5, "角度 deg（可选）", "tape_angle_deg")
        self.loose_group = ttk.LabelFrame(condition, text="安装松动（仅 mount_looseness）", padding=6)
        self.loose_group.grid(row=5, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self.loose_group.columnconfigure(1, weight=1)
        self._entry(self.loose_group, 0, "故障等级", "fault_level")
        self._entry(self.loose_group, 1, "松动方法", "fault_method")
        self._entry(self.loose_group, 2, "松动紧固点编号", "loose_fastener_id")
        self._entry(self.loose_group, 3, "回退圈数", "loosen_turns")
        self._entry(self.loose_group, 4, "安装间隙 mm（可选）", "mount_gap_mm")

        ttk.Label(provenance, text="formal 模式必须全部填写；其他模式可按需要留空。",
                  foreground="#555555").grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=5)
        self._entry(provenance, 1, "夹具编号", "fixture_id")
        self._entry(provenance, 2, "传感器模块编号", "sensor_module_id")
        self._entry(provenance, 3, "传感器测点编号", "sensor_mount_id")
        self._entry(provenance, 4, "安装姿态编号", "installation_orientation_id")
        self._combo(provenance, 5, "Y 轴重力参考符号", "reference_gravity_sign", ("+1", "-1"))
        self._entry(provenance, 6, "标定记录编号", "calibration_id")
        self._entry(provenance, 7, "实际烧录固件构建标识", "firmware_build_id")
        ttk.Label(provenance, text="备注").grid(row=8, column=0, sticky="nw", padx=6, pady=4)
        notes = ScrolledText(provenance, height=5, width=65, wrap="word")
        notes.grid(row=8, column=1, sticky="nsew", padx=6, pady=4)
        self.notes_box = notes

        ttk.Checkbutton(runtime, text="我已确认：硬件工况已设置、风扇稳定、串口未被其他程序占用",
                        variable=self.vars["hardware_ready"]).pack(anchor="w", pady=(2, 8))
        controls = ttk.Frame(runtime)
        controls.pack(anchor="w", pady=(0, 8))
        self.start_button = ttk.Button(controls, text="提交并开始自动采集", command=self._start_capture)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="强制结束本次采集", command=self._request_stop,
                                      state="disabled")
        self.stop_button.grid(row=0, column=1)
        self.log_box = ScrolledText(runtime, height=24, wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True)
        ttk.Label(runtime, text="采集期间请勿修改硬件或关闭窗口；结果会在采集完成后自动弹出。",
                  foreground="#555555").pack(anchor="w", pady=(6, 0))

        self.vars["data_role"].trace_add("write", lambda *_: self._refresh_form())
        self.vars["observed_condition"].trace_add("write", lambda *_: self._refresh_form())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_form()

    def _refresh_form(self):
        role = self.vars["data_role"].get()
        condition = self.vars["observed_condition"].get()
        if role == "formal" and condition == "unknown":
            self.vars["observed_condition"].set("baseline")
            condition = "baseline"
        if role == "formal":
            if self.vars["label_basis"].get() == "unknown":
                self.vars["label_basis"].set("controlled_injection")
            if self.vars["label_confidence"].get() == "unknown":
                self.vars["label_confidence"].set("confirmed")
        self.tape_group.grid() if condition == "added_mass" else self.tape_group.grid_remove()
        self.loose_group.grid() if condition == "mount_looseness" else self.loose_group.grid_remove()
        if condition == "baseline":
            self.vars["fault_level"].set("0")
            self.vars["tape_count"].set("0")
            self.vars["fault_method"].set("")
        elif condition == "added_mass":
            if self.vars["fault_level"].get() in ("", "0"):
                self.vars["fault_level"].set("1")
            self.vars["fault_method"].set("tape_mass")
        elif condition == "mount_looseness":
            if self.vars["fault_level"].get() in ("", "0"):
                self.vars["fault_level"].set("1")
            if not self.vars["fault_method"].get():
                self.vars["fault_method"].set("fastener_backoff")

    def _capture_argv(self):
        values = {name: variable.get().strip() if isinstance(variable, tk.StringVar) else variable.get()
                  for name, variable in self.vars.items()}
        values["notes"] = self.notes_box.get("1.0", "end-1c").strip()
        if not values["hardware_ready"]:
            raise ValueError("请先完成硬件准备确认")
        if not values["device_id"]:
            raise ValueError("必须填写设备编号")
        try:
            if int(values["frames"]) < 1 or int(values["run_index"]) < 1:
                raise ValueError
            int(values["baud"])
            _float_or_none(values["voltage_set_v"])
        except ValueError:
            raise ValueError("帧数、运行序号、波特率和设定电压必须是有效正数")
        if not values["voltage_set_v"] and values["source_type"] == "real":
            raise ValueError("真实设备必须填写设定电压")

        argv = []
        def add(flag, key, always=False):
            value = values[key]
            if always or value not in (None, ""):
                argv.extend((flag, str(value)))

        for flag, key in (
            ("--port", "port"), ("--baud", "baud"), ("--frames", "frames"),
            ("--data-role", "data_role"), ("--source-type", "source_type"),
            ("--device-id", "device_id"), ("--device-type", "device_type"),
            ("--run-index", "run_index"), ("--observed-condition", "observed_condition"),
            ("--label-basis", "label_basis"), ("--label-confidence", "label_confidence"),
            ("--fault-level", "fault_level"), ("--fault-method", "fault_method"),
            ("--tape-spec-id", "tape_spec_id"), ("--tape-count", "tape_count"),
            ("--voltage-set-v", "voltage_set_v"), ("--notes", "notes"),
        ):
            add(flag, key, always=True)
        for flag, key in (
            ("--session-id", "session_id"), ("--voltage-measured-v", "voltage_measured_v"),
            ("--rpm-measured", "rpm_measured"), ("--tape-mass-mg", "tape_mass_mg"),
            ("--tape-radius-mm", "tape_radius_mm"), ("--tape-angle-deg", "tape_angle_deg"),
            ("--loose-fastener-id", "loose_fastener_id"), ("--loosen-turns", "loosen_turns"),
            ("--mount-gap-mm", "mount_gap_mm"), ("--fixture-id", "fixture_id"),
            ("--sensor-module-id", "sensor_module_id"), ("--sensor-mount-id", "sensor_mount_id"),
            ("--installation-orientation-id", "installation_orientation_id"),
            ("--reference-gravity-sign", "reference_gravity_sign"),
            ("--calibration-id", "calibration_id"), ("--firmware-build-id", "firmware_build_id"),
        ):
            add(flag, key)
        return argv

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _start_capture(self):
        try:
            argv = self._capture_argv()
        except ValueError as exc:
            messagebox.showerror("无法开始采集", str(exc), parent=self)
            return
        self.start_button.configure(state="disabled")
        self.stop_event = threading.Event()
        self.stop_button.configure(state="normal")
        self._append_log("\n" + "=" * 56 + "\n开始本次采集和自动分析\n")
        threading.Thread(target=self._worker, args=(argv, self.stop_event), daemon=True).start()

    def _request_stop(self):
        if self.stop_event is not None and not self.stop_event.is_set():
            self.stop_event.set()
            self.stop_button.configure(state="disabled")
            self._append_log("\n已请求强制结束：正在关闭串口，最多等待 1 秒。\n")

    def _on_close(self):
        if self.stop_event is None:
            self.destroy()
            return
        self._closing = True
        self._request_stop()

    def _worker(self, argv, stop_event):
        captured = {}
        writer = QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                code = recv.main(argv, result_out=captured, stop_event=stop_event)
            if stop_event.is_set():
                self.events.put(("cancelled", None))
                return
            if code != 0 or not captured.get("path"):
                raise RuntimeError("采集未成功完成（退出码 %s）" % code)
            result = analyse_capture(captured["path"])
            self.events.put(("done", result))
        except Exception:
            self.events.put(("error", traceback.format_exc()))

    def _drain_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind == "done":
                    self.current_result = value
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.stop_event = None
                    self._append_log("\n采集与自动分析完成。\n")
                    self._show_results(value)
                elif kind == "cancelled":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.stop_event = None
                    self._append_log("\n本次采集已强制结束；串口已释放，可立即再次测试。\n")
                    if self._closing:
                        self.destroy()
                        return
                elif kind == "error":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.stop_event = None
                    self._append_log("\n[失败]\n" + value + "\n")
                    if self._closing:
                        self.destroy()
                        return
                    messagebox.showerror("采集或分析失败", "请查看“采集与日志”页的详细错误。", parent=self)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _show_results(self, result):
        window = tk.Toplevel(self)
        window.title("本次采集分析结果")
        window.geometry("1080x800")
        book = ttk.Notebook(window)
        book.pack(fill="both", expand=True, padx=8, pady=8)
        summary = ttk.Frame(book, padding=6)
        chart = ttk.Frame(book, padding=6)
        review = ttk.Frame(book, padding=10)
        book.add(summary, text="分析结论")
        book.add(chart, text="图表")
        if result["meta"].get("data_role") == "formal":
            book.add(review, text="正式数据质检")

        report = make_report_text(result)
        text = ScrolledText(summary, wrap="word", font=("Consolas", 10))
        text.insert("1.0", report)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

        figure = build_dashboard(result)
        canvas = FigureCanvasTkAgg(figure, master=chart)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        image_path = OUTPUT_DIR / (Path(result["path"]).stem + "_analysis.png")
        figure.savefig(image_path, dpi=140)
        ttk.Label(chart, text="图已保存：%s" % image_path).pack(anchor="w", pady=(5, 0))
        ttk.Button(chart, text="在资源管理器中打开图表", command=lambda: os.startfile(str(image_path))).pack(
            anchor="w", pady=5)

        if result["meta"].get("data_role") == "formal":
            ttk.Label(review, text="自动检查只覆盖通信与数据完整性；工况是否真实、设备是否位移、标签是否可信必须人工确认。",
                      wraplength=900).pack(anchor="w", pady=(0, 12))
            controls = ttk.Frame(review)
            controls.pack(anchor="w", fill="x")
            state = tk.StringVar(value="pending")
            reason = tk.StringVar(value="")
            ttk.Label(controls, text="质检结论").grid(row=0, column=0, padx=4, pady=4, sticky="w")
            ttk.Combobox(controls, textvariable=state, values=metadata.QUALITY_STATUSES,
                         state="readonly", width=14).grid(row=0, column=1, padx=4, pady=4)
            ttk.Label(controls, text="原因/说明").grid(row=1, column=0, padx=4, pady=4, sticky="w")
            ttk.Entry(controls, textvariable=reason, width=80).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
            controls.columnconfigure(1, weight=1)

            def save_review():
                try:
                    update_manifest_quality(result["path"], state.get(), reason.get())
                    messagebox.showinfo("已更新", "manifest.csv 已更新为 %s。" % state.get(), parent=window)
                except Exception as exc:
                    messagebox.showerror("未更新", str(exc), parent=window)
            ttk.Button(review, text="保存质检结论到 manifest", command=save_review).pack(anchor="w", pady=8)


def main():
    app = CaptureApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
