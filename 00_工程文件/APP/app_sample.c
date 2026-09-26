#include "app_sample.h"
#include <math.h>

#define APP_SLOT_INVALID 0xFFU

typedef enum
{
    APP_SLOT_FREE = 0,
    APP_SLOT_FILLING,
    APP_SLOT_READY,
    APP_SLOT_PROCESSING
} app_slot_state_t;

static TIM_HandleTypeDef g_tim_handle;
static volatile uint16_t g_pending_ticks;
static sample_window_t g_win[APP_WINDOW_SLOT_COUNT];
static app_slot_state_t g_slot_state[APP_WINDOW_SLOT_COUNT];
static uint8_t g_ready_q[APP_WINDOW_SLOT_COUNT];
static uint8_t g_ready_head;
static uint8_t g_ready_tail;
static uint8_t g_ready_count;
static uint8_t g_fill;
static uint8_t g_processing = APP_SLOT_INVALID;
static uint16_t g_widx;
static uint16_t g_seq;
static uint32_t g_next_sample_id;
static app_sample_stats_t g_stats;

void APP_TIM_IRQHandler(void)
{
    HAL_TIM_IRQHandler(&g_tim_handle);
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == APP_TIM)
    {
        if (g_pending_ticks != 0xFFFFU) g_pending_ticks++;
    }
}

void app_sample_init(void)
{
    uint8_t i;

    for (i = 0U; i < APP_WINDOW_SLOT_COUNT; i++) g_slot_state[i] = APP_SLOT_FREE;
    g_slot_state[0] = APP_SLOT_FILLING;
    g_ready_head = 0U;
    g_ready_tail = 0U;
    g_ready_count = 0U;
    g_fill = 0U;
    g_processing = APP_SLOT_INVALID;
    g_widx = 0U;
    g_seq = 0U;
    g_next_sample_id = 0U;
    g_pending_ticks = 0U;

    APP_TIM_CLK_ENABLE();
    g_tim_handle.Instance = APP_TIM;
    g_tim_handle.Init.Prescaler = APP_TIM_CLK_HZ / 1000000U - 1U;
    g_tim_handle.Init.CounterMode = TIM_COUNTERMODE_UP;
    g_tim_handle.Init.Period = 1000000U / APP_FS_HZ - 1U;
    g_tim_handle.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    g_tim_handle.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    HAL_TIM_Base_Init(&g_tim_handle);
    __HAL_TIM_CLEAR_FLAG(&g_tim_handle, TIM_FLAG_UPDATE);
    HAL_NVIC_SetPriority(APP_TIM_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(APP_TIM_IRQn);
    HAL_TIM_Base_Start_IT(&g_tim_handle);
}

uint8_t app_source_read(mpu6050_raw_t *raw)
{
#if APP_USE_FAKE_ACCEL
    static uint32_t n = 0U;
    float t = (float)n / (float)APP_FS_HZ;
    float fx = APP_FAKE_A0_G * sinf(APP_2PI * APP_FAKE_F0_HZ * t)
             + APP_FAKE_A1_G * sinf(APP_2PI * APP_FAKE_F1_HZ * t);

    raw->x = (int16_t)(fx * MPU6050_ACCEL_SENS);
    raw->y = (int16_t)(APP_FAKE_Y_G * MPU6050_ACCEL_SENS);
    raw->z = 0;
    n++;
    return 0;
#else
    return mpu6050_read_raw(raw);
#endif
}

static uint8_t app_find_free_slot(void)
{
    uint8_t i;
    for (i = 0U; i < APP_WINDOW_SLOT_COUNT; i++)
    {
        if (g_slot_state[i] == APP_SLOT_FREE) return i;
    }
    return APP_SLOT_INVALID;
}

static void app_discard_partial_window(void)
{
    g_widx = 0U;
    g_next_sample_id++;       /* explicit gap marker; never claim continuity after loss */
    g_stats.continuity_breaks++;
}

static void app_push_sample(const mpu6050_raw_t *r)
{
    sample_window_t *w = &g_win[g_fill];
    uint8_t next_fill;

    if (g_widx == 0U) w->first_sample_id = g_next_sample_id;
    w->x[g_widx] = r->x;
    w->y[g_widx] = r->y;
    w->z[g_widx] = r->z;
    g_widx++;
    g_next_sample_id++;
    g_stats.samples_captured++;

    if (g_widx < APP_FRAME_N) return;

    w->n = APP_FRAME_N;
    w->seq = ++g_seq;
    next_fill = app_find_free_slot();
    if (next_fill == APP_SLOT_INVALID)
    {
        /* All other slots are READY/PROCESSING. Drop this full window rather
         * than overwrite consumer-owned memory, then expose a continuity gap. */
        g_stats.window_drop++;
        app_discard_partial_window();
        return;
    }

    g_slot_state[g_fill] = APP_SLOT_READY;
    g_ready_q[g_ready_head] = g_fill;
    g_ready_head = (uint8_t)((g_ready_head + 1U) % APP_WINDOW_SLOT_COUNT);
    g_ready_count++;
    g_fill = next_fill;
    g_slot_state[g_fill] = APP_SLOT_FILLING;
    g_widx = 0U;
}

void app_sample_task(void)
{
    uint16_t due;

    if (g_pending_ticks == 0U) return;
    __disable_irq();
    due = g_pending_ticks;
    g_pending_ticks = 0U;
    __enable_irq();

#if APP_USE_FAKE_ACCEL
    while (due-- != 0U)
    {
        mpu6050_raw_t raw;
        if (app_source_read(&raw) == 0U) app_push_sample(&raw);
        else g_stats.iic_read_fail++;
    }
#else
    {
        mpu6050_raw_t raw[APP_FIFO_DRAIN_BATCH];
        uint16_t read = 0U;
        uint8_t rc;
        (void)due;
        rc = mpu6050_fifo_read_raw(raw, APP_FIFO_DRAIN_BATCH, &read);
        if (rc == 2U)
        {
            g_stats.fifo_overflow++;
            app_discard_partial_window();
            return;
        }
        if (rc != 0U)
        {
            g_stats.iic_read_fail++;
            return;
        }
        if (read > g_stats.max_fifo_batch) g_stats.max_fifo_batch = read;
        for (uint16_t i = 0U; i < read; i++) app_push_sample(&raw[i]);
    }
#endif
}

uint8_t app_sample_window_ready(void)
{
    return (g_ready_count != 0U) ? 1U : 0U;
}

const sample_window_t *app_sample_window_get(void)
{
    uint8_t slot;
    if ((g_processing != APP_SLOT_INVALID) || (g_ready_count == 0U)) return 0;
    slot = g_ready_q[g_ready_tail];
    g_ready_tail = (uint8_t)((g_ready_tail + 1U) % APP_WINDOW_SLOT_COUNT);
    g_ready_count--;
    g_slot_state[slot] = APP_SLOT_PROCESSING;
    g_processing = slot;
    return &g_win[slot];
}

void app_sample_window_release(void)
{
    if (g_processing == APP_SLOT_INVALID) return;
    g_slot_state[g_processing] = APP_SLOT_FREE;
    g_processing = APP_SLOT_INVALID;
}

uint32_t app_sample_count(void) { return g_stats.samples_captured; }
uint16_t app_sample_overrun(void) { return g_stats.window_drop; }
void app_sample_stats_get(app_sample_stats_t *out)
{
    if (out != 0) *out = g_stats;
}
