#include "link_frame.h"
#include "./SYSTEM/usart/usart.h"

/**
 * @brief       按轴号选中对应的一路数据数组
 * @param       w    ：一窗数据地址（只读）
 * @param       axis ：轴号，'X' / 'Y' / 'Z'
 * @retval      指向该轴 int16 数据首元素的指针；轴号非法时返回 0（空指针）
 */
static const int16_t *frame_axis_data(const sample_window_t *w, uint8_t axis)
{
    switch (axis)
    {
        case 'X': return w->x;
        case 'Y': return w->y;
        case 'Z': return w->z;
        default:  return 0;     /* 非法轴号: 返回空指针, 调用者必须先判空再使用 */
    }
}

/**
 * @brief       按帧格式把一窗数据打包成字节流（整条链路只传 int16 原始计数）
 * @param       w    ：待打包的一窗数据地址（只读）
 * @param       axis ：轴号，'X' / 'Y' / 'Z'
 * @param       out  ：输出缓冲区地址，容量不得小于 LINK_FRAME_MAX_LEN
 * @retval      帧总长度（字节）= 9 + 2n；参数非法时返回 0（0 不是合法帧长）
 */
uint16_t link_frame_pack(const sample_window_t *w, uint8_t axis, uint8_t *out)
{
    const int16_t *src;                 /* 该轴数据源 */
    uint16_t i, idx = 0, n;

    if ((w == 0) || (out == 0))          { return 0; }       /* 入参判空: 空指针解引用会直接返回 0 报错 */
    
    src = frame_axis_data(w, axis);                          /* 选中该轴的数据源 */
    
    if (src == 0)                        { return 0; }       /* 轴号非法: 必须在写任何字节之前退出 */
    
    n = w->n;                                                /* 本窗有效样本数（w 先判空，在解引用） */
    
    if ((n == 0) || (n > APP_FRAME_N))   { return 0; }       /* 样本数异常: 防越界读、防 out 缓冲区越界写 */
    

    /* ---- 帧头 ---- */
    out[idx++] = (uint8_t)(LINK_FRAME_HEAD >> 8);       /* 0x5A */
    out[idx++] = (uint8_t)(LINK_FRAME_HEAD >> 8);       /* 0x5A */

    /* ---- 类型 + 轴号 ---- */
    out[idx++] = LINK_FRAME_TYPE_ACCEL;
    out[idx++] = axis;

    /* ---- 窗序号、样本数(小端: 低字节在前) ---- */
    out[idx++] = (uint8_t)(w->seq & 0xFF);
    out[idx++] = (uint8_t)(w->seq >> 8);
    out[idx++] = (uint8_t)(n & 0xFF);
    out[idx++] = (uint8_t)(n >> 8);

    /* ---- 量程码: 将传感器使用的量程一并打包送给 PC 端 ---- */
    out[idx++] = (uint8_t)LINK_ACCEL_FS_CODE;

    /* ---- 原始数据: int16 小端 ---- */
    for (i = 0; i < n; i++)
    {
        out[idx++] = (uint8_t)((uint16_t)src[i] & 0xFF);         /* 低字节 */  /* src[i] = *(src + i) 代表计算地址偏移后再取出数据 */
        out[idx++] = (uint8_t)(((uint16_t)src[i] >> 8) & 0xFF);  /* 高字节 */
    }

    return idx;                     /* 返回帧长度（单位字节），idx= 9 + 2n */
}

/**
 * @brief       打包一窗数据并通过串口1发出
 * @param       w    ：待发送的一窗数据地址（只读）
 * @param       axis ：轴号，'X' / 'Y' / 'Z'
 * @retval      0, 成功; 1, 失败（打包失败 或 串口发送失败）
 */
uint8_t link_frame_send(const sample_window_t *w, uint8_t axis)
{
    static uint8_t buf[LINK_FRAME_MAX_LEN];     /* 必须 static: 2057 字节放栈上会溢出 */
    uint16_t len = link_frame_pack(w, axis, buf);

    if (len == 0)    { return 1; }              /* 打包失败: 不拿去发送 */

    if (HAL_UART_Transmit(&g_uart1_handle, buf, len, 1000) != HAL_OK)       /* 错误会返回 HAL_ERROR = 1 */
    {
        return 1;                               /* 发送超时或失败 */
    }
    return 0;
}

