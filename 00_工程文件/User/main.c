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

#if !APP_USE_FAKE_ACCEL                    /* 真传感器才需要 */
    iic_init();
    if (mpu6050_init() != 0)               /* mpu6050_init 返回 0 表示成功 */
    {
        APP_LOG("MPU6050 初始化失败!\r\n");
        while (1);                         /* 停在这里, 不要继续跑 */
    }
#endif

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
            link_frame_send(w, 'Z');
            app_sample_pause(0);

            app_sample_window_release();
        }

        // mpu6050_raw_t a, b, c;
        // uint8_t pm1 = 0, id = 0;

        // mpu6050_read_raw(&a);
        // mpu6050_read_raw(&b);
        // mpu6050_read_raw(&c);                                   /* 同一位置连读三次, 结果应几乎相同 */
        // iic_reg_read_length(MPU6050_ADDR, MPU6050_PWR_MGMT_1, &pm1, 1);
        // id = mpu6050_who_am_i();

        // printf("%6d %6d %6d | %6d %6d %6d | %6d %6d %6d | PWR=0x%02X ID=0x%02X\r\n",
        //    a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z, pm1, id);
        // delay_ms(50);
    }
}

