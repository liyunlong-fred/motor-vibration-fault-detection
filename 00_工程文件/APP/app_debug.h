/* app_debug.h */
#ifndef __APP_DEBUG_H
#define __APP_DEBUG_H

/**
 * @brief       日志输出: 把格式化后的文本打成 type=2 文本帧从串口1发出
 *              用法与 printf 完全相同: app_log("f=%lu mg\r\n", (unsigned long)v);
 */
void app_log(const char *fmt, ...);

#endif