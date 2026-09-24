---
kb_id: PROJECT-USMART
kind: reference
domain: firmware
lifecycle: current
authority: supporting
last_verified: 2026-09-24
migration_source: C:/Work/备份/电机振动故障检测/_Obsidian迁移前/_20260924/电机振动故障检测_项目规划.md
---

# 调试组件：USMART


## 1. 当前使用边界

USMART 只是可选调试组件，不能据原文推定已启用。当前采样使用 TIM3，串口链路使用 USART1 460800；启用或移除必须以当前源码和编译结果为证。


## 2. 组件说明

> **一句话**：USMART 是正点原子写的**串口命令行组件**——把 STM32 当成一台"可以敲命令调函数"的机器：在电脑串口助手（XCOM/SSCOM）里输入 `函数名(参数)`，固件真的去调用工程里**已登记**的那个函数，并把**返回值**和**执行耗时**打印回来；全程不用改代码、不用重新编译烧录。
> 
> **本项目定位**：**调试期工具，不是交付功能**。它的价值集中在"验通 IIC/MPU6050 + 量单次读取耗时"；结档或做演示版时可按 移除清单 的清单整组移除，不影响主线（相关页面 的 D1–D14 进度也不依赖它）。
> 
> **它从哪来**：跟着正点原子 IIC 例程一起拷贝进 `00_工程文件/Middlewares/USMART/`（本工程已带，且已加进 Keil 工程组的 `Middlewares/USMART` 分组）。

### 2.1 文件分工

| 文件                 | 干什么                                                                                                                                                                                                                                                                                          | 关键看点                                                                     |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `usmart.c`         | **组件主体**，一条命令的三段式：`usmart_scan()` 看串口有没有新命令 → `usmart_cmd_rec()` 把 `lcd_fill(0,0,10,10,0xF800)` 切出函数名、到函数表里逐个比对、解析参数 → `usmart_exe()` 按参数个数把参数强制转成对应类型后调用函数指针，并打印"函数名(参数)=返回值"。另外实现 help/list/id/hex/dec/runtime 五条系统指令，以及 `read_addr()`/`write_addr()`（直接读/写任意地址，等于一个极简调试器）                 | `usmart_exe()` 里的 `switch (usmart_dev.pnum)`；`usmart_sys_cmd_exe()` 的指令表 |
| `usmart.h`         | 对外接口与数据结构：`_m_usmart_nametab`（函数表项＝函数指针＋名字串）、`_m_usmart_dev`（控制管理器：函数数量、当前函数 ID、参数个数、显示进制、计时标志）、5 个错误码（函数错误/参数错误/参数太多/未找到函数）                                                                                                                                                                 | `usmart_nametab[]` 与 `usmart_dev` 的 extern 声明                            |
| `usmart_str.c/.h`  | **字符串解析工具**：`usmart_get_fname()` 切出函数名和参数个数、`usmart_get_fparam()` 切出所有参数、`usmart_str2num()` 字符串转数字（支持 10/16 进制、负数）、`usmart_strcmp()` 比较                                                                                                                                                      | 只有它碰字符串，与硬件无关                                                            |
| `usmart_port.c/.h` | **移植层**——凡与具体芯片/串口/定时器相关的都在这，换平台只改这个文件：`usmart_get_input_string()` 从 `usart.c` 的 `g_usart_rx_buf`/`g_usart_rx_sta` 取"一行（回车换行结尾）"；用 **TIM4 定时中断**周期调用 `usmart_scan()`，同时为 runtime 计时；配置宏 `USMART_ENTIMX_SCAN`、`USMART_USE_HELP`、`USMART_USE_WRFUNS`、`MAX_PARM`、`PARM_LEN`、`USMART_PRINTF` 也在这 | `USMART_TIMX_*` 四个宏（换定时器只改这 4 行）                                         |
| `usmart_config.c`  | **唯一需要你自己改的文件**：函数表 `usmart_nametab[]` 里登记"允许被串口调用"的函数（函数指针 + 名字串），以及 `usmart_dev` 结构体初始化                                                                                                                                                                                                    | 每次新增可调函数都改这里                                                             |

> 小知识：TIM4 的中断服务函数名就叫 `TIM4_IRQHandler`（定义在 `usmart_port.c`），与启动文件 `startup_stm32f407xx.s` 的向量表天然对齐，**不需要**再去 `stm32f4xx_it.c` 里写一遍。

> ⚠️ **现状提醒**：`usmart_config.c` 里仍登记着 `at24cxx_read_one_byte` / `at24cxx_write_one_byte`，也仍 `#include "./BSP/24CXX/24cxx.h"`。而 24CXX 驱动已从工程移除，于是链接期报 `L6218E: Undefined symbol at24cxx_read_one_byte (referred from usmart_config.o)`。**要么删掉这两行和那句 include，要么把 24cxx.c 加回工程**——决定留用 USMART 就必须先处理这一处（详见 相关页面 的工程清理类记录）。

### 2.2 启动方式

```c
/* main.c 里一句初始化，就接上了 */
usmart_dev.init(84);        /* 84 = TIM4 所在总线的时钟频率(MHz)，用于把定时器配成 0.1ms 计时基准 */
```

调用方向：串口助手 → `usart.c` 的中断把整行存进 `g_usart_rx_buf` 并置完成标志 → TIM4 中断里 `usmart_scan()` 取走该行 → 解析 → 执行 → `printf` 回显结果。

电脑端：**波特率 115200**，用 XCOM/SSCOM，**输入以回车换行结束**（`\r\n`）；串口须接板载 USB_UART，并把 PA9/PA10 的跳线帽接上（见工程根目录官方 readme 的注意事项）。

### 2.3 常用输入

| 输入                                                | 作用 / 现象                                                            |
| ------------------------------------------------- | ------------------------------------------------------------------ |
| `help`                                            | 打印帮助                                                               |
| `list`                                            | 列出 `usmart_config.c` 里登记过的所有函数（**能不能调，先看这张表**）                     |
| `id`                                              | 显示函数表信息（函数数量等）                                                     |
| `delay_ms(500)`                                   | 真的延时 500ms，并在串口回显这次调用；无返回值函数的"=数字"是无意义的，别当真                        |
| `delay_us(100)`                                   | 同上，微秒级                                                             |
| `lcd_clear(0xFFFF)`                               | 表里登记过的 LCD 函数可被直接调用，屏幕上立刻出效果                                       |
| `lcd_show_string(30,50,200,16,16,"HELLO",0xF800)` | 同上，字符串参数用双引号；参数个数与顺序必须与函数原型一致                                      |
| `runtime 1`                                       | 打开函数计时；之后每次调用都多打印一行 `Function Run Time:x.xms`（0.1ms 分辨率，靠 TIM4 计时） |
| `runtime 0`                                       | 关闭计时                                                               |
| `hex` / `hex 100`                                 | 切换参数按 16 进制显示；`hex 100` 顺带做进制转换（回 `HEX:0X64`）                      |
| `dec` / `dec 0x64`                                | 切换参数按 10 进制显示；`dec 0x64` 回 `DEC:100`                               |
| `read_addr(0x20000000)`                           | 读该地址的 32 位值（需 `USMART_USE_WRFUNS=1`，本工程已开）                         |
| `write_addr(0x20000000,0x12345678)`               | 往该地址写 32 位值（**慎用**：写错地址当场跑飞，写寄存器前先查手册）                             |
| `mpu6050_read_id()`                               | **（待你实现后在 `usmart_config.c` 登记）** 验通 IIC 最省事的办法                    |

规则补充：单个函数最多 10 个参数；参数支持 10/16 进制、负数、字符串；函数名必须与 `usmart_config.c` 里登记的名字串**完全一致**，且输入参数个数不能少于原型参数个数，否则回 `未找到匹配的函数!` 或 `参数错误!`。

### 2.4 调试价值

在 `usmart_config.c` 里登记自己写的函数，例如：

```c
#include "./BSP/IIC/iic.h"
#include "./BSP/MPU6050/mpu6050.h"

struct _m_usmart_nametab usmart_nametab[] =
{
    /* …原有的 delay_ms / lcd_* 等条目… */
    (void *)iic_init,           "void iic_init(void)",
    (void *)mpu6050_init,       "void mpu6050_init(void)",
    (void *)mpu6050_read_id,    "uint8_t mpu6050_read_id(void)",
    (void *)mpu6050_read_accel, "void mpu6050_read_accel(void)",
};
```

即可在串口里反复 `mpu6050_read_id()` 验通 IIC，再用 `runtime 1` + `mpu6050_read_accel()` 直接量出"读一帧加速度要多少 ms"——这正是后面估算**采样率上限**、判断 IIC 速度够不够 1 kHz 采样（相关页面 / 相关页面）时需要的第一手数字，比反复烧录快得多。

### 2.5 代价

- 占 **Flash 约 4 KB+**（`USMART_USE_HELP=1` 时帮助文本近 700 B；把该宏改 0 可省）；
- **独占 TIM4**，中断优先级被设成 (3,3)——若后期主线要用 TIM4 做采样节拍，必须改宏换定时器或直接移除；
- `usmart.c` 是 **GBK 编码**，AC6 下会报 `-Winvalid-source-encoding` 警告；`usmart_exe()` 的函数指针强转必然触发 `-Wdeprecated-non-prototype`。**两者都无害**，但会和真正的警告混在一起，容易误判；
- 属于正点原子生态的便利工具，不是通用做法，**不算简历加分项**。

### 2.6 移除清单

1. Keil 里移除 `Middlewares/USMART` 整个分组（右键 → Remove Group）；
2. 删磁盘上的 `Middlewares/` 文件夹（含 `USMART` 子目录）；
3. `User/main.c` 删除 `usmart_dev.init(84);` 与 `#include "./USMART/usmart.h"`；
4. 工程 Options for Target → C/C++ → Include Paths 中删掉 `..\..\Middlewares`；
5. 全局搜索确认再无 `#include "./USMART/usmart.h"`（`usmart_config.c` 会随文件夹一起删，但要确认没有别的文件引用它）。

> 对照检查：删完后再全编译一次，应无 `Undefined symbol usmart_*`；`Output/` 里的 `usmart*.o/.crf` 是历史产物，双击 `keilkill.bat` 清掉即可。

---




