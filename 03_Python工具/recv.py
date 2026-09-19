# 03_Python工具\recv.py
"""
功能: 从串口接收固件发来的数据帧, 存成 CSV 到 04_数据集\raw\
用法: python recv.py     (运行前必须先关闭串口助手, 串口是独占资源)
"""
import os
import sys
import serial
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_common"))
import frames

# ------------------------- 配置 -------------------------
PORT        = "COM13"       # 板子所在的串口
BAUD        = 460800        # 必须与固件 APP_UART_BAUD 一致
SAVE_FRAMES = 20            # 收满多少帧后存盘
AXIS_EXPECT = "X"           # 测试 X 轴，固件 link_frame_send(w, 'X')

PROJ    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJ, "04_数据集", "raw")

def main():
    if not os.path.isdir(RAW_DIR):
        os.makedirs(RAW_DIR)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
    except serial.SerialException as e:
        print("打开串口失败: %s" % e)
        print("排查: 1) 板子插好没  2) 串口助手是否还占着 %s  3) 端口号对不对" % PORT)
        return

    ser.reset_input_buffer()
    print("已打开 %s @ %d, 目标 %d 帧, 按 Ctrl+C 可提前结束" % (PORT, BAUD, SAVE_FRAMES))

    buf      = bytearray()      # 累积的原始字节流
    datas    = []               # 每帧的 int16 数组
    axis     = None
    afs_code = 0
    seq_last = 0
    lost     = 0

    try:
        while len(datas) < SAVE_FRAMES:
            chunk = ser.read(ser.in_waiting or 1)   # 有多少读多少, 没有就等 1 字节
            if chunk:
                buf += chunk

            while True:
                pos = frames.find_head(buf)
                if pos < 0:
                    if len(buf) > 1:
                        del buf[:len(buf) - 1]      # 只留最后 1 字节(可能是半个帧头)
                    break
                if pos > 0:
                    del buf[:pos]                   # 丢掉帧头之前的杂散字节

                status, f, used = frames.parse_frame(buf)
                if status == "more":
                    break                           # 还不够一帧, 等下次 read
                if status == "bad":
                    del buf[0]                      # 假帧头, 跳过它继续找
                    continue

                del buf[:used]

                if seq_last and f["seq"] != seq_last + 1:
                    miss = f["seq"] - seq_last - 1
                    lost += miss
                    print("  !! 丢帧: 期望 seq=%d, 实收 %d (丢 %d 帧)"
                          % (seq_last + 1, f["seq"], miss))
                seq_last = f["seq"]
                axis     = f["axis"]
                afs_code  = f["afs_code"]
                datas.append(f["data"])
                print("  [%2d/%2d] axis=%s seq=%d n=%d afs_code=%d"
                      % (len(datas), SAVE_FRAMES, f["axis"], f["seq"], f["n"], f["afs_code"]))
    except KeyboardInterrupt:
        print("\n[手动停止]")
    finally:
        if ser.is_open:
            ser.close()
            print("串口已关闭")

    if not datas:
        print("没有收到任何帧, 不保存")
        return

    if axis != AXIS_EXPECT:
        print("注意: 收到的是 %s 轴, 期望 %s 轴 —— 桩信号的振动在 X 轴, 发 Z 轴会全是 0"
              % (axis, AXIS_EXPECT))

    all_data  = np.concatenate(datas)
    first_seq = seq_last - len(datas) + 1
    path      = os.path.join(RAW_DIR, "%s_%04d_%04d.csv" % (axis, first_seq, seq_last))

    with open(path, "w", encoding="utf-8") as fp:
        fp.write("# axis=%s fs=%d afs_code=%d per_frame=%d frames=%d first_seq=%d last_seq=%d\n"
                 % (axis, frames.FS_HZ, afs_code, datas[0].size, len(datas), first_seq, seq_last))
        np.savetxt(fp, all_data, fmt="%d")

    print("-" * 56)
    print("共收到 %d 帧, 丢帧 %d" % (len(datas), lost))
    print("已保存: %s  (%d 个样本)" % (path, all_data.size))

if __name__ == "__main__":
    main()