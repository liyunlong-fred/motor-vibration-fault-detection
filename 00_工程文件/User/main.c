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
#include "./app_calibration.h"
#include "./app_sample.h"
#include "link_frame.h"
#include "dsp_fft.h"

#if APP_CALIBRATION_MEAN_LOG
static int32_t window_mean_counts(const int16_t *data, uint16_t n)
{
    int32_t sum = 0;
    uint16_t i;

    if ((data == 0) || (n == 0U)) return 0;
    for (i = 0U; i < n; i++) sum += data[i];
    return sum / (int32_t)n;
}

static void print_calibration_means(const sample_window_t *w)
{
    if ((w == 0) || (w->n == 0U)) return;

    APP_LOG("CAL_MEAN seq=%u first=%lu n=%u x=%ld y=%ld z=%ld\r\n",
            (unsigned)w->seq,
            (unsigned long)w->first_sample_id,
            (unsigned)w->n,
            (long)window_mean_counts(w->x, w->n),
            (long)window_mean_counts(w->y, w->n),
            (long)window_mean_counts(w->z, w->n));
}
#endif

int main(void)
{
    uint16_t windows_since_stats = 0U;

    HAL_Init();
    sys_stm32_clock_init(336, 8, 2, 7);
    delay_init(168);
    usart_init(APP_UART_BAUD);
    app_sample_init();
    dsp_fft_init();

#if !APP_USE_FAKE_ACCEL
    iic_init();
    if (mpu6050_init() != 0)
    {
        APP_LOG("MPU6050 init failed\r\n");
        while (1) {}
    }
#endif

    APP_LOG("capture=fifo_continuous fs=%u N=%u\r\n", APP_FS_HZ, APP_FRAME_N);

    while (1)
    {
        const sample_window_t *w;
        app_sample_task();

        if (!app_sample_window_ready()) continue;
        w = app_sample_window_get();
        if (w == 0) continue;

        {
            dsp_fft_result_t fft_res;
            dsp_fft_run(w, 'X', &fft_res);

#if APP_CALIBRATION_MEAN_LOG
            print_calibration_means(w);
#endif

            /* Copy the raw window into the DMA-owned queue before release. */
            (void)link_frame_send(w, 'X');
#if APP_DEBUG && APP_FFT_VERBOSE
            dsp_fft_print(&fft_res);
#endif
        }
        app_sample_window_release();

        windows_since_stats++;
        if (windows_since_stats >= 20U)
        {
            app_sample_stats_t stats;
            app_sample_stats_get(&stats);
            APP_LOG("CAP samples=%lu break=%lu fifo_ovf=%u iic_fail=%u win_drop=%u tx_drop=%u tx_err=%u batch=%u\r\n",
                    (unsigned long)stats.samples_captured,
                    (unsigned long)stats.continuity_breaks,
                    (unsigned)stats.fifo_overflow,
                    (unsigned)stats.iic_read_fail,
                    (unsigned)stats.window_drop,
                    (unsigned)usart_tx_dropped(),
                    (unsigned)usart_tx_errors(),
                    (unsigned)stats.max_fifo_batch);
            windows_since_stats = 0U;
        }
    }
}
