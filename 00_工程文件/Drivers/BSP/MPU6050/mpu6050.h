#ifndef MPU6050_H
#define MPU6050_H

#include "./SYSTEM/sys/sys.h"

/* ==================== 器件地址 ====================
 * 8位地址(含读写位) = 7位地址 << 1
 * AD0 接 GND(模块默认下拉) -> 7位地址 0x68 -> 8位地址 0xD0
 */
#define MPU6050_ADDR            (0x68 << 1)     /* 0xD0 */

/* ==================== 寄存器地址 ==================== */
/* -------------------- 配置类 -------------------- */

#define MPU6050_SMPLRT_DIV      0x19
/*  bit[7:0] : SMPLRT_DIV[7:0]  采样率分频值
 *             采样率 = 陀螺仪输出率 / (1 + SMPLRT_DIV)
 *             · DLPF_CFG=0   陀螺输出率 8kHz -> 写 0x07 -> 8k/(1+7) = 1kHz(本项目)
 *             · DLPF_CFG=1~6 陀螺输出率 1kHz -> 写 0x00 -> 1kHz
 *  ★ 本项目: 0x07 (1kHz)
 *  [!] 加速度计内部输出率恒为 1kHz, 采样率设更高只是重复样本, 没有新信息
 */

#define MPU6050_CONFIG          0x1A
/*  bit7     : 保留
 *  bit6     : 保留
 *  bit5:3   : EXT_SYNC_SET[2:0] 外部帧同步(FSYNC)采样位置; 本板 FSYNC 未接 -> 必须 0
 *  bit2:0   : DLPF_CFG[2:0]     片上数字低通滤波档位(加速度+陀螺共用)
 *             0=260Hz  1=184Hz  2=94Hz  3=44Hz  4=21Hz  5=10Hz  6=5Hz  7=保留
 *  ★ 本项目: 0x00 -> 加速度带宽 260Hz(最高档), 延迟 0ms
 *  [!] 260Hz 以上已被硬件衰减: 做 "200-400Hz 宽带能量" 时只有 <=260Hz 段可信
 */

#define MPU6050_GYRO_CONFIG     0x1B
/*  bit7     : XG_ST  X轴陀螺自检(正常采集必须为 0)
 *  bit6     : YG_ST  Y轴陀螺自检
 *  bit5     : ZG_ST  Z轴陀螺自检
 *  bit4:3   : FS_SEL[1:0] 陀螺量程 0=±250 1=±500 2=±1000 3=±2000 °/s
 *  bit2:0   : 保留
 *  ★ 本项目: 不写, 保持复位默认 0x00 (FS_SEL=0 ±250°/s, 自检关)
 *  [!] 手册内部不一致: §3 汇总表把 Bit7~Bit5 画成"-", §4.4 明细页写明是
 *      XG_ST/YG_ST/ZG_ST, 以 §4.4 为准
 */

#define MPU6050_ACCEL_CONFIG    0x1C
/*  bit7     : XA_ST  X轴加速度自检(正常采集必须为 0, 置1会主动激励传感器)
 *  bit6     : YA_ST  Y轴加速度自检
 *  bit5     : ZA_ST  Z轴加速度自检
 *  bit4:3   : AFS_SEL[1:0] 加速度量程/分辨率
 *             0=±2g (16384 LSB/g)   1=±4g (8192 LSB/g)
 *             2=±8g ( 4096 LSB/g)   3=±16g(2048 LSB/g)
 *  bit2:0   : ACCEL_HPF[2:0] 高通滤波, 只作用于运动/自由落体/静止检测支路,
 *             不影响数据寄存器 -> 本项目置 0
 *  ★ 本项目: 0x00 = ±2g + 不自检 + 无高通
 *  [!] 量程太小会削顶, 削顶会在频谱上凭空造出高频假峰(比噪声更危险)
 *      若读数长期贴 ±32767, 改为 AFS_SEL=1(±4g)
 */

#define MPU6050_FIFO_EN         0x23
/*  bit7     : TEMP_FIFO_EN   温度写入 FIFO
 *  bit6     : XG_FIFO_EN     X轴陀螺写入 FIFO
 *  bit5     : YG_FIFO_EN     Y轴陀螺写入 FIFO
 *  bit4     : ZG_FIFO_EN     Z轴陀螺写入 FIFO
 *  bit3     : ACCEL_FIFO_EN  三轴加速度写入 FIFO
 *  bit2     : SLV2_FIFO_EN   辅助I2C从机2 写入 FIFO
 *  bit1     : SLV1_FIFO_EN   辅助I2C从机1 写入 FIFO
 *  bit0     : SLV0_FIFO_EN   辅助I2C从机0 写入 FIFO
 *  ★ 本项目: 0x08 (只攒加速度, 6 字节/样本); 连温度一起攒用 0x88 (8 字节/样本)
 *  [!] 前置条件: USER_CTRL(0x6A).FIFO_EN 必须已置 1 且 FIFO 已清空, 否则本使能无效
 */

#define MPU6050_INT_PIN_CFG     0x37
/*  bit7     : INT_LEVEL       中断电平极性  0=高有效  1=低有效
 *  bit6     : INT_OPEN        中断输出类型  0=推挽    1=开漏
 *  bit5     : LATCH_INT_EN    0=50us 脉冲    1=锁存直到读 INT_STATUS
 *  bit4     : INT_RD_CLEAR    1=读任意寄存器都清中断  0=只由读 INT_STATUS(0x3A) 清
 *  bit3     : FSYNC_INT_LEVEL FSYNC 中断极性
 *  bit2     : FSYNC_INT_EN    FSYNC 中断使能
 *  bit1     : I2C_BYPASS_EN   辅助I2C旁路使能(外挂磁力计用)
 *  bit0     : CLKOUT_EN       时钟输出使能
 *  ★ 本项目: 0x00 (高有效+推挽+50us脉冲, STM32 配上升沿 EXTI 即可);
 *            怕短脉冲被漏掉、想用逻辑分析仪抓 -> 0x20 (LATCH_INT_EN=1)
 *  [!] INT_RD_CLEAR 建议保持 0, 标志只由读 INT_STATUS 清除, 程序才能确认中断来源
 */

#define MPU6050_INT_ENABLE      0x38
/*  bit7     : FF_EN           自由落体中断使能
 *  bit6     : MOT_EN          运动检测中断使能
 *  bit5     : ZMOT_EN         零运动(静止)中断使能
 *  bit4     : FIFO_OFLOW_EN   FIFO 溢出中断使能
 *  bit3     : I2C_MST_INT_EN  辅助I2C主中断使能
 *  bit2     : 保留
 *  bit1     : 保留
 *  bit0     : DATA_RDY_EN     数据就绪中断使能(寄存器每次刷新即 1kHz 产生一次)
 *  ★ 本项目: 0x01 (只开数据就绪); 要监控"丢点"用 0x11 (+FIFO_OFLOW)
 *  [!] 采样节拍交给硬件中断, 比 delay 轮询稳定得多(规划 §5.1 的 1kHz 就靠它)
 */

#define MPU6050_INT_STATUS      0x3A
/*  只读寄存器
 *  bit7     : FF_INT          自由落体中断标志
 *  bit6     : MOT_INT         运动检测中断标志
 *  bit5     : ZMOT_INT        零运动中断标志
 *  bit4     : FIFO_OFLOW_INT  FIFO 溢出标志(触发即说明 MCU 没跟上, 数据已丢)
 *  bit3     : I2C_MST_INT     辅助I2C主中断标志
 *  bit2     : 保留
 *  bit1     : 保留
 *  bit0     : DATA_RDY_INT    数据就绪标志
 *  ★ 只读; ISR 里必读一次: (1)清标志 (2)区分本次是"数据就绪"还是"FIFO溢出"
 */

#define MPU6050_USER_CTRL       0x6A
/*  bit7     : 保留
 *  bit6     : FIFO_EN         FIFO 总开关(0x23 的使能必须先打开它才生效)
 *  bit5     : I2C_MST_EN      辅助I2C主模式使能(本项目不用辅助I2C -> 0)
 *  bit4     : I2C_IF_DIS      1=禁用I2C改用SPI(MPU-6000 用)
 *  bit3     : 保留
 *  bit2     : FIFO_RESET      1=清空FIFO(写完自动归0)
 *  bit1     : I2C_MST_RESET   辅助I2C主复位
 *  bit0     : SIG_COND_RESET  传感器信号链复位
 *  ★ 本项目: 初始 0x00; 开FIFO流程 = 写 0x04(FIFO_RESET) -> 写 0x40(FIFO_EN=1)
 *  [!][!] MPU-6050 的 I2C_IF_DIS 必须写 0! 写 1 是切 SPI 用的, 6050 写 1 会直接
 *         搞坏主 I2C 通信(典型的"一写就失联"坑)
 */

#define MPU6050_PWR_MGMT_1      0x6B
/*  bit7     : DEVICE_RESET   1=软复位全部寄存器(复位值 0x40)
 *  bit6     : SLEEP          1=睡眠; [!] 上电默认就是睡眠, 不唤醒则数据寄存器不更新
 *  bit5     : CYCLE          1=低功耗循环模式(配合 PWR_MGMT_2 的 LP_WAKE_CTRL)
 *  bit4     : 保留
 *  bit3     : TEMP_DIS       1=关闭温度传感器
 *  bit2:0   : CLKSEL[2:0]    时钟源 0=内部8MHz RC  1=X轴陀螺PLL  2=Y轴陀螺PLL
 *                            3=Z轴陀螺PLL  4=外部32.768kHz  5=外部19.2MHz
 *  ★ 本项目: (1)先写 0x80(DEVICE_RESET) -> 延时 >=100ms; (2)再写 0x01(SLEEP=0 + CLKSEL=1)
 *  [!] "WHO_AM_I 读得到、数据却一直不变" 就是 bit6 没清;
 *      CLKSEL=1 依赖 X 轴陀螺工作, 若在 0x6C 把 XG 置待机, 时钟会自动退回内部振荡器
 */

#define MPU6050_PWR_MGMT_2      0x6C
/*  bit7:6   : LP_WAKE_CTRL[1:0] 低功耗唤醒频率(仅 CYCLE=1 时有效)
 *  bit5     : STBY_XA        X轴加速度待机
 *  bit4     : STBY_YA        Y轴加速度待机
 *  bit3     : STBY_ZA        Z轴加速度待机
 *  bit2     : STBY_XG        X轴陀螺待机
 *  bit1     : STBY_YG        Y轴陀螺待机
 *  bit0     : STBY_ZG        Z轴陀螺待机
 *  ★ 本项目: 0x00 (六轴全开, 最省心, 且与 CLKSEL=1 兼容)
 *  [!] 想省电写 0x38(保留 X 陀螺当时钟); 但三轴加速度 STBY_XA/YA/ZA 必须为 0,
 *      否则拿不到完整振动信息
 */

#define MPU6050_FIFO_COUNTH     0x72
/*  bit[7:0] : FIFO_COUNT[15:8]  FIFO 内未读字节数 高 8 位(只读)
 *  与 0x73 合成 16 位; 除以每样本字节数(加速度 6 / 加速度+温度 8) = 样本数
 *  [!] 手册 §3 汇总表标 R/W, §4.38 明细页写 "Type: Read Only", 按只读用
 */

#define MPU6050_FIFO_COUNTL     0x73
/*  bit[7:0] : FIFO_COUNT[7:0]   FIFO 内未读字节数 低 8 位(与 0x72 合成 16 位)
 */

#define MPU6050_FIFO_R_W        0x74
/*  bit[7:0] : FIFO_DATA[7:0]    FIFO 读写数据口(每读/写一个字节, 指针自动 +1)
 *  读之前先看 FIFO_COUNT(0x72/0x73); ACCEL_FIFO_EN=1 时每个样本 =
 *  X_H,X_L,Y_H,Y_L,Z_H,Z_L (3 个 int16, 高位在前)
 *  [!] 开始新一段采集前必须先 FIFO_RESET, 否则上段残留会让样本错位
 */

#define MPU6050_WHO_AM_I        0x75
/*  只读寄存器
 *  bit7     : 保留
 *  bit6:1   : WHO_AM_I[6:1]  器件ID, 出厂默认 0x68
 *  bit0     : 保留
 *  ★ AD0 只影响 I2C 从机地址(0x68/0x69), 不影响本寄存器返回值
 *  [!] 兼容/山寨芯片可能返回 0x60 / 0x70 / 0x72 / 0x98 等非 0x68 的值
 *      -> 只记录不判死; 只有 0x00 / 0xFF 才说明通信失败
 */

/* --- 数据类(按顺序连续读即可, 地址自动加1) --- */
#define MPU6050_ACCEL_XOUT_H    0x3B    /* 从这里连续读 6 字节 = 加速度 X/Y/Z 轴 */
#define MPU6050_ACCEL_XOUT_L    0x3C
#define MPU6050_ACCEL_YOUT_H    0x3D
#define MPU6050_ACCEL_YOUT_L    0x3E
#define MPU6050_ACCEL_ZOUT_H    0x3F
#define MPU6050_ACCEL_ZOUT_L    0x40
#define MPU6050_TEMP_OUT_H      0x41    /* 连续读 2 字节 = 温度 */
#define MPU6050_TEMP_OUT_L      0x42
#define MPU6050_GYRO_XOUT_H     0x43    /* 连续读 6 字节 = 陀螺 X/Y/Z 轴 */
#define MPU6050_GYRO_XOUT_L     0x44
#define MPU6050_GYRO_YOUT_H     0x45
#define MPU6050_GYRO_YOUT_L     0x46
#define MPU6050_GYRO_ZOUT_H     0x47
#define MPU6050_GYRO_ZOUT_L     0x48

/* ==================== 量程与灵敏度 ====================
 * 加速度计是 16 位有符号输出(共 65536 格), 量程决定"这些格子铺多大的物理范围":
 *     灵敏度(格/g) = 32768 / 量程(g)
 *   量程越小 -> 每格代表越小 -> 分辨率越高, 但可测上限越低
 *
 *   量程     灵敏度        每格代表    可测上限    AFS_SEL
 *   ±2g    16384 LSB/g    0.061 mg    ±2 g        0
 *   ±4g     8192 LSB/g    0.122 mg    ±4 g        1
 *   ±8g     4096 LSB/g    0.244 mg    ±8 g        2
 *   ±16g    2048 LSB/g    0.488 mg    ±16 g       3
 */

    /* 各量程对应的灵敏度(LSB/g) */
#define MPU6050_ACCEL_FS_2G     16384.0f
#define MPU6050_ACCEL_FS_4G     8192.0f
#define MPU6050_ACCEL_FS_8G     4096.0f
#define MPU6050_ACCEL_FS_16G    2048.0f

/* ------- 本项目当前使用的量程 ------- */
#define MPU6050_ACCEL_FS_SEL    0       /* 0=±2g  1=±4g  2=±8g  3=±16g */

/* ------- 量程的数值及配置的自动定义 ------- */
#if   MPU6050_ACCEL_FS_SEL == 0
#define MPU6050_ACCEL_SENS      MPU6050_ACCEL_FS_2G
#define MPU6050_ACCEL_FS_NAME   "±2g"
#elif MPU6050_ACCEL_FS_SEL == 1
#define MPU6050_ACCEL_SENS      MPU6050_ACCEL_FS_4G
#define MPU6050_ACCEL_FS_NAME   "±4g"
#elif MPU6050_ACCEL_FS_SEL == 2
#define MPU6050_ACCEL_SENS      MPU6050_ACCEL_FS_8G
#define MPU6050_ACCEL_FS_NAME   "±8g"
#elif MPU6050_ACCEL_FS_SEL == 3
#define MPU6050_ACCEL_SENS      MPU6050_ACCEL_FS_16G
#define MPU6050_ACCEL_FS_NAME   "±16g"
#else
#error "MPU6050_ACCEL_FS_SEL 只能是 0~3"
#endif

/* 写 0x1C ACCEL_CONFIG 用的值: AFS_SEL 在 bit4:3, 其余位(自检/高通)都为 0 */
#define MPU6050_ACCEL_CONFIG_VAL    (MPU6050_ACCEL_FS_SEL << 3)

/* ==================== 数据类型 ==================== */
typedef struct
{
    int16_t x, y, z;        /* 原始值(LSB) */
} mpu6050_raw_t;

typedef struct
{
    float x, y, z;          /* 换算后的加速度, 单位 g */
} mpu6050_accel_t;

/* ==================== 函数声明 ==================== */
uint8_t mpu6050_init(void);                             /* 0=成功, 其他=失败步骤号 */
uint8_t mpu6050_who_am_i(void);                         /* 读器件ID */
uint8_t mpu6050_read_raw(mpu6050_raw_t *raw);           /* 读三轴原始值, 0=成功 */
uint8_t mpu6050_read_accel(mpu6050_accel_t *accel);     /* 读三轴加速度(g), 0=成功 */
float   mpu6050_read_temp(void);                        /* 读温度(℃) */

#endif
