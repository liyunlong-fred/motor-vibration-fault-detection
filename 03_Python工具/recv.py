# 03_Python工具\recv.py
"""
功能: 从串口接收固件发来的数据帧, 存成 CSV 到 04_数据集\raw\
用法: python recv.py     (运行前必须先关闭串口助手, 串口是独占资源)
"""
import os
import sys
import serial           # 串口所使用的库
import numpy as np
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_common"))   # 取得 frames.py 的路径，并将其插到搜索列表的最前面
import frames   # 导入 frames.py

# ------------------------- 配置 -------------------------
PORT        = "COM13"        # 板子所在的串口
BAUD        = 460800         # 波特率，必须与固件 APP_UART_BAUD 一致
SAVE_FRAMES = 20             # 收满多少帧后存盘
AXIS_EXPECT = "X"            # 期望测试 X 轴，固件 link_frame_send(w, '?')
TAG         = "fan9v_normal" # 本次采集工况: 风扇+电压+状态, 例如 fan9v_normal / fan6v_unbalance

PROJ    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 取得项目根目录
RAW_DIR = os.path.join(PROJ, "04_数据集", "raw")                         # 定义原始数据的存储路径

def main():
    if not os.path.isdir(RAW_DIR):  # 原始数据的目录如果不存在就创一个新的
        os.makedirs(RAW_DIR)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)  # 创建串口对象并打开，传入端口和波特率，超时返回（秒）
    except serial.SerialException as e:
        # 打印异常状态信息
        print("打开串口失败: %s" % e)
        print("排查: 1) 板子插好没  2) 串口助手是否还占着 %s  3) 端口号对不对" % PORT)
        return

    # 探索者板载 CH340 的“一键下载”电路: RTS->NRST, DTR->BOOT0。
    # 线状态若停在 DTR=0 / RTS=1, MCU 会被一直按在复位上, 一个字节都发不出来;
    # 而 pyserial 打开端口时不会主动驱动这两条线, 会沿用驱动里已有的状态,
    # 所以这里必须显式置 0（实测: DTR=0/RTS=1 收 0 字节, 其余三种组合都能收）。
    ser.dtr = False
    ser.rts = False

    ser.reset_input_buffer()    # 清空串口接收缓冲区
    print("已打开 %s @ %d, 目标 %d 帧, 按 Ctrl+C 可提前结束" % (PORT, BAUD, SAVE_FRAMES))

    buf      = bytearray()      # 接受缓冲，累积的原始字节流
    datas    = []               # 每帧的 int16 数组，收到一帧就追加一个数组
    axis     = None             # 轴号
    afs_code = 0                # 量程码
    seq_last = 0                # 上一帧的序号，用于检测丢帧
    lost     = 0                # 累计丢帧数

    stamp    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(PROJ, "06_笔记与踩坑", "%s_boardlog.txt" % stamp)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_fp   = open(log_path, "w", encoding="utf-8")

    try:
        
        while len(datas) < SAVE_FRAMES:             # 不断读串口数据，直到收取帧数大于指定的存盘帧数
            chunk = ser.read(ser.in_waiting or 1)   # 读取串口缓冲区全部字节, 缓冲区为空就阻塞等待 1 字节
            if chunk:
                buf += chunk                        # 将数据存到接收缓冲区

            while True:
                pos = frames.find_head(buf)         # 调用 frames.py 中找帧头的函数
                # ========删掉除完整帧以外的所有无用数据=========
                if pos < 0:                         # 如果缓冲区没有帧头
                    if len(buf) > 1:                # 如果缓冲区有数据
                        del buf[:len(buf) - 1]      # 删掉数据，只留最后 1 字节(可能是半个帧头)
                    break
                if pos > 0:
                    del buf[:pos]                   # 丢掉帧头之前的杂散字节
                # ============================================


                # ====解析帧：处理解析时的异常状态，成功则继续====
                status, f, used = frames.parse_frame(buf) # 将 “解析状态”、“帧字典”、“总帧长” 返回存入变量
                if status == "more":
                    break                           # 还不够一帧, 等下次 read
                if status == "bad":
                    del buf[0]                      # 假帧头, 跳过它继续找
                    continue

                del buf[:used]                      # 解析成功，取走并将其在缓冲区删除
                # ============================================


                if f["type"] == frames.TYPE_TEXT:       # 板上日志: 打印 + 落盘, 不当数据
                    line = f["text"].rstrip("\r\n")
                    print(line)
                    log_fp.write(line + "\n")
                    log_fp.flush()
                    continue                            # ★ 必须 continue: 否则日志的序号会被当成窗序号

                # =====处理帧：查询丢帧数、记录数据、打印进度=====
                if seq_last and f["seq"] != seq_last + 1:       # 判定是否丢帧：上一帧序号不为 0 且本帧不等于上一帧序号加 1
                    miss = f["seq"] - seq_last - 1              # 计算丢帧数
                    lost += miss
                    print("  !! 丢帧: 期望帧序号 seq=%d, 实收帧序号 %d (丢 %d 帧)"
                          % (seq_last + 1, f["seq"], miss))     # 打印丢帧信息
                
                seq_last = f["seq"]                             # 记录数据
                axis     = f["axis"]
                afs_code  = f["afs_code"]

                datas.append(f["data"])                         # 存储帧
                
                print("  接收进度 [%2d/%2d] 轴号 axis=%s 帧序号 seq=%d 此帧样本数 n=%d 量程码 afs_code=%d"
                      % (len(datas), SAVE_FRAMES, f["axis"], f["seq"], f["n"], f["afs_code"]))  # 打印进度和接收信息
                # ============================================
    except KeyboardInterrupt:
        print("\n[手动停止]")
    finally:
        if ser.is_open:         # 判断串口是否是打开状态
            ser.close()         # 关闭串口
            print("串口已关闭")
        
        log_fp.close()
        print("日志已保存: %s" % log_path)            

    if not datas:
        print("没有收到任何帧, 不保存")
        return

    if axis != AXIS_EXPECT:
        print("注意: 收到的是 %s 轴, 期望 %s 轴 —— 桩信号的振动在 X 轴, 发 Z 轴会全是 0"
              % (axis, AXIS_EXPECT))

    all_data  = np.concatenate(datas)           # 将 datas 首尾相接，拼成一个长数组
    first_seq = seq_last - len(datas) + 1       # 计算首帧序号
    path      = os.path.join(RAW_DIR, "%s_%s_%s_f%04d-%04d.csv" % (stamp, TAG, axis, first_seq, seq_last))

    with open(path, "w", encoding="utf-8") as fp:
        fp.write("# tag=%s axis=%s fs=%d afs_code=%d per_frame=%d frames=%d first_seq=%d last_seq=%d\n"
                 % (TAG, axis, frames.FS_HZ, afs_code, datas[0].size, len(datas), first_seq, seq_last))        
        np.savetxt(fp, all_data, fmt="%d")      # 存入指定文件，按整数格式

    print("-" * 56)
    print("共收到 %d 帧, 丢帧 %d" % (len(datas), lost))
    print("已保存: %s  (%d 个样本)" % (path, all_data.size))

# 可直接当工具运行：被直接运行时执行 main()，被别的文件导入时不会自己执行一遍 main()
if __name__ == "__main__":
    main()