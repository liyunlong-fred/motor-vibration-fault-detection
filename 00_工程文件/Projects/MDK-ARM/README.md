# Keil MDK 工程

使用 Keil MDK 打开 `motor_vib_detect.uvprojx`。该工程通过相对路径引用 `../../APP/`、`../../Drivers/`、`../../Middlewares/` 和 `../../User/`，因此应保留 `00_工程文件/` 的目录层级。

首次打开或切换开发机后，Keil 可能生成 `Output/`、`DebugConfig/`、`RTE/`、`.vscode/`、`*.uvoptx` 和 `*.uvguix.*`。它们含构建产物或机器专属路径，均不应提交；只提交 `motor_vib_detect.uvprojx` 与可复现构建所需的项目源码。

构建并烧录当前源码后，使用 `03_Python工具/recv.py` 重新采集一段数据，才能确认固件、板端日志和 PC 侧解析仍然一致。详见 [当前状态](../../../知识库/10_当前状态.md)。
