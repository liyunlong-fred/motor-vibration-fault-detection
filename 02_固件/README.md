# 固件工程目录说明

## 目录定位

`02_固件/`用于保存项目结档后的正式 STM32 固件源码和工程文件。

当前开发阶段的实际工程位于 `00_工程文件/`。项目结档时，将其中的固件源码和 Keil 工程迁移到本目录；`00_工程文件/`可作为开发过程目录保留。

## 结档时迁移内容

迁移后应保持下面的目录层级：

```text
02_固件/
├─ README.md
├─ APP/
├─ Drivers/
├─ Middlewares/
├─ User/
└─ Projects/
   └─ MDK-ARM/
      └─ motor_vib_detect.uvprojx
```

应迁移的内容包括：

- `APP/`：项目业务层代码，包括采样、FFT、调试和串口帧处理。
- `Drivers/`：STM32 HAL、CMSIS、板级驱动、MPU6050、IIC、LCD、LED、KEY 和系统基础驱动。
- `Middlewares/`：例如 USMART 调试组件。
- `User/`：`main.c`、中断文件和 HAL 配置文件。
- `Projects/MDK-ARM/motor_vib_detect.uvprojx`：Keil 工程文件。
- 其他确实属于工程源码、工程配置或复现构建所需的说明文件。

迁移的是 `00_工程文件/`里面的内容，而不是把整个 `00_工程文件/`目录再套一层放进 `02_固件/`。保持上述相对目录层级后，Keil 工程中的相对路径通常无需修改。

## 不迁移的内容

以下内容属于编译产物、临时文件或本机专用配置，不应作为正式固件源码归档：

- `Output/`
- `*.o`、`*.d`、`*.axf`、`*.map`、`*.htm`、`*.dep`
- `*.uvopt`、`*.uvguix.*`
- 本机专用的 `DebugConfig/`、`RTE/`、`.vscode/`

首次在 `02_固件/` 中打开并编译工程时，Keil 可以重新生成 `Output/` 等编译产物。

如果需要提供可直接烧录的固件，应单独保存带版本号的发布文件，例如：

```text
02_固件/
└─ Releases/
   └─ motor_vib_detect_v0.1.0.hex
```

发布文件应注明对应源码版本、编译日期、目标芯片和主要固件参数，不能用未确认来源的历史 HEX 文件代替当前源码构建结果。
