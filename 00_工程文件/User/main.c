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

int main(void)
{
    uint32_t last = 0, prev = 0;

    HAL_Init();
    sys_stm32_clock_init(336, 8, 2, 7);
    delay_init(168);
    usart_init(APP_UART_BAUD);

    app_sample_init();                          /* 起 1kHz 心跳 */

    APP_LOG("fs=%u Hz, N=%u, 数据源=%s\r\n", APP_FS_HZ, APP_FRAME_N,
            APP_USE_FAKE_ACCEL ? "合成信号(桩)" : "MPU6050");

    while (1)
    {
        app_sample_task();                      /* 到点采一个样本 */

        if (HAL_GetTick() - last >= 1000)       /* 每秒自检一次实际采样率 */
        {
            uint32_t now = app_sample_count();
            last += 1000;
            APP_LOG("1s 采到 %lu 点, 丢窗 %u\r\n",
                    (unsigned long)(now - prev), app_sample_overrun());
            prev = now;
        }

        if (app_sample_window_ready())          /* 攒满一窗就发出去 */
        {
            const sample_window_t *w = app_sample_window_get();

            app_sample_pause(1);                /* 发帧期间暂停采样 */
            link_frame_send(w, 'X');
            app_sample_pause(0);

            app_sample_window_release();
        }
    }
}

