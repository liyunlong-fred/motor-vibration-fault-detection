#ifndef __LINK_FRAME_H
#define __LINK_FRAME_H

#include "app_config.h"
#include "app_sample.h"

/* Common header (offset 0..8): 0x5A5A, type, axis, seq, n, AFS code.
 * Acceleration frames append a 32-bit first_sample_id before int16 payload.
 * Text frames retain the nine-byte common header. */
#define LINK_FRAME_HEAD         0x5A5AU
#define LINK_FRAME_TYPE_ACCEL   1U
#define LINK_FRAME_TYPE_TEXT    2U
#define LINK_TEXT_OVERHEAD      9U
#define LINK_ACCEL_OVERHEAD     13U
#define LINK_FRAME_MAX_LEN      (LINK_ACCEL_OVERHEAD + 2U * APP_FRAME_N)
#define LINK_TEXT_MAX           96U
#define LINK_ACCEL_FS_CODE      MPU6050_ACCEL_FS_SEL

uint16_t link_frame_pack(const sample_window_t *w, uint8_t axis, uint8_t *out);
uint8_t  link_frame_send(const sample_window_t *w, uint8_t axis);
uint16_t link_text_pack(const char *s, uint8_t *out);
uint8_t  link_text_send(const char *s);

#endif
