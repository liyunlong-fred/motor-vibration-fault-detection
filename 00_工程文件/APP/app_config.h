#ifndef __APP_CONFIG_H
#define __APP_CONFIG_H

#include "stdio.h"          /* APP_LOG 用到的 printf 在这里声明 */
#include "stdint.h"

/* ================= 1、采样与窗 ================= */
#define APP_FS_HZ           1000U       /* 采样率: 1kHz */
#define APP_FRAME_N         1024U       /* 一窗/一帧的样本数 */

/* ================= 2、时基 TIM ================= */
#define APP_TIM                 TIM3
#define APP_TIM_IRQn            TIM3_IRQn
#define APP_TIM_IRQHandler      TIM3_IRQHandler
#define APP_TIM_CLK_ENABLE()    __HAL_RCC_TIM3_CLK_ENABLE()
#define APP_TIM_CLK_HZ          84000000U   /* APB1 定时器时钟 = 42MHz x2 */

/* ================= 3、数据源开关 ================= */
/* 1 = 使用合成信号（仅用于测试）
 * 0 = 使用MPU6050（真实数据） */
#define APP_USE_FAKE_ACCEL  0

/* ================= 4、测试信号参数 ================= */
#if APP_USE_FAKE_ACCEL                  /* 仅在测试阶段进行定义“测试信号参数” */

#define APP_2PI             6.28318531f
#define APP_FAKE_F0_HZ      45.0f       /* 主振动: 对应风扇 1x 基频 */
#define APP_FAKE_A0_G       0.05f       /* 主振动幅值 0.05g */
#define APP_FAKE_F1_HZ      90.0f       /* 二倍频 */
#define APP_FAKE_A1_G       0.01f       /* 二倍频幅值 0.01g */
#define APP_FAKE_Y_G        0.99f       /* 假装重力压在 Y 轴上 */

#endif

/* ================= 5、串口与调试 ================= */
#define APP_UART_BAUD       460800U

#define APP_DEBUG           1
#if APP_DEBUG
#define APP_LOG(...)        printf(__VA_ARGS__)
#else
#define APP_LOG(...)        ((void)0)
#endif

#endif

