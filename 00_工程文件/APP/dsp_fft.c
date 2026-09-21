#include "dsp_fft.h"
#include <math.h>               /* cosf / sqrtf / sinf / fabsf */

/* ================= 1、内部状态与缓冲 ================= */
static arm_rfft_fast_instance_f32 g_rfft;                   /* FFT 实例: 内部存旋转因子指针等 */
static float32_t g_win [DSP_FFT_N];                         /* Hann 窗系数表, 上电算一次 */
static float32_t g_in  [DSP_FFT_N];                         /* FFT 输入: 去均值 + 加窗后的数据 */
static float32_t g_out [DSP_FFT_N];                         /* FFT 输出: CMSIS-DSP 的"打包"格式 */
static float32_t g_amp [(DSP_FFT_N >> 1) + 1U];             /* 单边幅值谱: 0~500 Hz 共 513 根谱线 */
static float32_t g_work[(DSP_FFT_N >> 1) + 1U];             /* 取峰用的副本(取过的峰清零, 不动 g_amp) */
static uint8_t   g_inited = 0;                              /* 1 = 已经初始化过 */

/* 说明: 本文件所有 APP_LOG 的字符串都用 ASCII 写(中文只出现在注释里), 原因有两条:
 *   1. 源文件是 GBK 编码, 字符串里的中文在 AC6 下会报 -Winvalid-source-encoding 警告(无害, 但没必要新增);
 *   2. 串口输出要与 PC 端 peak_check.py 的输出逐行对照, 纯 ASCII 不受终端编码影响, 直接 diff 就行。 */

/* ================= 2、按轴号取原始计数 ================= */
/**
 * @brief       取一窗里第 i 个样本的原始计数
 * @param       w    : 一窗数据(只读)
 * @param       axis : 轴号 'X' / 'Y' / 'Z'
 * @param       i    : 样本下标 0 ~ n-1
 * @retval      该样本的 int16 原始计数
 */
static int16_t dsp_fft_pick(const sample_window_t *w, uint8_t axis, uint16_t i)
{
    if (axis == 'X') return w->x[i];
    if (axis == 'Y') return w->y[i];
    return w->z[i];     /* 默认 Z 轴: 按 2026-09-21 实测, 装好后重力压在 Z 轴(静止读数约 17000 格) */
}

/* ================= 3、初始化 ================= */
/**
 * @brief       初始化: DWT 计时 + Hann 窗表 + FFT 实例
 * @param       无
 * @retval      无
 */
void dsp_fft_init(void)
{
    uint16_t   i;
    arm_status st;
    uint32_t   df_x10000;

    /* --- 3.1 DWT 周期计数器: 用来量耗时的"秒表" ---
     * CYCCNT 每个 CPU 时钟加 1, 主频 168 MHz 时 1 个周期约 5.95 ns, 每 168 个周期 = 1 us */
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;     /* 跟踪调试模块总开关, 不开 CYCCNT 不走 */
    DWT->CYCCNT = 0U;                                   /* 计数器清零 */
    DWT->CTRL  |= DWT_CTRL_CYCCNTENA_Msk;               /* 让 CYCCNT 开始自增 */

    /* --- 3.2 Hann 窗系数表 ---
     * w[i] = 0.5 - 0.5*cos(2*pi*i/(N-1)), 两头接近 0、中间接近 1, 用来压掉截断处的频谱泄漏。
     * 用 N-1 而不是 N: 这样首尾两个系数严格为 0, 和 numpy 的 np.hanning(N) 完全一致。
     * ★ 写错会怎样: 若写成 cos(2*pi*i/N), 窗系数与 PC 端差一点, 峰值幅值会出现百分之一二的偏差,
     *   看起来"好像对", 但做板 PC 对拍时永远差那一口气, 很难查。 */
    for (i = 0; i < DSP_FFT_N; i++)
    {
        g_win[i] = 0.5f - 0.5f * cosf(6.28318531f * (float32_t)i / (float32_t)(DSP_FFT_N - 1U));
    }

    /* --- 3.3 FFT 实例: 只在这里初始化一次 ---
     * arm_rfft_fast_init_f32 会把长度 1024 对应的旋转因子表地址填进 g_rfft。
     * ★ 写错会怎样: 把它放进 dsp_fft_run() 里每窗都调一次, 单是初始化就要几百微秒,
     *   既拖慢又不稳定; 一旦和 arm_rfft_fast_f32 之间插了别的初始化, 结果直接错乱。 */
    st = arm_rfft_fast_init_f32(&g_rfft, DSP_FFT_N);
    if (st != ARM_MATH_SUCCESS)
    {
        g_inited = 0;
        APP_LOG("dsp_fft_init FAIL: arm_rfft_fast_init_f32 -> %d\r\n", (int)st);
        return;
    }

    g_inited = 1;

    /* df = 1000/1024 = 0.9766 Hz, 用 1e-4 Hz 为单位的整数打印, 避免用 %f */
    df_x10000 = ((uint32_t)APP_FS_HZ * 10000UL + (DSP_FFT_N / 2U)) / DSP_FFT_N;
    APP_LOG("dsp_fft_init OK: N=%u, df=%lu.%04lu Hz, cpu=%lu MHz\r\n",
            (unsigned)DSP_FFT_N,
            (unsigned long)(df_x10000 / 10000UL), (unsigned long)(df_x10000 % 10000UL),
            (unsigned long)DSP_FFT_CPU_MHZ);
}

/* ================= 4、算一窗 ================= */
/**
 * @brief       去均值 -> 加 Hann 窗 -> 1024 点实数 FFT -> 单边幅值谱 -> 找最强的几个峰
 * @param       w    : 一窗数据(只读)
 * @param       axis : 轴号 'X' / 'Y' / 'Z'
 * @param       res  : 结果输出地址
 * @retval      无
 */
void dsp_fft_run(const sample_window_t *w, uint8_t axis, dsp_fft_result_t *res)
{
    uint16_t  i, k, n, half, kmin, kmax, k0, k1, best_k, p;
    float32_t sens, sum = 0.0f, mean = 0.0f, re, im, df, best_v;
    uint32_t  c0;

    if ((w == 0) || (res == 0)) return;                 /* 空指针直接返回, 不要往下算 */
    if (!g_inited)
    {
        APP_LOG("dsp_fft_run: call dsp_fft_init() first\r\n");
        return;
    }

    /* --- 4.0 准备参数 --- */
    n    = w->n;
    if (n > DSP_FFT_N) n = DSP_FFT_N;                   /* 防御: 样本数超过 1024 会越界 */
    half = (uint16_t)(DSP_FFT_N >> 1);                  /* 512: 单边谱最多到第 512 格(500 Hz) */
    sens = (float32_t)MPU6050_ACCEL_SENS;               /* 格/g, 与 PC 端 frames.SENS 同一来源 */
    df   = (float32_t)APP_FS_HZ / (float32_t)DSP_FFT_N; /* 0.9766 Hz/格 */

    res->seq      = w->seq;
    res->n        = n;
    res->df_hz    = df;
    res->cycles   = 0U;
    res->peak_cnt = 0U;

    /* --- 4.1 原始计数 -> g, 顺手求和(为求均值) --- */
    for (i = 0; i < n; i++)
    {
        g_in[i] = (float32_t)dsp_fft_pick(w, axis, i) / sens;
        sum    += g_in[i];
    }
    mean = (n > 0U) ? (sum / (float32_t)n) : 0.0f;

    /* 样本数不足 1024 时后半段补均值(减完均值正好是 0), 不要补 0 也不要留上一窗的旧数据 */
    for (i = n; i < DSP_FFT_N; i++) g_in[i] = mean;

    /* --- 4.2 去均值 + 加 Hann 窗 ---
     * ★ 写错会怎样: 忘记减均值, 0 Hz(直流)那根谱线高达 1.04 g, 纵轴一压缩,
     *   真实的小峰(几十 mg)在图上看不见; 忘了乘 g_win, 谱峰会拖尾、幅值也会不准。 */
    for (i = 0; i < DSP_FFT_N; i++)
    {
        g_in[i] = (g_in[i] - mean) * g_win[i];
    }
    res->mean_g = mean;

    /* --- 4.3 实数 FFT: 最后一个参数 0 = 正变换 ---
     * 注意 g_in 会被这个函数当场改写, 所以原始数据不能只留这一份。
     * ★ 写错会怎样: 最后一个参数写成 1 就是逆变换, 出来的不是频谱, 是一堆无意义的时域数。 */
    c0 = DWT->CYCCNT;                                   /* 秒表开始 */
    arm_rfft_fast_f32(&g_rfft, g_in, g_out, 0U);
    res->cycles = DWT->CYCCNT - c0;                     /* 秒表结束 */

    /* --- 4.4 频域 -> 单边幅值谱 ---
     * CMSIS-DSP 的输出是"打包"格式, 顺序与实数频谱的自然顺序不同:
     *     g_out[0] = Re(0)          , 直流(0 Hz)
     *     g_out[1] = Re(N/2)        , 奈奎斯特(500 Hz)
     *     g_out[2k] = Re(k), g_out[2k+1] = Im(k)   (k = 1 .. N/2-1)
     * ★ 写错会怎样: 若按 Re(k)=g_out[2k], Im(k)=g_out[2k+1] 从头开始理解,
     *   却把 g_out[1] 当成 Im(1) 用, 从第 1 格起整条频率轴就错位了, 峰位置全对不上。
     * 幅值公式里的 2 是把双边谱折成单边谱, 0.5 是 Hann 窗相干增益。 */
    g_amp[0] = fabsf(g_out[0]) / ((float32_t)DSP_FFT_N * DSP_FFT_HANN_CG);
    for (k = 1U; k < half; k++)
    {
        re = g_out[2U * k];
        im = g_out[2U * k + 1U];
        g_amp[k] = 2.0f * sqrtf(re * re + im * im) / ((float32_t)DSP_FFT_N * DSP_FFT_HANN_CG);
    }
    g_amp[half] = fabsf(g_out[1]) / ((float32_t)DSP_FFT_N * DSP_FFT_HANN_CG);

    /* --- 4.5 找最强的 DSP_FFT_TOP_N 个峰 --- */
    kmin = (uint16_t)(DSP_FFT_FMIN_HZ / df + 0.999f);   /* 向上取整: 略过 10 Hz 以下 */
    kmax = (uint16_t)(DSP_FFT_FMAX_HZ / df);            /* 向下取整: 不超过 400 Hz */
    if (kmax > (uint16_t)(half - 1U)) kmax = (uint16_t)(half - 1U);
    if (kmin < 1U) kmin = 1U;
    if (kmin > kmax) kmin = kmax;                       /* 参数写反时不至于算出乱值 */

    for (k = 0U; k <= half; k++) g_work[k] = g_amp[k];  /* 在副本上取峰, g_amp 留着以后提特征用 */

    for (p = 0U; p < DSP_FFT_TOP_N; p++)
    {
        best_k = 0U;
        best_v = -1.0f;
        for (k = kmin; k <= kmax; k++)
        {
            if (g_work[k] > best_v)
            {
                best_v = g_work[k];
                best_k = k;
            }
        }
        if ((best_k == 0U) || (best_v <= 0.0f)) break;  /* 找不到峰(或幅值为 0)就结束 */

        res->peak_bin[p] = best_k;
        res->peak_hz [p] = (float32_t)best_k * df;
        res->peak_g  [p] = best_v;

        /* 把峰左右各 DSP_FFT_GUARD 格清零: Hann 窗一个峰的主瓣宽 4 格(左右各 2 格),
         * 不清零的话同一个峰会连着被选中 5 次, TOP5 全是同一个频率。 */
        k0 = (best_k > DSP_FFT_GUARD) ? (uint16_t)(best_k - DSP_FFT_GUARD) : 0U;
        k1 = (uint16_t)(best_k + DSP_FFT_GUARD);
        if (k1 > half) k1 = half;
        for (k = k0; k <= k1; k++) g_work[k] = 0.0f;
    }
    res->peak_cnt = (uint8_t)p;
}

/* ================= 5、打印结果 ================= */
/**
 * @brief       用整数格式打印 TOP 峰, 方便和 PC 端逐行对照
 * @param       res : 结果(只读)
 * @retval      无
 */
void dsp_fft_print(const dsp_fft_result_t *res)
{
    uint8_t  p;
    uint32_t fx100, amg;

    if (res == 0) return;

    APP_LOG("FFT seq=%u n=%u mean=%ld mg cycles=%lu (%lu us)\r\n",
            (unsigned)res->seq, (unsigned)res->n,
            (long)(res->mean_g * 1000.0f),
            (unsigned long)res->cycles,
            (unsigned long)(res->cycles / DSP_FFT_CPU_MHZ));   /* 周期 / 168 = 微秒 */

    for (p = 0U; p < res->peak_cnt; p++)
    {
        fx100 = (uint32_t)(res->peak_hz[p] * 100.0f + 0.5f);        /* Hz 的百倍整数 */
        amg   = (uint32_t)(res->peak_g [p] * 1000.0f + 0.5f);       /* mg */
        APP_LOG("  #%u bin=%u f=%lu.%02lu Hz amp=%lu mg\r\n",
                (unsigned)(p + 1U), (unsigned)res->peak_bin[p],
                (unsigned long)(fx100 / 100UL), (unsigned long)(fx100 % 100UL),
                (unsigned long)amg);
    }

    if (res->peak_cnt == 0U)
    {
        APP_LOG("  no line above 0 in %u~%u Hz, check data source\r\n",
                (unsigned)DSP_FFT_FMIN_HZ, (unsigned)DSP_FFT_FMAX_HZ);
    }
}

/* ================= 6、桩信号自检 ================= */
/**
 * @brief       板上造已知频率的合成信号, 走完整条通路, 给算法对答案
 * @param       无
 * @retval      无
 */
void dsp_fft_selftest(void)
{
    static sample_window_t w;       /* 6 KB, 只在自检时用 */
    dsp_fft_result_t res;
    uint16_t i;
    float32_t t, a;

    for (i = 0; i < DSP_FFT_N; i++)
    {
        t = (float32_t)i / (float32_t)APP_FS_HZ;                        /* 第 i 个样本对应的时刻(秒) */
        a = DSP_FFT_SELF_DC_G                                          /* 直流: 假装重力压在测量轴上 */
          + DSP_FFT_SELF_A0_G * sinf(6.28318531f * DSP_FFT_SELF_F0_HZ * t)
          + DSP_FFT_SELF_A1_G * sinf(6.28318531f * DSP_FFT_SELF_F1_HZ * t);

        w.z[i] = (int16_t)(a * (float32_t)MPU6050_ACCEL_SENS);         /* 换算成和传感器一样的原始计数 */
        w.x[i] = 0;
        w.y[i] = 0;
    }
    w.n   = DSP_FFT_N;
    w.seq = 0U;

    APP_LOG("---- selftest: 45Hz/50mg + 90Hz/10mg + DC 990mg ----\r\n");
    dsp_fft_run(&w, 'Z', &res);
    dsp_fft_print(&res);
    APP_LOG("---- expect: #1 f=44.92Hz amp=50mg, #2 f=89.84Hz amp=10mg ----\r\n");
}
