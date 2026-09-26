#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include <string.h>

#if SYS_SUPPORT_OS
#include "os.h"
#endif

#if (__ARMCC_VERSION >= 6010050)
__asm(".global __use_no_semihosting\n\t");
__asm(".global __ARM_use_no_argv \n\t");
#else
#pragma import(__use_no_semihosting)
struct __FILE { int handle; };
#endif

int _ttywrch(int ch) { return ch; }
void _sys_exit(int x) { (void)x; }
char *_sys_command_string(char *cmd, int len) { (void)cmd; (void)len; return NULL; }
FILE __stdout;

/* Only retained for early boot diagnostics. Runtime logging uses TX DMA queue. */
int fputc(int ch, FILE *f)
{
    (void)f;
    while ((USART1->SR & USART_SR_TC) == 0U) {}
    USART1->DR = (uint8_t)ch;
    return ch;
}

uint8_t g_usart_rx_buf[USART_REC_LEN];
uint16_t g_usart_rx_sta;
uint8_t g_rx_buffer[RXBUFFERSIZE];
UART_HandleTypeDef g_uart1_handle;

static DMA_HandleTypeDef g_uart1_tx_dma;
static uint8_t g_tx_data[USART_TX_QUEUE_DEPTH][USART_TX_MAX_LEN];
static uint16_t g_tx_len[USART_TX_QUEUE_DEPTH];
static volatile uint8_t g_tx_head;
static volatile uint8_t g_tx_tail;
static volatile uint8_t g_tx_count;
static volatile uint8_t g_tx_busy;
static volatile uint16_t g_tx_dropped;
static volatile uint16_t g_tx_error_count;

static void usart_tx_start_next(void)
{
    while (g_tx_count != 0U)
    {
        g_tx_busy = 1U;
        if (HAL_UART_Transmit_DMA(&g_uart1_handle, g_tx_data[g_tx_tail],
                                  g_tx_len[g_tx_tail]) == HAL_OK)
        {
            return;
        }
        g_tx_error_count++;
        g_tx_tail = (uint8_t)((g_tx_tail + 1U) % USART_TX_QUEUE_DEPTH);
        g_tx_count--;
        g_tx_busy = 0U;
    }
    g_tx_busy = 0U;
}

uint8_t usart_tx_enqueue(const uint8_t *data, uint16_t len)
{
    uint8_t slot;
    uint32_t primask;

    if ((data == 0) || (len == 0U) || (len > USART_TX_MAX_LEN)) return 1U;

    /* The producer is main context.  Copy before publishing the slot to DMA ISR. */
    if (g_tx_count >= USART_TX_QUEUE_DEPTH)
    {
        g_tx_dropped++;
        return 1U;
    }
    slot = g_tx_head;
    memcpy(g_tx_data[slot], data, len);

    primask = __get_PRIMASK();
    __disable_irq();
    if (g_tx_count >= USART_TX_QUEUE_DEPTH)
    {
        g_tx_dropped++;
        if (primask == 0U) __enable_irq();
        return 1U;
    }
    g_tx_len[slot] = len;
    g_tx_head = (uint8_t)((g_tx_head + 1U) % USART_TX_QUEUE_DEPTH);
    g_tx_count++;
    if (g_tx_busy == 0U) usart_tx_start_next();
    if (primask == 0U) __enable_irq();
    return 0U;
}

uint16_t usart_tx_dropped(void) { return g_tx_dropped; }
uint16_t usart_tx_errors(void) { return g_tx_error_count; }

void usart_init(uint32_t baudrate)
{
    g_uart1_handle.Instance = USART_UX;
    g_uart1_handle.Init.BaudRate = baudrate;
    g_uart1_handle.Init.WordLength = UART_WORDLENGTH_8B;
    g_uart1_handle.Init.StopBits = UART_STOPBITS_1;
    g_uart1_handle.Init.Parity = UART_PARITY_NONE;
    g_uart1_handle.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    g_uart1_handle.Init.Mode = UART_MODE_TX_RX;
    HAL_UART_Init(&g_uart1_handle);
    HAL_UART_Receive_IT(&g_uart1_handle, g_rx_buffer, RXBUFFERSIZE);
}

void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
    GPIO_InitTypeDef gpio;
    if (huart->Instance != USART_UX) return;

    USART_UX_CLK_ENABLE();
    USART_TX_GPIO_CLK_ENABLE();
    USART_RX_GPIO_CLK_ENABLE();
    gpio.Pin = USART_TX_GPIO_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_PULLUP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Alternate = USART_TX_GPIO_AF;
    HAL_GPIO_Init(USART_TX_GPIO_PORT, &gpio);
    gpio.Pin = USART_RX_GPIO_PIN;
    gpio.Alternate = USART_RX_GPIO_AF;
    HAL_GPIO_Init(USART_RX_GPIO_PORT, &gpio);

    __HAL_RCC_DMA2_CLK_ENABLE();
    g_uart1_tx_dma.Instance = DMA2_Stream7;
    g_uart1_tx_dma.Init.Channel = DMA_CHANNEL_4;
    g_uart1_tx_dma.Init.Direction = DMA_MEMORY_TO_PERIPH;
    g_uart1_tx_dma.Init.PeriphInc = DMA_PINC_DISABLE;
    g_uart1_tx_dma.Init.MemInc = DMA_MINC_ENABLE;
    g_uart1_tx_dma.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    g_uart1_tx_dma.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    g_uart1_tx_dma.Init.Mode = DMA_NORMAL;
    g_uart1_tx_dma.Init.Priority = DMA_PRIORITY_LOW;
    g_uart1_tx_dma.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
    (void)HAL_DMA_Init(&g_uart1_tx_dma);
    __HAL_LINKDMA(huart, hdmatx, g_uart1_tx_dma);

    HAL_NVIC_SetPriority(USART_UX_IRQn, 3, 3);
    HAL_NVIC_EnableIRQ(USART_UX_IRQn);
    HAL_NVIC_SetPriority(DMA2_Stream7_IRQn, 3, 2);
    HAL_NVIC_EnableIRQ(DMA2_Stream7_IRQn);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART_UX) return;
    if ((g_usart_rx_sta & 0x8000U) == 0U)
    {
        if (g_usart_rx_sta & 0x4000U)
        {
            if (g_rx_buffer[0] != 0x0AU) g_usart_rx_sta = 0U;
            else g_usart_rx_sta |= 0x8000U;
        }
        else if (g_rx_buffer[0] == 0x0DU)
        {
            g_usart_rx_sta |= 0x4000U;
        }
        else
        {
            g_usart_rx_buf[g_usart_rx_sta & 0x3FFFU] = g_rx_buffer[0];
            g_usart_rx_sta++;
            if (g_usart_rx_sta > (USART_REC_LEN - 1U)) g_usart_rx_sta = 0U;
        }
    }
    HAL_UART_Receive_IT(&g_uart1_handle, g_rx_buffer, RXBUFFERSIZE);
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART_UX) return;
    if (g_tx_count != 0U)
    {
        g_tx_tail = (uint8_t)((g_tx_tail + 1U) % USART_TX_QUEUE_DEPTH);
        g_tx_count--;
    }
    g_tx_busy = 0U;
    usart_tx_start_next();
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    uint32_t error;
    if (huart->Instance != USART_UX) return;
    error = HAL_UART_GetError(huart);
    g_tx_error_count++;

    /* RX line errors must not discard a DMA-owned TX frame. */
    if ((error & HAL_UART_ERROR_DMA) != 0U)
    {
        if (g_tx_busy != 0U && g_tx_count != 0U)
        {
            g_tx_tail = (uint8_t)((g_tx_tail + 1U) % USART_TX_QUEUE_DEPTH);
            g_tx_count--;
        }
        g_tx_busy = 0U;
        usart_tx_start_next();
    }
    else
    {
        HAL_UART_Receive_IT(&g_uart1_handle, g_rx_buffer, RXBUFFERSIZE);
    }
}

void DMA2_Stream7_IRQHandler(void)
{
    HAL_DMA_IRQHandler(&g_uart1_tx_dma);
}

void USART_UX_IRQHandler(void)
{
#if SYS_SUPPORT_OS
    OSIntEnter();
#endif
    HAL_UART_IRQHandler(&g_uart1_handle);
#if SYS_SUPPORT_OS
    OSIntExit();
#endif
}
