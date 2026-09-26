# 应用层（APP）

这里是振动检测固件的项目业务层。先阅读 `app_config.h`，它是采样率、窗口长度、数据源、串口波特率和调试开关的唯一参数入口。

| 模块 | 职责 |
| --- | --- |
| `app_config.h` | 定义 1 kHz、1024 点窗口、FIFO 批量大小、窗口槽数、数据源和 USART 波特率 |
| `app_sample.c/.h` | 以 TIM3 触发服务 MPU6050 FIFO，管理三槽连续窗口并提供连续性统计 |
| `dsp_fft.c/.h` | 对窗口做量程换算、去均值、Hann 窗、CMSIS-DSP RFFT、单边幅值和 10–400 Hz TOP-5 峰值 |
| `link_frame.c/.h` | 编码并投递加速度/文本帧；加速度帧带 `first_sample_id` |
| `app_debug.c/.h` | `APP_LOG` 使用的调试输出封装 |

主循环位于 `../User/main.c`：它持续服务 FIFO，取得完成窗口后执行 FFT、将原始帧投递给 UART DMA 队列，再释放窗口；采样不会因 FFT、日志或发送而暂停。

`link_frame.h` 与 `../../03_Python工具/py_common/frames.py` 共同构成 PC/MCU 通信契约。改动帧头、帧类型、字段顺序、样本数、量程码或字节序时，必须同步修改并对拍两端，不能只调整其中一端。
