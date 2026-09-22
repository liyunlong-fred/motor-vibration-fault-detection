# 03_Python工具\py_common\frames.py
"""
功能: 与固件 link_frame.c 一一对应的帧协议实现(协议唯一定义处)
帧格式(小端):
    偏移 0    2 byte   帧头 0x5A 0x5A
    偏移 2    1 byte   类型 1 = 单轴加速度样本块
    偏移 3    1 byte   轴号 'X'/'Y'/'Z'
    偏移 4    2 byte   窗序号 seq
    偏移 6    2 byte   样本数 n
    偏移 8    1 byte   量程码 AFS_SEL (0=±2g 1=±4g 2=±8g 3=±16g)
    偏移 9   2n byte   原始数据 int16 小端
整条链路只传 int16 原始计数, 换算成 g 只在本文件 to_g() 里做
"""
import numpy as np

HEAD       = b"\x5a\x5a"      # 帧头字节（b代表字节串）
HEAD0      = 0x5A
HEAD1      = 0x5A
TYPE_ACCEL = 1                # 类型码: 加速度样本块
OVERHEAD   = 9                # 数据区之前的固定开销(字节)
FS_HZ      = 1000             # 采样率（Hz）
MAX_N      = 1024             # 单帧最大样本数
AXIS_OK    = (ord("X"), ord("Y"), ord("Z"))                     # ord：把单字符转换成ASCII码    # 元组（只读数组）
SENS       = {0: 16384.0, 1: 8192.0, 2: 4096.0, 3: 2048.0}      # 量程码 -> 灵敏度(格/g)        # 字典：{键：值}
AFS_NAME   = {0: "+/-2g", 1: "+/-4g", 2: "+/-8g", 3: "+/-16g"}  # 量程码 -> 量程名称

TYPE_TEXT  = 2                # 新增: 文本日志行
TEXT_MAX   = 96               # 必须与固件 LINK_TEXT_MAX 一致
AXIS_TEXT  = "T"              # 文本帧在 Python 侧统一贴这个轴号

def find_head(buf, start=0):
    """在字节流里找帧头（从头开始）, 返回下标; 没找到返回 -1"""
    return buf.find(HEAD, start)

def parse_frame(buf, pos=0):
    """尝试解析 buf[pos:] 处的一帧
    返回 (status, frame, used):
        "ok"   : 解析成功, frame 为字典, used 为本帧总字节数
        "more" : 数据还不够一帧, 需要继续接收
        "bad"  : 此处不是合法帧(数据里恰好出现的假帧头), 调用者应跳过 1 字节重找
    """
    if len(buf) - pos < OVERHEAD:
        return ("more", None, 0)
    if buf[pos] != HEAD0 or buf[pos + 1] != HEAD1:
        return ("bad", None, 0)

    ftype    = buf[pos + 2]
    axis     = buf[pos + 3]
    seq      = buf[pos + 4] | (buf[pos + 5] << 8)          # 小端: 低字节在前
    cnt      = buf[pos + 6] | (buf[pos + 7] << 8)
    afs_code = buf[pos + 8]

    if ftype == TYPE_ACCEL:                             # 类型 1: 加速度样本块
        if (axis not in AXIS_OK) or (cnt < 1) or (cnt > MAX_N) or (afs_code not in SENS):
            return ("bad", None, 0)
        payload = 2 * cnt                               # 每样本 2 字节
    elif ftype == TYPE_TEXT:                            # 类型 2: 文本日志行
        if (cnt < 1) or (cnt > TEXT_MAX):
            return ("bad", None, 0)
        payload = cnt                                   # 文本是 1 字节 1 个字符
    else:                                               # 类型不认识: 当假帧头处理
        return ("bad", None, 0)

    total = OVERHEAD + payload                          # 计算帧长

    if len(buf) - pos < total:
        return ("more", None, 0)                        # 剩余字节不够一整帧

    # buf[]——对buf的数据部分切片，bytes()——转化成只读的字节
    # xx.frombuffer(xxx, dtype="xxx")——按指定格式解释成数组，"<i2"——小端、有符号整数、两字节
    # 将buf的 “数据部分” 按 “小端、有符号整数、两字节” 解释成数组，存入 data
    body = bytes(buf[pos + OVERHEAD: pos + total])

    if ftype == TYPE_ACCEL:
        frame = {"type": ftype, "axis": chr(axis), "seq": seq, "n": cnt,
                 "afs_code": afs_code, "data": np.frombuffer(body, dtype="<i2"),
                 "length": total}
    else:
        frame = {"type": ftype, "axis": AXIS_TEXT, "seq": seq, "n": cnt,
                 "afs_code": 0, "text": body.decode("gbk", "replace"),
                 "length": total}

    return ("ok", frame, total)                         # 返回将帧按协议切分好的字典

def to_g(data, afs_code):
    """int16 原始计数 -> g; PC 端唯一做真实值换算的地方"""
    if afs_code not in SENS:
        raise ValueError("未知量程码: %r" % (afs_code,))
    return np.asarray(data, dtype=np.float64) / SENS[afs_code]