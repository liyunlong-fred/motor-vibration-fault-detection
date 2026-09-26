# Python 公共契约模块

本目录只放被多个 Python 脚本共享的协议与数据契约代码，不放独立可执行工具。

| 文件 | 唯一职责 |
| --- | --- |
| `frames.py` | 解析 MCU 字节流中的加速度帧与文本日志帧；定义帧头、字段、采样率、量程码，以及原始 `int16` 到 `g` 的换算 |
| `metadata.py` | 定义 schema v3 的受控字段、工况到模型标签映射、元数据校验、CSV 注释头和正式数据 `manifest.csv` 读写 |

它们分别与 `00_工程文件/APP/link_frame.h` 和 `03_Python工具/config.json` 共同构成跨端契约。更改帧格式、采样率、量程码、轴向、标签枚举或 manifest 字段时，需要同步更新两端、相关测试和说明文档；不得在 `recv.py`、绘图脚本或训练脚本中复制另一份定义。

验证入口位于上级目录：`test_metadata.py` 检查 schema 与 CSV/manifest 行为，`test_harmonics.py` 检查频谱分析，`recv.py` 负责实际串口接收。
