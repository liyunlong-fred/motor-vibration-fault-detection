/* app_debug.c */
#include "app_debug.h"
#include "app_config.h"      /* LINK_TEXT_MAX 不在里面也没关系, 下面 include link_frame.h */
#include "link_frame.h"
#include <stdio.h>
#include <stdarg.h>

#define APP_LOG_VIA_FRAME   1    /* 1=日志走文本帧(串口上只有帧); 0=退回裸 printf(应急/临时用串口助手看) */

void app_log(const char *fmt, ...)
{
    char    buf[LINK_TEXT_MAX + 1];
    va_list ap;
    int     n;

    if (fmt == 0) { return; }

    va_start(ap, fmt);                                  /* 取得可变参数列表 */
    n = vsnprintf(buf, sizeof(buf), fmt, ap);           /* 格式化到 buf, 自动留 '\0' */
    va_end(ap);

    if (n < 0) { return; }                              /* 格式化失败 */
    if (n > (int)LINK_TEXT_MAX) { n = (int)LINK_TEXT_MAX; }   /* 返回值是"想写的长度", 必须自己截断 */

    while ((n > 0) && ((buf[n - 1] == '\r') || (buf[n - 1] == '\n'))) { n--; }  /* 去掉结尾换行 */
    buf[n] = '\0';

#if APP_LOG_VIA_FRAME
    link_text_send(buf);
#else
    printf("%s\r\n", buf);
#endif
}