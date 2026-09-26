#ifndef _USART_H
#define _USART_H

#include "stdio.h"
#include "./SYSTEM/sys/sys.h"

#define USART_TX_GPIO_PORT              GPIOA
#define USART_TX_GPIO_PIN               GPIO_PIN_9
#define USART_TX_GPIO_AF                GPIO_AF7_USART1
#define USART_TX_GPIO_CLK_ENABLE()      do{ __HAL_RCC_GPIOA_CLK_ENABLE(); }while(0)
#define USART_RX_GPIO_PORT              GPIOA
#define USART_RX_GPIO_PIN               GPIO_PIN_10
#define USART_RX_GPIO_AF                GPIO_AF7_USART1
#define USART_RX_GPIO_CLK_ENABLE()      do{ __HAL_RCC_GPIOA_CLK_ENABLE(); }while(0)
#define USART_UX                        USART1
#define USART_UX_IRQn                   USART1_IRQn
#define USART_UX_IRQHandler             USART1_IRQHandler
#define USART_UX_CLK_ENABLE()           do{ __HAL_RCC_USART1_CLK_ENABLE(); }while(0)

#define USART_REC_LEN           200U
#define USART_EN_RX             1U
#define RXBUFFERSIZE            1U
#define USART_TX_QUEUE_DEPTH    4U
#define USART_TX_MAX_LEN        2100U

extern UART_HandleTypeDef g_uart1_handle;
extern uint8_t  g_usart_rx_buf[USART_REC_LEN];
extern uint16_t g_usart_rx_sta;
extern uint8_t  g_rx_buffer[RXBUFFERSIZE];

void usart_init(uint32_t baudrate);
uint8_t usart_tx_enqueue(const uint8_t *data, uint16_t len);
uint16_t usart_tx_dropped(void);
uint16_t usart_tx_errors(void);

#endif
