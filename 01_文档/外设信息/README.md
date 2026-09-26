---
kb_id: HARDWARE-REFERENCE-GUIDE
kind: reference
domain: hardware
lifecycle: current
authority: reference
last_verified: 2026-09-25
source_paths:
  - 01_文档/外设信息/MPU6050寄存器选用表_电机振动检测.xlsx
  - 01_文档/外设信息/GY521mpu-6050资料/RM-MPU-6000A.pdf
  - 01_文档/外设信息/GY521mpu-6050资料/PS-MPU-6000A.pdf
---

# 外设信息与参考资料

本目录保存 MPU6050/GY-521 的项目速查资料和本地供应商/社区参考包。

- `MPU6050寄存器选用表_电机振动检测.xlsx`：项目使用的寄存器、位域和配置值速查表；变更前应同时对照当前 `00_工程文件/Drivers/BSP/MPU6050/mpu6050.h`。
- `GY521mpu-6050资料/`：本地参考 PDF、历史示例与第三方工程。它在 `.gitignore` 中作为本地参考资料保留，不参与当前工程构建，也不要批量修改或重排其内部目录。

当前项目硬件事实以源码和 [系统地图](../../知识库/20_系统地图.md) 为准：MPU6050 使用软件 IIC（PB6/PB7）、加速度量程为 ±2 g；X 是测量轴、Y 是重力轴。参考包与示例的芯片型号、接线、库版本或数据格式可能不同，只能作为查阅线索，不能直接当作当前实现。
