#include "./BSP/MPU6050/mpu6050.h"
#include "./BSP/IIC/iic.h"
#include "./SYSTEM/delay/delay.h"
#include "./SYSTEM/usart/usart.h"

/**
 * @brief       读取器件 ID
 * @param       无
 * @retval      器件返回的 ID; 读失败返回 0xFF
 */
uint8_t mpu6050_who_am_i(void)
{
    uint8_t id = 0xFF;

    iic_reg_read_length(MPU6050_ADDR, MPU6050_WHO_AM_I, &id, 1);
    return id;
}

/**
 * @brief       初始化MPU6050
 * @param       无
 * @retval      0, 成功
 *              1~8, 失败, 数字代表卡在第几步
 */
uint8_t mpu6050_init(void)
{
    uint8_t id  = 0;
    uint8_t tmp = 0;

    /* --- 1. 软复位, 让芯片回到已知状态 --- */
    if (iic_reg_write(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0x80)) return 1;
    delay_ms(100);                          /* 复位后需等待寄存器稳定 */

    /* --- 2. 认芯片: 宽松判据, 只有 0x00/0xFF 才算真的没通信 --- */
    id = mpu6050_who_am_i();
    if (id == 0x00 || id == 0xFF) return 2;
    /* 兼容芯片可能报 0x60/0x70/0x72/0x98 等, 只记录不判死 */
    printf("MPU6050 WHO_AM_I = 0x%02X (非 0x68 也可能是兼容芯片)\r\n", id);

    /* --- 3. 唤醒 + 时钟源选 X 轴陀螺 PLL (复位后是 0x40 睡眠态) --- */
    if (iic_reg_write(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0x01)) return 3;
    delay_ms(100);
    iic_reg_write(MPU6050_ADDR, 0x68, 0x07);                  /* 陀螺+加速度+温度 信号链复位 */
    delay_ms(100);
    iic_reg_write(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0x01);    /* 复位后重新唤醒 */
    delay_ms(50);
    /* --- 4. 采样率: DLPF关闭时陀螺输出 8kHz, 8k/(1+7) = 1kHz --- */
    if (iic_reg_write(MPU6050_ADDR, MPU6050_SMPLRT_DIV, 0x07)) return 4;

    /* --- 5. DLPF: CFG=0 -> 低通滤波档位，加速度带宽 260Hz(最大), 延迟 0 --- */
    if (iic_reg_write(MPU6050_ADDR, MPU6050_CONFIG, 0x00)) return 5;

    /* --- 6. 量程: 值由头文件决定, 不自检, 关闭高通 --- */
    if (iic_reg_write(MPU6050_ADDR, MPU6050_ACCEL_CONFIG, MPU6050_ACCEL_CONFIG_VAL)) return 6;

    /* --- 7. 回读校验: 只要 SLEEP 位(bit6)清了就算成功 --- */
    if (iic_reg_read_length(MPU6050_ADDR, MPU6050_PWR_MGMT_1, &tmp, 1)) return 7;
    if (tmp & 0x40) return 8;               /* 还在睡眠 -> 写没生效 */

    return 0;
}

/**
 * @brief       读取三轴加速度原始值
 * @param       raw: 原始值结构体指针
 * @retval      0, 成功; 1, 失败
 */
uint8_t mpu6050_read_raw(mpu6050_raw_t *raw)
{
    uint8_t buf[6];

    /* 一次突发读 6 字节: 高字节在前, 地址自动加1 */
    if (iic_reg_read_length(MPU6050_ADDR, MPU6050_ACCEL_XOUT_H, buf, 6)) return 1;

    raw->x = (int16_t)(((uint16_t)buf[0] << 8) | buf[1]);
    raw->y = (int16_t)(((uint16_t)buf[2] << 8) | buf[3]);
    raw->z = (int16_t)(((uint16_t)buf[4] << 8) | buf[5]);
    return 0;
}

/**
 * @brief       读取三轴加速度(单位 g)
 * @param       accel: 结果结构体指针
 * @retval      0, 成功; 1, 失败
 */
uint8_t mpu6050_read_accel(mpu6050_accel_t *accel)
{
    mpu6050_raw_t raw;

    if (mpu6050_read_raw(&raw)) return 1;

/* --- 原始数据视为步数，量程的倒数为步长，而这相乘可得加速度（单位为重力加速度g = 9.80665 m/s2） --- */
    accel->x = raw.x / MPU6050_ACCEL_SENS;      /* 灵敏度由 mpu6050.h中定义的量程决定 */
    accel->y = raw.y / MPU6050_ACCEL_SENS;
    accel->z = raw.z / MPU6050_ACCEL_SENS;
    return 0;
}

/**
 * @brief       读取芯片温度(℃)
 * @param       无
 * @retval      温度; 失败返回 -273.0f
 */
float mpu6050_read_temp(void)
{
    uint8_t buf[2];
    int16_t raw;

    if (iic_reg_read_length(MPU6050_ADDR, MPU6050_TEMP_OUT_H, buf, 2)) return -273.0f;

    raw = (int16_t)(((uint16_t)buf[0] << 8) | buf[1]);
    return raw / 340.0f + 36.53f;
}

