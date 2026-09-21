/*
    文件：iic.h
    功能：IIC驱动代码
    
*/
#ifndef IIC_H
#define IIC_H

#include "./SYSTEM/sys/sys.h"


/******************************************************************************************/
/* 引脚 定义 */

#define IIC_SCL_GPIO_PORT               GPIOB
#define IIC_SCL_GPIO_PIN                GPIO_PIN_6      //IIC时钟线定义输出口
#define IIC_SCL_GPIO_CLK_ENABLE()       do{ __HAL_RCC_GPIOB_CLK_ENABLE(); }while(0)   /* PB口时钟使能 */

#define IIC_SDA_GPIO_PORT               GPIOB
#define IIC_SDA_GPIO_PIN                GPIO_PIN_7      //IIC数据线定义输出口
#define IIC_SDA_GPIO_CLK_ENABLE()       do{ __HAL_RCC_GPIOB_CLK_ENABLE(); }while(0)   /* PB口时钟使能 */

/******************************************************************************************/

/******************************************************************************************/
/* IO 操作设定 */

#define IIC_SCL(x)        do{ x ? \
                              HAL_GPIO_WritePin(IIC_SCL_GPIO_PORT, IIC_SCL_GPIO_PIN, GPIO_PIN_SET) : \
                              HAL_GPIO_WritePin(IIC_SCL_GPIO_PORT, IIC_SCL_GPIO_PIN, GPIO_PIN_RESET); \
                          }while(0)       //设定 时钟线 的高低电平：x=1为高电平；x=0为低电平

#define IIC_SDA(x)        do{ x ? \
                              HAL_GPIO_WritePin(IIC_SDA_GPIO_PORT, IIC_SDA_GPIO_PIN, GPIO_PIN_SET) : \
                              HAL_GPIO_WritePin(IIC_SDA_GPIO_PORT, IIC_SDA_GPIO_PIN, GPIO_PIN_RESET); \
                          }while(0)       //设定 数据线 的高低电平：x=1为高电平；x=0为低电平

#define IIC_READ_SDA     HAL_GPIO_ReadPin(IIC_SDA_GPIO_PORT, IIC_SDA_GPIO_PIN) /* 读取数据 */

/******************************************************************************************/


/******************************************************************************************/
/* 函数 定义 */

void iic_init(void);            /* 初始化IIC的IO口 */
void iic_start(void);           /* 发送IIC开始信号 */
void iic_stop(void);            /* 发送IIC停止信号 */
uint8_t iic_wait_ack(void);     /* IIC等待ACK信号 */
void iic_ack(void);             /* IIC发送ACK信号 */
void iic_nack(void);            /* IIC不发送ACK信号 */
void iic_send_byte(uint8_t txd);/* IIC发送一个字节 */
uint8_t iic_read_byte(unsigned char ack);/* IIC读取一个字节 */

uint8_t iic_reg_write(uint8_t dev_addr, uint8_t reg_addr, uint8_t data);                            //向一个寄存器写入数据
uint8_t iic_reg_read_length(uint8_t dev_addr, uint8_t reg_addr, uint8_t *buf, uint16_t length);    //读取指定长度的数据

/******************************************************************************************/

#endif
