#ifndef __APP_SAMPLE_H
#define __APP_SAMPLE_H

#include "app_config.h"
#include "./BSP/MPU6050/mpu6050.h"

typedef struct
{
    uint16_t seq;
    uint16_t n;
    uint32_t first_sample_id;   /* monotonically increasing capture id */
    int16_t  x[APP_FRAME_N];
    int16_t  y[APP_FRAME_N];
    int16_t  z[APP_FRAME_N];
} sample_window_t;

typedef struct
{
    uint32_t samples_captured;
    uint32_t continuity_breaks;
    uint16_t fifo_overflow;
    uint16_t iic_read_fail;
    uint16_t window_drop;
    uint16_t max_fifo_batch;
} app_sample_stats_t;

void app_sample_init(void);
void app_sample_task(void);             /* drain sensor FIFO into capture windows */

uint8_t                app_sample_window_ready(void);
const sample_window_t *app_sample_window_get(void);
void                   app_sample_window_release(void);

uint32_t app_sample_count(void);
uint16_t app_sample_overrun(void);
void     app_sample_stats_get(app_sample_stats_t *out);

/* Kept for synthetic-source tests and legacy callers. */
uint8_t app_source_read(mpu6050_raw_t *accel);

#endif
