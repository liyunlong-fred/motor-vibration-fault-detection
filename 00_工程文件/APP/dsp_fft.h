#ifndef __DSP_FFT_H
#define __DSP_FFT_H

#include "app_config.h"
#include "app_sample.h"
#include "arm_math.h"           /* CMSIS-DSP 的 FFT 函数与 float32_t 都在这里声明 */

/* ============================== 模块职责 =================================
 *  把 app_sample.c 攒满的一窗数据(APP_FRAME_N = 1024 点 int16 原始计数)
 *  做 1024 点实数 FFT, 算出单边幅值谱, 再挑出最强的几个峰打印出来。
 *
 *  与 PC 端 plot_check.py 必须完全一致的四件事(任何一处不同都对不上答案):
 *    1. 原始计数 -> g: 用同一个灵敏度 MPU6050_ACCEL_SENS (格/g);
 *    2. 先减去窗内均值(把重力造成的 0 Hz 大分量压掉), 再加窗;
 *    3. 乘 Hann 窗  w[i] = 0.5 - 0.5*cos(2*pi*i/(N-1));
 *    4. 单边幅值  amp[k] = 2*|X(k)| / (N * 0.5)
 *       分母里的 0.5 是 Hann 窗的"相干增益", 漏掉它幅值就只有真实值的一半。
 *
 *  频率分辨率: df = fs / N = 1000 / 1024 = 0.9766 Hz/格
 *  第 k 格对应的频率: f = k * df
 *  已知对照值(N=1024, fs=1000): 45 Hz 落在第 46 格(44.92 Hz), 90 Hz 落在第 92 格(89.84 Hz)
 * ======================================================================= */

#define DSP_FFT_N           APP_FRAME_N      /* FFT 点数, 必须等于一窗样本数 */
#define DSP_FFT_TOP_N       5U               /* 打印最强的几个峰 */
#define DSP_FFT_FMIN_HZ     10.0f            /* 只看 10 Hz 以上: 更低的多是重力零偏与温漂 */
#define DSP_FFT_FMAX_HZ     400.0f           /* 只看 400 Hz 以下: 1 kHz 采样上限是 500 Hz, 留余量 */
#define DSP_FFT_HANN_CG     0.5f             /* Hann 窗相干增益 */
#define DSP_FFT_GUARD       2U               /* 选中一个峰后左右各清掉 2 格, 防止一个峰被重复选中 */
#define DSP_FFT_SELF_F0_HZ  45.0f            /* 自检桩信号主频 */
#define DSP_FFT_SELF_A0_G   0.05f            /* 自检桩信号主频幅值 */
#define DSP_FFT_SELF_F1_HZ  90.0f            /* 自检桩信号二倍频 */
#define DSP_FFT_SELF_A1_G   0.01f            /* 自检桩信号二倍频幅值 */
#define DSP_FFT_SELF_DC_G   0.99f            /* 自检桩信号的直流(模拟重力压在测量轴上) */
#define DSP_FFT_CPU_MHZ     168UL            /* 系统主频, 只用来把周期数换算成微秒 */

/* 一次 FFT + 找峰的全部结果 */
typedef struct
{
    uint16_t seq;                        /* 本窗序号(抄自 sample_window_t, 用于和 PC 端对同一窗) */
    uint16_t n;                          /* 实际参与运算的样本数 */
    float    mean_g;                     /* 窗内均值(g), 也就是被减掉的那份重力分量 */
    float    df_hz;                      /* 频率分辨率 = fs/N = 0.9766 Hz */
    uint32_t cycles;                     /* 本次 arm_rfft_fast_f32 用了多少个 CPU 周期 */
    uint8_t  peak_cnt;                   /* 实际找到的峰个数(0 ~ DSP_FFT_TOP_N) */
    uint16_t peak_bin[DSP_FFT_TOP_N];    /* 峰所在谱线号 k */
    float    peak_hz [DSP_FFT_TOP_N];    /* 峰频率 = k * df, 单位 Hz */
    float    peak_g  [DSP_FFT_TOP_N];    /* 峰幅值(单边, 已做窗校正), 单位 g */
} dsp_fft_result_t;

/**
 * @brief       初始化: 打开 DWT 周期计数器、算好 Hann 窗表、初始化 1024 点实数 FFT 实例
 *              整个程序只需在开头调用一次(不要每窗都调, 初始化里要查表, 很费时间)
 * @param       无
 * @retval      无
 */
void dsp_fft_init(void);

/**
 * @brief       对一窗数据做 FFT 并找出最强的几个峰
 * @param       w    : 一窗数据地址(只读, 取完不会改动它)
 * @param       axis : 轴号 'X' / 'Y' / 'Z'
 * @param       res  : 结果输出地址(调用者提供, 需要读写)
 * @retval      无
 */
void dsp_fft_run(const sample_window_t *w, uint8_t axis, dsp_fft_result_t *res);

/**
 * @brief       把结果按"整数"格式打到串口上(频率用 Hz 的百倍整数, 幅值用 mg 整数)
 *              故意不用 %f: 浮点打印在嵌入式里既慢又要额外的库支持, 整数打印最稳
 * @param       res : 要打印的结果(只读)
 * @retval      无
 */
void dsp_fft_print(const dsp_fft_result_t *res);

/**
 * @brief       桩信号自检: 板上自己造 45 Hz/0.05 g + 90 Hz/0.01 g + 0.99 g 直流的 1024 点数据,
 *              走完整条 FFT 通路并打印。用来在"不接传感器、不接风扇"的情况下先给算法对答案
 *              期望输出: #1 f=44.92 Hz 50 mg, #2 f=89.84 Hz 10 mg
 * @param       无
 * @retval      无
 */
void dsp_fft_selftest(void);

#endif
