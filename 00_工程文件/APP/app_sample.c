#include "app_sample.h"
#include <math.h>                      /* 使用了库中的sinf——单浮点精度正弦函数 */

/* ================= 内部状态 ================= */
static TIM_HandleTypeDef g_tim_handle;          /* TIM配置信息 */
static volatile uint8_t  g_tick    = 0;         /* 1kHz 心跳标志 */
static volatile uint8_t  g_paused  = 0;         /* 1=暂停采样(发帧期间) */

static sample_window_t   g_win[2];              /* 双缓冲 */
static volatile uint8_t  g_fill    = 0;         /* 正在写的那一半 */
static volatile uint8_t  g_ready   = 0xFF;      /* 已填满待取的那一半, 0xFF=已被取走 */
static volatile uint16_t g_widx    = 0;         /* 当前窗已写样本数 */
static volatile uint32_t g_count   = 0;         /* 累计采样点数 */
static volatile uint16_t g_overrun = 0;         /* 丢窗计数 */
static volatile uint16_t g_seq     = 0;         /* 窗序号 */

/* ================= 临时测量计数器 ================= */
static volatile uint32_t g_tim_irq_total = 0;
static volatile uint32_t g_read_fail_total = 0;

static volatile uint32_t g_win_first_tick = 0;
static volatile uint32_t g_win_last_tick = 0;
static volatile uint32_t g_prev_win_last_tick = 0;
static volatile uint32_t g_win_read_fail_begin = 0;

static volatile uint32_t g_report_span_ticks = 0;
static volatile uint32_t g_report_missed_ticks = 0;
static volatile uint32_t g_report_boundary_gap = 0;
static volatile uint32_t g_report_read_fail = 0;
static volatile uint8_t  g_report_ready = 0;

/* ================= 1、TIM、中断配置 ================= */
/**
 * @brief       配置中断服务函数，指向HAL库的公共处理函数
 * @param       无
 * @retval      无
 */
void APP_TIM_IRQHandler(void)
{
    HAL_TIM_IRQHandler(&g_tim_handle);
}

/**
 * @brief       HAL 的更新中断回调: 这里只置标志, 处理在主循环中
 * @param       htim（handle TIM）：TIM句柄的指针，内部保存句柄的地址
 * @retval      无
 */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == APP_TIM)      /* 确保溢出的TIM为采样所使用的TIM */
    {
        g_tim_irq_total++;
        g_tick = 1;                     /* 标志位置1，处理留给main函数 */
    }
}

/**
 * @brief       采样初始化：配置TIM，使能中断，启动TIM
 * @param       无
 * @retval      无
 */
void app_sample_init(void)
{
    APP_TIM_CLK_ENABLE();       /* 开启TIM时钟（未开启无法写入寄存器） */

    g_tim_handle.Instance           = APP_TIM;                              /* 在app_config.h中定义所使用的TIM */
    g_tim_handle.Init.Prescaler     = APP_TIM_CLK_HZ / 1000000U - 1U;       /* 84-1 -> 1MHz */
    g_tim_handle.Init.CounterMode   = TIM_COUNTERMODE_UP;                   /* 向上计数模式 */
    g_tim_handle.Init.Period        = 1000000U / APP_FS_HZ - 1U;            /* 计算分频系数1000-1 -> 1kHz */
    g_tim_handle.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;               /* 采样时钟分频系数使用DIV1 */
    g_tim_handle.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;   /* 不自动装载分频系数（更改Period立刻生效） */
    HAL_TIM_Base_Init(&g_tim_handle);                                       /* 将配置写入对应寄存器 */

    __HAL_TIM_CLEAR_FLAG(&g_tim_handle, TIM_FLAG_UPDATE);                   /* 启动先将标志位清零 */
    HAL_NVIC_SetPriority(APP_TIM_IRQn, 2, 0);                               /* 设置中断优先级（越小越高）：抢占优先级——2；响应优先级——0 */
    HAL_NVIC_EnableIRQ(APP_TIM_IRQn);                                       /* 中断信号使能 */
    HAL_TIM_Base_Start_IT(&g_tim_handle);                                   /* 启动TIM，并允许更新中断 */
}

/* ================= 2、 数据源: 实际 / 模拟 ================= */
/**
 * @brief       将选定数据源传入raw指向的结构体中：实际————直接传入MPU6050测量值，模拟————传入通过sin函数模拟出测试信号（参数写在app.config.h中）
 *              注意：调用一次只传入 ！一组！ 三轴加速度值，即进行一次采样，此函数每秒要进行数值为“采样频率”次数的调用
 * @param       raw：mpu6050所测加速度的存储地址
 * @retval      0, 成功; 1, 失败
 */
uint8_t app_source_read(mpu6050_raw_t *raw)
{
#if APP_USE_FAKE_ACCEL
    static uint32_t n = 0;                          /* 样本序号 = 假时间轴 */
    float t = (float)n / (float)APP_FS_HZ;          /* 模拟时域信号的自变量时间 t ：[样本序号（第几次采样）n] * [采样频率的倒数（一次采样所需时间）] */
    float fx, fy;                                   /* fx为 x 轴上模拟的风扇震动加速度，fy为 y 轴上的重力加速度（单位均为 g ） */

    /* 以设定的频率，计算模拟信号的时域函数（单位为g） */
    fx = APP_FAKE_A0_G * sinf(APP_2PI * APP_FAKE_F0_HZ * t)   /* 主频分量：  频率为APP_FAKE_F0_HZ */
       + APP_FAKE_A1_G * sinf(APP_2PI * APP_FAKE_F1_HZ * t);  /* 二倍频分量：频率为APP_FAKE_F1_HZ */
    fy = APP_FAKE_Y_G;                                        /* 假定重力加速度压在 Y 轴上 */
    
    /* 将单位从单浮点精度的g，转换成16位整型，方便传输（与传感器的原始数据保持一致） */
    raw -> x = (int16_t)(fx * MPU6050_ACCEL_SENS);
    raw -> y = (int16_t)(fy * MPU6050_ACCEL_SENS);
    raw -> z = 0;

    n++;
    return 0;
#else
    return mpu6050_read_raw(raw);               /* 传感器数据走这里，直接原始数据 */
#endif
}

/* ================= 3、 主循环任务 ================= */
/**
 * @brief       
 * @param       
 * @retval      
 */
void app_sample_task(void)
{
    mpu6050_raw_t  r;             /* 类型：结构体变量，用于接收传感器读取数据 */
    sample_window_t *w;             /* 类型：指针，存放一窗数据的地址 */
    uint32_t service_tick;

    if (!g_tick)   return;          /* 没到 1ms, 立刻返回 */
    g_tick = 0;                     /* 下一窗数据开始，先进行标志位清零 */
    if (g_paused)  return;          /* 发帧期间不采集样本, 保证窗内样本等间隔 */

    service_tick = g_tim_irq_total;

    if (app_source_read(&r) != 0)
    {
        g_read_fail_total++;
        return;
    }

    w = &g_win[g_fill];     /* 将双缓冲中正在写的那一窗的结构体取地址赋给 w */
    if (g_widx == 0)
    {
        g_win_first_tick = service_tick;
        g_win_read_fail_begin = g_read_fail_total;

        if (g_prev_win_last_tick != 0)
        {
            g_report_boundary_gap =
                g_win_first_tick - g_prev_win_last_tick - 1U;
        }
        else
        {
            g_report_boundary_gap = 0;
        }
    }
    w->x[g_widx] = r.x;     /* g -> 原始计数 */
    w->y[g_widx] = r.y;
    w->z[g_widx] = r.z;
    g_widx++;
    g_count++;

    if (g_widx >= APP_FRAME_N)      /* 一个窗口 */
    {
        g_win_last_tick = service_tick;

        g_report_span_ticks =
            g_win_last_tick - g_win_first_tick;

        if (g_report_span_ticks >= (APP_FRAME_N - 1U))
        {
            /* 总漏节拍 = 窗口内节拍间隔数 - 理想间隔数。 */
            g_report_missed_ticks =
                g_report_span_ticks - (APP_FRAME_N - 1U);
        }
        else
        {
            g_report_missed_ticks = 0;
        }

        g_report_read_fail =
            g_read_fail_total - g_win_read_fail_begin;

        g_prev_win_last_tick = g_win_last_tick;
        g_report_ready = 1;

        w->n   = APP_FRAME_N;
        w->seq = ++g_seq;

        if (g_ready != 0xFF)        /* 上一窗还没被取走 */
        {
            g_overrun++;
        }
        g_ready = g_fill;           /* 交出满窗 */
        g_fill ^= 1;                /* 0与1来回切换，意思是换另一半继续写 */
        g_widx  = 0;                /* 将当前窗已采样数清零 */
    }
}

/* ================= 4、 对外接口 ================= */
//正常工作调用
uint8_t app_sample_window_ready(void)               { return (g_ready != 0xFF) ? 1 : 0; }   /* 是否能取————判断是否满窗：满窗返回1，无满窗返回0 */
const sample_window_t *app_sample_window_get(void)                                          /* 取数据————返回满窗所在的结构体指针 */
{
    if (g_ready == 0xFF) return 0;      /* 没有满窗, 返回空指针 */
    return &g_win[g_ready];
}
void    app_sample_window_release(void)             { g_ready = 0xFF; }                     /* 结束使用————将 “g_ready” 置于默认值 0xFF */
void    app_sample_pause(uint8_t on)                { g_paused = on; }                      /* 发送前暂停，发送后继续————“on” 为 1 ：app_sample_task暂停采样；“on” 为 0 ：正常采样 */

//调试阶段使用
uint32_t app_sample_count(void)                     { return g_count; }                     /* 返回开机至今累计采样点数，用法：窗满时的数值 - 开窗时的数值，用增量计算窗内采样点数是否正常 */
uint16_t app_sample_overrun(void)                   { return g_overrun; }                   /* 返回累计丢窗数 */
uint8_t app_sample_timing_get(
    uint32_t *span_ticks,
    uint32_t *missed_ticks,
    uint32_t *boundary_gap,
    uint32_t *read_fail)
{
    if ((span_ticks == 0) || (missed_ticks == 0) ||
        (boundary_gap == 0) || (read_fail == 0))
    {
        return 0;
    }

    if (!g_report_ready)
    {
        return 0;
    }

    *span_ticks   = g_report_span_ticks;
    *missed_ticks = g_report_missed_ticks;
    *boundary_gap = g_report_boundary_gap;
    *read_fail    = g_report_read_fail;
    g_report_ready = 0;
    return 1;
}