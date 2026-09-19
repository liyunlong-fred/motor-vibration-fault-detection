#ifndef __APP_SAMPLE_H
#define __APP_SAMPLE_H

#include "app_config.h"
#include "./BSP/MPU6050/mpu6050.h"

/* 一窗数据: 直接存传感器原始计数(int16), 与帧格式一致, 打包时不用再换算 */
typedef struct
{
    uint16_t seq;                   /* 窗序号, 从 1 开始, 用于 PC 端查丢帧 */
    uint16_t n;                     /* 本窗有效样本数(= APP_FRAME_N) */
    int16_t  x[APP_FRAME_N];
    int16_t  y[APP_FRAME_N];
    int16_t  z[APP_FRAME_N];
} sample_window_t;

/* ---- 生命周期: 主循环里调用 ---- */
void app_sample_init(void);             /* 启动 1kHz 时基 */
void app_sample_task(void);             /* 反复调用: 到点就采一个样本 */

/* ---- 双缓冲: 生产者(中断/任务) 与 消费者(主循环) 的交接 ---- */
uint8_t                app_sample_window_ready(void);    /* 1 = 有满窗待取 */
const sample_window_t *app_sample_window_get(void);      /* 取指针, 只读 */
void                   app_sample_window_release(void);  /* 用完归还 */

/* ---- 运行统计(自检用) ---- */
uint32_t app_sample_count(void);        /* 开机至今累计采样点数 */
uint16_t app_sample_overrun(void);      /* 因主循环来不及取而丢掉的窗数 */

/* ---- 采样期间暂停(发帧时用, 保证窗内样本等间隔) ---- */
void app_sample_pause(uint8_t on);

/* ---- 数据源: 内部按 APP_USE_FAKE_ACCEL 选择真/假 ---- */
uint8_t app_source_read(mpu6050_raw_t *accel);   /* 0=成功 */

#endif

