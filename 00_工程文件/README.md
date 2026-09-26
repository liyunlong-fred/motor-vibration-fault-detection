# 当前 STM32 开发工程

本目录是项目当前实际使用的 STM32F407 开发工程；`02_固件/`仅用于结档后的正式归档，不能作为当前实现状态的依据。

## 从哪里开始

使用 Keil MDK 打开 [Projects/MDK-ARM/motor_vib_detect.uvprojx](Projects/MDK-ARM/motor_vib_detect.uvprojx)。采样、窗口长度、数据源和串口参数首先查看 [APP/app_config.h](APP/app_config.h)；固件与 PC 工具的模块边界见 [系统地图](../知识库/20_系统地图.md)。

## 目录职责

| 目录 | 内容 |
| --- | --- |
| `APP/` | 项目业务层：定时采样、窗口管理、板上 FFT、串口帧和调试日志 |
| `Drivers/BSP/` | 板级设备驱动；当前采集链路使用软件 IIC 与 MPU6050 |
| [`Drivers/SYSTEM/`](Drivers/SYSTEM/README.md) | 延时、系统时钟和 USART 基础支持；进入该目录前先查看模块说明 |
| `Drivers/CMSIS/`、`Drivers/STM32F4xx_HAL_Driver/` | ST/CMSIS 依赖，不将其当作项目业务逻辑修改 |
| `Middlewares/USMART/` | 串口命令调试组件；保留其自带 `readme.txt` |
| `User/` | `main`、中断处理和 HAL 配置 |
| `Projects/MDK-ARM/` | Keil 工程定义；由 MDK 生成的本机配置不入库 |
| `Output/` | 编译产物；可重新生成，不入库 |

## 当前链路

`MPU6050 → APP/app_sample.c → APP/dsp_fft.c + APP/link_frame.c → USART1 → Python recv.py`。

当前工程参数为 1 kHz 采样、1024 点窗口、X 测量轴、MPU6050 ±2 g 和 USART1 460800 baud。修改这些通信或采样契约时，必须同步检查 `03_Python工具/py_common/frames.py`、`03_Python工具/py_common/metadata.py` 与数据集说明。

不要提交 `Output/`、`DebugConfig/`、`RTE/`、`*.uvoptx`、`*.uvguix.*` 或目标文件；它们是编译产物或本机 Keil 配置，具体忽略规则见项目根目录 `.gitignore`。
