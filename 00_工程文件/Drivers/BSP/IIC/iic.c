/*
    文件：iic.
    功能：IIC驱动代码
    
*/

#include "./BSP/IIC/iic.h"
#include "./SYSTEM/delay/delay.h"


/**
 * @brief       初始化IIC
 * @param       无
 * @retval      无
 */

void iic_init(void)
{
    
    GPIO_InitTypeDef gpio_init_struct_SCL;/* 定义SCL的GPIO配置结构体 */
    GPIO_InitTypeDef gpio_init_struct_SDA;/* 定义SDA的GPIO配置结构体 */
    
    IIC_SCL_GPIO_CLK_ENABLE();  /* SCL引脚时钟使能 */
    IIC_SDA_GPIO_CLK_ENABLE();  /* SDA引脚时钟使能 */

    //GPIO配置详情
    //——————————————————————————————
        //时钟线配置：
    gpio_init_struct_SCL.Pin = IIC_SCL_GPIO_PIN;
    gpio_init_struct_SCL.Mode = GPIO_MODE_OUTPUT_PP;        /* 推挽输出 */
    gpio_init_struct_SCL.Pull = GPIO_PULLUP;                /* 上拉 */
    gpio_init_struct_SCL.Speed = GPIO_SPEED_FREQ_VERY_HIGH; /* 快速 */

        //数据线配置
    gpio_init_struct_SDA.Pin = IIC_SDA_GPIO_PIN;
    gpio_init_struct_SDA.Mode = GPIO_MODE_OUTPUT_OD;        /* 开漏输出 */
    //——————————————————————————————
    
    //配置完成后，启用初始化函数
    HAL_GPIO_Init(IIC_SCL_GPIO_PORT, &gpio_init_struct_SCL);/* SCL */
    HAL_GPIO_Init(IIC_SDA_GPIO_PORT, &gpio_init_struct_SDA);/* SDA */
    
    /* SDA引脚模式设置,开漏输出,上拉, 这样就不用再设置IO方向了,
    开漏输出的时候(=1), 也可以读取外部信号的高低电平 */

    iic_stop();     /* 停止总线上所有设备 */
    
}

//————————————————————时序与字节操作————————————————————

/**
 * @brief       IIC延时函数,用于控制IIC读写速度
 * @param       无
 * @retval      无
 */

static void iic_delay(void)
{
    delay_us(2);    /* 2us的延时, 读写速度在250Khz以内 */
}


/**
 * @brief       产生IIC起始信号
 * @param       无
 * @retval      无
 */

void iic_start(void)
{
    IIC_SDA(1);
    IIC_SCL(1);
    iic_delay();
    IIC_SDA(0);     /* START信号: 当SCL为高时, SDA从高变成低, 表示起始信号 */
    iic_delay();
    IIC_SCL(0);     /* 钳住I2C总线，准备等待ACK应答、发送或接收数据 */
    iic_delay();
}


/**
 * @brief       产生IIC停止信号
 * @param       无
 * @retval      无
 */

void iic_stop(void)
{
    IIC_SDA(0);     /* STOP信号: 当SCL为高时, SDA从低变成高, 表示停止信号 */
    iic_delay();
    IIC_SCL(1);
    iic_delay();
    IIC_SDA(1);     /* 发送I2C总线结束信号 */
    iic_delay();
}


/**
 * @brief       等待应答信号到来
 * @param       无
 * @retval      1，接收应答失败
 *              0，接收应答成功
 */

uint8_t iic_wait_ack(void)
{
    uint8_t waittime = 0;
    uint8_t rack = 0;

    IIC_SDA(1);     /* 主机释放SDA线(此时外部器件可以拉低SDA线) */
    iic_delay();
    IIC_SCL(1);     /* SCL=1, 此时从机可以返回ACK */
    iic_delay();

    while (IIC_READ_SDA)    /* 等待应答 */
    {
        waittime++;

        if (waittime > 250)
        {
            iic_stop();
            rack = 1;
            break;
        }
    }

    IIC_SCL(0);     /* SCL=0, 结束ACK检查 */
    iic_delay();
    return rack;
}


/**
 * @brief       产生ACK应答
 * @param       无
 * @retval      无
 */
void iic_ack(void)
{
    IIC_SDA(0);     /* SCL 0 -> 1 时 SDA = 0,表示应答 */
    iic_delay();
    IIC_SCL(1);     /* 产生一个时钟 */
    iic_delay();
    IIC_SCL(0);
    iic_delay();
    IIC_SDA(1);     /* 主机释放SDA线 */
    iic_delay();
}


/**
 * @brief       不产生ACK应答
 * @param       无
 * @retval      无
 */
void iic_nack(void)
{
    IIC_SDA(1);     /* SCL 0 -> 1  时 SDA = 1,表示不应答 */
    iic_delay();
    IIC_SCL(1);     /* 产生一个时钟 */
    iic_delay();
    IIC_SCL(0);
    iic_delay();
}


/**
 * @brief       IIC发送一个字节
 * @param       data: 要发送的数据
 * @retval      无
 */
void iic_send_byte(uint8_t data)
{
    uint8_t t;
    
    for (t = 0; t < 8; t++)
    {
        IIC_SDA((data & 0x80) >> 7);    /* 高位先发送 */
        iic_delay();
        IIC_SCL(1);
        iic_delay();
        IIC_SCL(0);
        data <<= 1;     /* 左移1位,用于下一次发送 */
    }
    IIC_SDA(1);         /* 发送完成, 主机释放SDA线 */
}


/**
 * @brief       IIC读取一个字节
 * @param       ack:  传输结束后：ack=1时，发送ack; ack=0时，发送nack
 * @retval      接收到的数据
 */
uint8_t iic_read_byte(uint8_t ack)
{
    uint8_t i, receive = 0;

    for (i = 0; i < 8; i++ )    /* 接收1个字节数据 */
    {
        receive <<= 1;  /* 高位先输出,所以先收到的数据位要左移 */
        IIC_SCL(1);
        iic_delay();

        if (IIC_READ_SDA)
        {
            receive++;
        }
        
        IIC_SCL(0);
        iic_delay();
    }

    //一个字节传输结束，返回ack或者nack决定是否继续传输下一字节
    if (!ack)
    {
        iic_nack();     /* 发送nACK */
    }
    else
    {
        iic_ack();      /* 发送ACK */
    }

    return receive;
}

//————————————————————寄存器操作————————————————————

/**
 * @brief       将一个字节的数据写入指定寄存器地址
 * @param       dev_addr:写入设备地址(8位包含读写位)
 *              reg_addr:写入寄存器地址
 *              data    :待写入的一字节数据
 * @retval      0:写入成功
 *              1:写入失败
 */

uint8_t iic_reg_write(uint8_t dev_addr, uint8_t reg_addr, uint8_t data)
{
    iic_start();                                    //起始信号
    iic_send_byte(dev_addr & 0xFE);                 //发送设备地址（按位与去除最后的读写位）
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号，没有则停止
    iic_send_byte(reg_addr);                        //发送写入寄存器地址
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号
    iic_send_byte(data);                            //发送写入数据
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号
    iic_stop();
    return 0;
}

/**
 * @brief       读取指定寄存器地址的数据
 * @param       dev_addr:读取设备地址(8位包含读写位)
 *              reg_addr:读取寄存器地址
 *              buf     :读取数据存放缓冲区
 *              length  :读取数据长度（单位为“字节”）
 * @retval      0:写入成功
 *              1:写入失败
 */

 uint8_t iic_reg_read_length(uint8_t dev_addr, uint8_t reg_addr, uint8_t *buf, uint16_t length)
 {
    uint16_t i;                                     //for循环参数

    if(length == 0) return 1;                       //参数保护：读取长度为0没有意义

    iic_start();                                    //起始信号
    iic_send_byte(dev_addr & 0xFE);                 //发送设备地址
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号
    iic_send_byte(reg_addr);                        //发送读取寄存器地址
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号
    
    iic_start();                                    //restart信号，标志数据传输方向由主→从变为从→主
    iic_send_byte(dev_addr | 0x01);                 //设备地址+读操作
    if(iic_wait_ack())  {iic_stop(); return 1;}     //等待ack信号

    for(i = 0; i < length; i++)                     //依次将数据写入指定地址（buf）的寄存器中
    {
        buf[i] = iic_read_byte(i < (length - 1));        
    }

    iic_stop();
    return 0;
 }


