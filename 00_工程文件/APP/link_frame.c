#include "link_frame.h"
#include "./SYSTEM/usart/usart.h"

static const int16_t *frame_axis_data(const sample_window_t *w, uint8_t axis)
{
    switch (axis)
    {
        case 'X': return w->x;
        case 'Y': return w->y;
        case 'Z': return w->z;
        default: return 0;
    }
}

uint16_t link_frame_pack(const sample_window_t *w, uint8_t axis, uint8_t *out)
{
    const int16_t *src;
    uint16_t i, idx = 0U, n;

    if ((w == 0) || (out == 0)) return 0U;
    src = frame_axis_data(w, axis);
    if (src == 0) return 0U;
    n = w->n;
    if ((n == 0U) || (n > APP_FRAME_N)) return 0U;

    out[idx++] = (uint8_t)(LINK_FRAME_HEAD >> 8);
    out[idx++] = (uint8_t)(LINK_FRAME_HEAD & 0xFFU);
    out[idx++] = LINK_FRAME_TYPE_ACCEL;
    out[idx++] = axis;
    out[idx++] = (uint8_t)(w->seq & 0xFFU);
    out[idx++] = (uint8_t)(w->seq >> 8);
    out[idx++] = (uint8_t)(n & 0xFFU);
    out[idx++] = (uint8_t)(n >> 8);
    out[idx++] = (uint8_t)LINK_ACCEL_FS_CODE;
    out[idx++] = (uint8_t)(w->first_sample_id & 0xFFUL);
    out[idx++] = (uint8_t)((w->first_sample_id >> 8) & 0xFFUL);
    out[idx++] = (uint8_t)((w->first_sample_id >> 16) & 0xFFUL);
    out[idx++] = (uint8_t)((w->first_sample_id >> 24) & 0xFFUL);

    for (i = 0U; i < n; i++)
    {
        out[idx++] = (uint8_t)((uint16_t)src[i] & 0xFFU);
        out[idx++] = (uint8_t)(((uint16_t)src[i] >> 8) & 0xFFU);
    }
    return idx;
}

uint8_t link_frame_send(const sample_window_t *w, uint8_t axis)
{
    static uint8_t buf[LINK_FRAME_MAX_LEN];
    uint16_t len = link_frame_pack(w, axis, buf);
    if (len == 0U) return 1U;
    return usart_tx_enqueue(buf, len);
}

static uint16_t g_text_seq;

uint16_t link_text_pack(const char *s, uint8_t *out)
{
    uint16_t i, n = 0U;
    if ((s == 0) || (out == 0)) return 0U;
    while ((s[n] != '\0') && (n < LINK_TEXT_MAX)) n++;
    if (n == 0U) return 0U;

    out[0] = (uint8_t)(LINK_FRAME_HEAD >> 8);
    out[1] = (uint8_t)(LINK_FRAME_HEAD & 0xFFU);
    out[2] = LINK_FRAME_TYPE_TEXT;
    out[3] = 0U;
    out[4] = (uint8_t)(g_text_seq & 0xFFU);
    out[5] = (uint8_t)(g_text_seq >> 8);
    out[6] = (uint8_t)(n & 0xFFU);
    out[7] = (uint8_t)(n >> 8);
    out[8] = 0U;
    for (i = 0U; i < n; i++) out[LINK_TEXT_OVERHEAD + i] = (uint8_t)s[i];
    g_text_seq++;
    return (uint16_t)(LINK_TEXT_OVERHEAD + n);
}

uint8_t link_text_send(const char *s)
{
    static uint8_t buf[LINK_TEXT_OVERHEAD + LINK_TEXT_MAX];
    uint16_t len = link_text_pack(s, buf);
    if (len == 0U) return 1U;
    return usart_tx_enqueue(buf, len);
}
