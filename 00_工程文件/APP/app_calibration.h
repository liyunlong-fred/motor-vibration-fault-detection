#ifndef __APP_CALIBRATION_H
#define __APP_CALIBRATION_H

/*
 * Static six-face calibration aid.  Set to 1 only while the sensor is
 * stationary for calibration.  Each completed capture window then emits a
 * CAL_MEAN text frame with X/Y/Z mean raw counts.
 */
#define APP_CALIBRATION_MEAN_LOG  1

#if APP_CALIBRATION_MEAN_LOG && !APP_DEBUG
#error "APP_CALIBRATION_MEAN_LOG requires APP_DEBUG=1"
#endif

#endif
