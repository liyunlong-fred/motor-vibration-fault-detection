# 驱动层

本目录混合了项目使用的板级驱动、系统基础代码和第三方依赖。修改前应先确认文件归属，避免把项目逻辑直接写进 HAL 或 CMSIS。

| 位置 | 归属与用途 |
| --- | --- |
| `BSP/` | 板级驱动。当前振动采集依赖 `BSP/IIC/` 和 `BSP/MPU6050/`；`KEY`、`LED`、`LCD` 为板级外围模块 |
| [`SYSTEM/`](SYSTEM/README.md) | 时钟、延时与 USART 支持；模块说明、职责边界和子目录入口见其 README |
| `CMSIS/` | ARM/ST 设备与内核定义 |
| `STM32F4xx_HAL_Driver/` | STM32F4 HAL 库 |

当前 MPU6050 使用软件 IIC 的 PB6/PB7；量程、寄存器配置和换算参数以 `BSP/IIC/iic.h`、`BSP/MPU6050/mpu6050.h` 及 `../APP/app_config.h` 为准。变更引脚或量程后，需同时核对 Python 侧的帧解析和数据集元数据。
