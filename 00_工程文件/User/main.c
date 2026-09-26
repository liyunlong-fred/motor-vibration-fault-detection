#include <math.h>
#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./USMART/usmart.h"
#include "./BSP/LED/led.h"
#include "./BSP/LCD/lcd.h"
#include "./BSP/IIC/iic.h"
#include "./BSP/MPU6050/mpu6050.h"
#include "./app_config.h"
#include "./app_sample.h"
#include "link_frame.h"
#include "dsp_fft.h"

int main(void)
{
    uint32_t last = 0;

    HAL_Init();
    sys_stm32_clock_init(336, 8, 2, 7);
    delay_init(168);
    usart_init(APP_UART_BAUD);
    app_sample_init();                      /* 起 1kHz 心跳 */
    dsp_fft_init();                         /* 算 Hann 窗表 + 初始化 1024 点 FFT 实例, 只调一次 */
    //dsp_fft_selftest();                     /* 板上造 45Hz/50mg + 90Hz/10mg, 对完答案就把这一行删掉 */

#if !APP_USE_FAKE_ACCEL                    /* 真传感器才需要 */
    iic_init();
    if (mpu6050_init() != 0)               /* mpu6050_init 返回 0 表示成功 */
    {
        APP_LOG("MPU6050 初始化失败!\r\n");
        while (1);                         /* 停在这里, 不要继续跑 */
    }
#endif

    

    APP_LOG("fs=%u Hz, N=%u, 数据源=%s\r\n", APP_FS_HZ, APP_FRAME_N,
            APP_USE_FAKE_ACCEL ? "合成信号(桩)" : "MPU6050");

    while (1)
    {
        
        app_sample_task();                      /* 到点采一个样本 */

        if (app_sample_window_ready())          /* 攒满一窗 */
        {
            const sample_window_t *w = app_sample_window_get();
            dsp_fft_result_t fft_res;
            uint32_t span_ticks;
            uint32_t missed_ticks;
            uint32_t boundary_gap;
            uint32_t read_fail;

            app_sample_pause(1);                /* 处理期间暂停采样, 保证窗内样本等间隔 */
            dsp_fft_run(w, 'X', &fft_res);      /* 先算 FFT(几百微秒) */
            dsp_fft_print(&fft_res);            /* 再打印(每窗 6 行, 几毫秒) */
            link_frame_send(w, 'X');            /* 原来的发帧照旧, 供 PC 对拍 */


            if (app_sample_timing_get(
                    &span_ticks,
                    &missed_ticks,
                    &boundary_gap,
                    &read_fail) != 0)
            {
                APP_LOG(
                    "TIM seq=%u span=%lu miss=%lu gap=%lu readfail=%lu",
                    (unsigned)w->seq,
                    (unsigned long)span_ticks,
                    (unsigned long)missed_ticks,
                    (unsigned long)boundary_gap,
                    (unsigned long)read_fail);
            }
            else
            {
                APP_LOG("TIM seq=%u unavailable", (unsigned)w->seq);
            }

            app_sample_pause(0);

            app_sample_window_release();
        }    
    }
}

