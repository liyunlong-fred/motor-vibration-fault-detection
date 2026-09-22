#ifndef __LINK_FRAME_H
#define __LINK_FRAME_H

#include "app_config.h"
#include "app_sample.h"

/* ============================== 帧格式 =================================
 *  偏移   长度（字节）         字段说明
 *   0        2       帧头: 0x5A 0x5A
 *   2        1       类型: 1 = 单轴加速度样本块; 2 = 日志
 *   3        1       轴号: 'X'(0x58) / 'Y'(0x59) / 'Z'(0x5A)
 *   4        2       窗序号 seq      (小端: 低字节在前)
 *   6        2       样本数 n        (小端)
 *   8        1       量程码 AFS_SEL  (0=±2g  1=±4g  2=±8g  3=±16g)
 *   9       2n       原始数据: int16 计数, 小端, 每样本低字节在前
 * -----------------------------------------------------------------------
 *  一帧总长 = 9 + 2n, n = 1024 时 = 2057 字节
 *  整条链路只传 int16 原始计数; PC 端显示/做 FFT 需要先按量程码换算成真实值:
 *      真实加速度(g) = 原始计数 ÷ 灵敏度
 *      量程码 0 → 16384.0   1 → 8192.0   2 → 4096.0   3 → 2048.0  (格/g)
 * ======================================================================= */
/* 数据帧 */
#define LINK_FRAME_HEAD         0x5A5A                                      /* 帧头固定为 0x5A5A */
#define LINK_FRAME_TYPE_ACCEL   1U                                          /* 数据为加速度 */
#define LINK_FRAME_OVERHEAD     9U                                          /* 样本数据的帧偏移 */
#define LINK_FRAME_MAX_LEN      (LINK_FRAME_OVERHEAD + 2U * APP_FRAME_N)    /* 帧总长 */

/* 日志帧 */
#define LINK_FRAME_TYPE_TEXT    2U                          /* 类型 2 = 文本日志行 */
#define LINK_TEXT_MAX           96U                         /* 一条日志最多 96 字节(必须与 PC 端一致) */

/* 量程码：直接取 mpu6050.h 中的 AFS_SEL 配置，保证与传感器实际量程同步 */
#define LINK_ACCEL_FS_CODE      MPU6050_ACCEL_FS_SEL

/* ================数据帧================ */
/**
 * @brief       按上述帧格式打包一窗数据；纯软件操作，不涉及硬件，可在 PC 端复用同一份逻辑
 * @param       w    ：待打包的一窗数据地址（只读）
 * @param       axis ：轴号，'X' / 'Y' / 'Z'
 * @param       out  ：输出缓冲区地址，容量不得小于 LINK_FRAME_MAX_LEN
 * @retval      帧总长度（字节）= 9 + 2n
 */
uint16_t link_frame_pack(const sample_window_t *w, uint8_t axis, uint8_t *out);

/**
 * @brief       打包一窗数据并通过串口1发出（阻塞式，115200 下发完一帧约 180ms）
 * @param       w    ：待发送的一窗数据地址（只读）
 * @param       axis ：轴号，'X' / 'Y' / 'Z'
 * @retval      0, 成功; 1, 失败
 */
uint8_t  link_frame_send(const sample_window_t *w, uint8_t axis);


/* ================日志帧================ */
/**
 * @brief       把一段 ASCII 文本打包成 type=2 的文本帧
 * @param       s   : 以 '\0' 结尾的字符串(只读)
 * @param       out : 输出缓冲区, 容量不得小于 LINK_FRAME_OVERHEAD + LINK_TEXT_MAX
 * @retval      帧总长度 = 9 + n; 参数非法时返回 0
 */
uint16_t link_text_pack(const char *s, uint8_t *out);

/**
 * @brief       打包一条日志并通过串口1发出
 * @param       s : 以 '\0' 结尾的字符串(只读)
 * @retval      0, 成功; 1, 失败
 */
uint8_t  link_text_send(const char *s);

#endif
