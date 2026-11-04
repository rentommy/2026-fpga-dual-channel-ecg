/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main2.c
  * @brief          : ADS1292 心电采集 —— 精简版
  ******************************************************************************
  *
  *  跟 main.c 的区别：
  *    - SPI 收发全部用 HAL_SPI_TransmitReceive，不自己操作寄存器
  *    - 串口输出用 sprintf + HAL_UART_Transmit，不自己写数字转换
  *    - 数据用「一个变量 + 一个标志位」传递，不用环形缓冲
  *    - 寄存器配置写成二进制，每一位都有注释
  *
  *  程序流程：
  *    1. ads_power_up()    上电时序、复位、读 ID 确认 SPI 通
  *    2. ads_config()      写 11 个配置寄存器并回读校验
  *    3. ads_start()       等基准建立、启动转换、打开 DRDY 中断
  *    4. 中断里读数据，主循环里发串口
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>          /* sprintf */
#include <string.h>         /* strlen  */
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* 运行模式：1 = 内部测试信号（不用接电极）  0 = 正常电极采集
   建议先用 1 跑通整条链路，再改成 0 接电极 */
#define TEST_MODE   0

/* ─── 引脚分配（跟原理图对应）───────────────────────────────────────────
     PA4  CS        片选，低电平选中芯片
     PA5  SCK       SPI 时钟      （CubeMX 配好，代码里不用管）
     PA6  MISO/DOUT SPI 主机输入   （CubeMX 配好，代码里不用管）
     PA7  MOSI/DIN  SPI 主机输出   （CubeMX 配好，代码里不用管）
     PB0  START     高电平芯片才开始转换
     PB1  PWDN/RESET 复位 / 掉电
     PA0  DRDY      芯片输出，数据就绪时拉低，配成下降沿中断
   ──────────────────────────────────────────────────────────────────── */

/* ─── ADS1292 的 SPI 命令码（手册 Table 15）─────────────────────────── */
#define CMD_SDATAC   0x11   /* 退出连续读模式，之后才能读写寄存器 */
#define CMD_RDATAC   0x10   /* 进入连续读模式，之后直接读 9 字节即可 */
#define CMD_RREG     0x20   /* 读寄存器，实际发送 0x20 + 寄存器地址 */
#define CMD_WREG     0x40   /* 写寄存器，实际发送 0x40 + 寄存器地址 */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
SPI_HandleTypeDef hspi1;

UART_HandleTypeDef huart1;

/* USER CODE BEGIN PV */

/* ══════════════════════════════════════════════════════════════════════
 *  寄存器配置表
 *  ADS1292 的 01h~0Bh 这 11 个寄存器地址是连续的，可以用一条 WREG 命令
 *  一次全部写完。数组下标 0 对应寄存器地址 01h。
 * ══════════════════════════════════════════════════════════════════════ */

/* ─── 正常电极采集用的配置 ─────────────────────────────────────────── */
static const uint8_t cfg_ecg[11] =
{
    /* [0] 01h CONFIG1 —— 采样率
           bit7   SINGLE_SHOT = 0     连续转换（0）而不是单次转换（1）
           bit6~3 保留        = 0000  手册要求写 0
           bit2~0 DR[2:0]     = 010   500 SPS
                                      000=125 001=250 010=500 011=1k     */
    0b00000010,

    /* [1] 02h CONFIG2 —— 基准电压和测试信号
           bit7   保留           = 1  手册要求必须写 1
           bit6   PDB_LOFF_COMP  = 0  关闭导联脱落比较器（我们不用）
           bit5   PDB_REFBUF     = 1  打开内部基准缓冲，输出 2.42V
                                      不开就得从外面给 VREFP 供电
           bit4   VREF_4V        = 0  基准选 2.42V（1 是 4.033V，需要更高电源）
           bit3   CLK_EN         = 0  不从 CLK 引脚输出时钟
           bit2   保留           = 0
           bit1   INT_TEST       = 0  不用内部测试信号（采集模式）
           bit0   TEST_FREQ      = 0  测试信号频率，此处无效           */
    0b10100000,

    /* [2] 03h LOFF —— 导联脱落检测，保持复位默认值
           bit7~5 COMP_TH[2:0]   = 000  比较器阈值 95%/5%
           bit4   保留           = 1    手册要求必须写 1
           bit3~2 ILEAD_OFF[1:0] = 00   激励电流 6nA
           bit1   保留           = 0
           bit0   FLEAD_OFF      = 0    直流脱落检测                    */
    0b00010000,

    /* [3] 04h CH1SET —— 通道 1（我们唯一使用的通道）
           bit7   PD1        = 0     通道 1 上电工作（1 是关闭）
           bit6~4 GAIN1[2:0] = 000   增益 6 倍
                                     注意 000 代表 6 不是 1！001 才是 1 倍
           bit3~0 MUX1[3:0]  = 0000  正常电极输入
                                     0001=输入短接 0101=内部测试信号    */
    0b00000000,

    /* [4] 05h CH2SET —— 通道 2，不用，关掉
           bit7   PD2        = 1     关闭通道 2，省电并减少噪声
           bit6~4 GAIN2[2:0] = 000   无所谓，已关闭
           bit3~0 MUX2[3:0]  = 0001  输入短接
                                     手册要求：关闭通道时 MUX 必须设成短接，
                                     否则浮空的输入会耦合噪声串扰到通道 1  */
    0b10000001,

    /* [5] 06h RLD_SENS —— 右腿驱动（抑制 50Hz 工频干扰的关键）
           bit7~6 CHOP[1:0]       = 00  斩波频率 fMOD/16（默认）
           bit5   PDB_RLD         = 1   打开右腿驱动放大器
           bit4   RLD_LOFF_SENS   = 0   关闭 RLD 脱落检测
           bit3   RLD2N           = 0   通道 2 不参与（已关闭）
           bit2   RLD2P           = 0
           bit1   RLD1N           = 1   从通道 1 负电极取共模
           bit0   RLD1P           = 1   从通道 1 正电极取共模

           RLD 的作用：人体像天线，身上感应了几伏的 50Hz 工频干扰。
           RLD 测出这个共模干扰，反相后通过第三个电极注回人体主动抵消。
           不开的话波形会被 50Hz 完全淹没。                            */
    0b00100011,

    /* [6] 07h LOFF_SENS —— 导联脱落检测使能，全部关闭
           bit7~6 保留  = 00
           bit5   FLIP2 = 0
           bit4   FLIP1 = 0
           bit3~0 LOFF2N/LOFF2P/LOFF1N/LOFF1P = 0000  四路检测全关     */
    0b00000000,

    /* [7] 08h LOFF_STAT —— 时钟分频 + 脱落状态
           bit7   保留      = 0
           bit6   CLK_DIV   = 0   内部时钟 512kHz（1 是 2.048MHz）
           bit5   保留      = 0
           bit4   RLD_STAT  ← 只读！RLD 连接状态，写进去无效
           bit3~0 IN*_OFF   ← 只读！各电极脱落状态，写进去无效

           ★ 因为 bit4~0 是只读状态位，这个寄存器读回来的值可能跟写进去的
             不一样，所以下面的回读校验会跳过它                        */
    0b00000000,

    /* [8] 09h RESP1 —— 呼吸功能控制
           bit7   RESP_DEMOD_EN1 = 0   （ADS1292R 才有的功能）
           bit6   RESP_MOD_EN    = 0
           bit5~2 RESP_PH[3:0]   = 0000
           bit1   保留           = 1   ★ 手册要求必须写 1
           bit0   RESP_CTRL      = 0

           手册 p60 明确写：非 R 型号（ADS1292 而不是 ADS1292R）
           这个寄存器必须写 02h，也就是只有 bit1 为 1。照做即可。   */
    0b00000010,

    /* [9] 0Ah RESP2 —— 校准 + RLD 参考源
           bit7   CALIB_ON   = 0   关闭偏移校准
           bit6~3 保留       = 0000
           bit2   RESP_FREQ  = 1   ★ 手册 Table 27：ADS1291/1292 必须写 1
           bit1   RLDREF_INT = 0   RLDREF 由外部电阻分压提供
                                   （1 = 芯片内部产生 (AVDD-AVSS)/2）
           bit0   保留       = 1   ★ 手册要求必须写 1

           ★★ 如果接上电极后 RLD 不起作用（波形全是 50Hz），
              先确认板子上 RLDREF 引脚有没有外部分压电阻。
              没有的话把 bit1 改成 1 用内部产生：0b00000111        */
    0b00000101,

    /* [10] 0Bh GPIO —— 通用 IO，保持复位默认值
            bit7~4 保留        = 0000
            bit3~2 GPIOC[2:1]  = 11   两个 GPIO 都设为输入
            bit1~0 GPIOD[2:1]  = 00   数据位

            ★ GPIOD 读回来的是引脚的实际电平，不是写进去的值，
              所以这个寄存器也跳过回读校验                         */
    0b00001100
};

/* ─── 内部测试信号用的配置 ─────────────────────────────────────────────
     只有两个字节跟上面不同（已用 ★ 标出），其余完全一样。
     测试信号是芯片内部产生的 1Hz 方波，幅度 ±(2.42V/2400) = ±1.008mV，
     经过 6 倍增益后原始码约 ±20960。不接电极就能验证整条链路。
   ──────────────────────────────────────────────────────────────────── */
static const uint8_t cfg_test[11] =
{
    0b00000010,   /* 01h CONFIG1  跟上面一样：500 SPS */

    /* ★ 02h CONFIG2  bit1 INT_TEST = 1  打开内部测试信号发生器
                      bit0 TEST_FREQ = 1  选 1Hz 方波（0 是直流）  */
    0b10100011,

    0b00010000,   /* 03h LOFF     跟上面一样 */

    /* ★ 04h CH1SET  bit3~0 MUX1 = 0101  把通道 1 的输入
                     从电极切换到内部测试信号，增益仍是 6      */
    0b00000101,

    0b10000001,   /* 05h CH2SET   跟上面一样：关闭通道 2 */
    0b00000000,   /* 06h RLD_SENS 测试信号不经过人体，不需要 RLD */
    0b00000000,   /* 07h LOFF_SENS */
    0b00000000,   /* 08h LOFF_STAT */
    0b00000010,   /* 09h RESP1 */
    0b00000101,   /* 0Ah RESP2 */
    0b00001100    /* 0Bh GPIO */
};

/* ─── 中断和主循环之间传数据用的两个变量 ──────────────────────────────
     中断把新样本放进 g_sample 并把 g_ready 置 1，
     主循环看到 g_ready 是 1 就取走数据、清零标志。

     volatile 的作用：告诉编译器这个变量随时可能被中断改掉，
     每次用都要重新从内存读，不许优化成"读一次存寄存器里"。
     不加的话主循环会永远看不到中断的修改，死在空转上。
   ──────────────────────────────────────────────────────────────────── */
static volatile int32_t  g_sample  = 0;   /* 最新的一个 CH1 采样值 */
static volatile uint8_t  g_ready   = 0;   /* 1 表示有新数据待发送 */
static volatile uint32_t g_overrun = 0;   /* 主循环没来得及取走的次数 */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_SPI1_Init(void);
static void MX_USART1_UART_Init(void);
/* USER CODE BEGIN PFP */
static void short_delay(void);
static void uart_send(const char *s);
static void spi_read_write(const uint8_t *tx, uint8_t *rx, uint16_t len);
static void ads_send_cmd(uint8_t cmd);
static int  ads_power_up(void);
static int  ads_config(const uint8_t *cfg);
static void ads_start(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* ══════════════════════════════════════════════════════════════════════
 *  短延时（约 20 微秒）
 *
 *  为什么不用 HAL_Delay？
 *    1. HAL_Delay 最小单位是 1 毫秒，而这里要等的是 8 微秒，差 125 倍
 *    2. 更要命的是：HAL_Delay 靠 SysTick 计时，而 DRDY 中断的优先级(3)
 *       比 SysTick(15) 高，中断执行期间 SysTick 无法打断它，计时器不走。
 *       HAL_Delay 的循环唯一的退出条件就是计时器前进，
 *       所以在中断里调用 HAL_Delay 会「永远卡死」，整块板子死机。
 *
 *  所以这里用最简单的空转循环。变量加 volatile 是为了防止编译器
 *  发现"这个循环什么也没干"而直接把它优化掉。
 * ══════════════════════════════════════════════════════════════════════ */
static void short_delay(void)
{
    /* 72MHz 主频下每圈约 7 个时钟周期，200 圈约 20 微秒。
       ADS1292 要求 CS 拉高前至少等 4 个内部时钟 = 7.8 微秒，够用 */
    for (volatile uint32_t i = 0; i < 200; i++)
    {
    }
}

/* ══════════════════════════════════════════════════════════════════════
 *  发送一个字符串到串口
 *  HAL_MAX_DELAY 表示一直等到发完为止，不设超时
 * ══════════════════════════════════════════════════════════════════════ */
static void uart_send(const char *s)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)s, (uint16_t)strlen(s), HAL_MAX_DELAY);
}

/* ══════════════════════════════════════════════════════════════════════
 *  一次完整的 SPI 通信：拉低片选 → 收发数据 → 延时 → 拉高片选
 *
 *  SPI 是全双工的：发出去一个字节的同时，必然会收进来一个字节。
 *  所以「读数据」的做法是发一堆无意义的 0x00 出去，把时钟转起来，
 *  对方的数据就被换进来了。
 *
 *  超时参数用 HAL_MAX_DELAY 而不是具体毫秒数，原因见 short_delay 的说明：
 *  在中断里 SysTick 不走，超时判断本来就失效，写个具体数值只是自欺欺人。
 *  （HAL_SPI_TransmitReceive 的循环靠硬件标志退出，所以能正常跑完，
 *    只是万一硬件坏了不会自动报错而已。）
 * ══════════════════════════════════════════════════════════════════════ */
static void spi_read_write(const uint8_t *tx, uint8_t *rx, uint16_t len)
{
    /* 拉低 CS，选中 ADS1292 */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_RESET);

    /* 收发 len 个字节 */
    HAL_SPI_TransmitReceive(&hspi1, (uint8_t *)tx, rx, len, HAL_MAX_DELAY);

    /* 手册要求：CS 拉高前必须等 4 个内部时钟周期（7.8 微秒） */
    short_delay();

    /* 拉高 CS，本次通信结束 */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);

    /* 两次通信之间也要留间隔 */
    short_delay();
}

/* ══════════════════════════════════════════════════════════════════════
 *  发送一条单字节命令（SDATAC / RDATAC 这种不带参数的）
 * ══════════════════════════════════════════════════════════════════════ */
static void ads_send_cmd(uint8_t cmd)
{
    uint8_t tx = cmd;
    uint8_t rx = 0;

    spi_read_write(&tx, &rx, 1);
}

/* ══════════════════════════════════════════════════════════════════════
 *  第 1 步：上电时序
 *
 *  时间常数（内部时钟 512kHz）：
 *      一个时钟周期 tCLK = 1 / 512000 = 1.95 微秒
 *      调制器周期  tMOD = 4 × tCLK   = 7.8 微秒
 *
 *  返回 0 = 成功，-1 = SPI 读不到芯片 ID
 * ══════════════════════════════════════════════════════════════════════ */
static int ads_power_up(void)
{
    uint8_t tx[3];
    uint8_t rx[3];
    char    msg[40];

    /* ─────────────────────────────────────────────────────────────────
       ★ 先关掉 DRDY 中断。
       CubeMX 生成的 MX_GPIO_Init() 里已经执行了 HAL_NVIC_EnableIRQ()，
       而它在 main() 里比这个函数先执行。也就是说现在中断已经是开着的。
       接下来复位芯片、写寄存器的过程中 DRDY 引脚会乱跳，如果不关中断，
       中断会插进写寄存器的过程中间，把正在进行的操作彻底冲掉。
       ───────────────────────────────────────────────────────────────── */
    HAL_NVIC_DisableIRQ(EXTI0_IRQn);

    /* ── 1. 设置初始电平 ──────────────────────────────────────────────
       手册 10.1 要求：上电瞬间所有数字输入引脚必须是低电平。
       （这也是板子上 PWDN/RESET 接下拉电阻的原因——在 STM32 还没跑起来
         的那几十毫秒里，靠电阻保证它是低的。）
       CS 是例外，高电平表示"不选中"，是空闲状态。                    */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_RESET);   /* RESET = 低 */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);   /* START = 低 */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);     /* CS    = 高 */

    /* ── 2. 等上电复位完成 ────────────────────────────────────────────
       手册 Table 29：上电复位需要 2^12 个调制器周期 = 32 毫秒。
       等 100 毫秒留足裕量。                                          */
    HAL_Delay(100);

    /* ── 3. 退出掉电模式 ──────────────────────────────────────────────
       PWDN/RESET 这个引脚是复用的：
         持续拉低超过 4 毫秒  → 芯片进入掉电模式
         短暂拉低再拉高       → 触发复位
       上一步等了 100 毫秒，芯片已经进掉电了，现在拉高唤醒。
       手册 p9：掉电到就绪需要 10 毫秒。                              */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_SET);
    HAL_Delay(20);

    /* ── 4. 发一个复位脉冲 ────────────────────────────────────────────
       手册 8.5.1.8：复位是靠"高→低"这个跳变触发的，不是低电平本身。
       脉冲宽度约 20 微秒：
         下限 —— 必须大于 2 个时钟周期 = 3.9 微秒
         上限 —— 必须远小于 4 毫秒，否则会变成进入掉电模式
       上一步的唤醒不保证寄存器回到默认值，显式复位一次让芯片处于
       确定的初始状态，后面的配置才可靠。                            */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_RESET);
    short_delay();
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, GPIO_PIN_SET);
    short_delay();      /* 复位后需要等 18 个时钟周期 = 35 微秒 */
    short_delay();

    /* ── 5. 退出连续读模式（★ 最容易漏掉的一步）──────────────────────
       芯片上电后默认就在 RDATAC（连续读）模式。
       手册 Table 15 脚注1：在这个模式下，读写寄存器的命令会被芯片
       直接忽略，而且不会报任何错。

       不发这条命令的话：
         - 下面读 ID 会读到 ADC 数据而不是 ID，校验必然失败
         - 再下面写 11 个寄存器，一个都写不进去，芯片还是默认配置
       你只会看到一堆莫名其妙的数据，完全不知道哪里出了问题。      */
    ads_send_cmd(CMD_SDATAC);

    /* ── 6. 读 ID 寄存器，确认 SPI 通路正常 ───────────────────────────
       读寄存器的 SPI 格式是三个字节：
         第 1 字节：0x20 + 寄存器地址   （这里地址是 00h，所以是 0x20）
         第 2 字节：要读几个寄存器 - 1  （读 1 个就发 0）
         第 3 字节：发 0x00 把数据换回来

       手册 Table 16：ID 寄存器的 bit4 恒为 1、bit3 和 bit2 恒为 0。
       ADS1292 完整的 ID 值通常是 0x53。

       这一步的价值：把"SPI 硬件不通"和"配置写错了"两类问题分开。
         读出 0x00 或 0xFF → 线没接对 / 芯片没供电 / CS 不对
         读出 0x53         → 硬件通路完全正常，后面出问题就是软件的事 */
    tx[0] = CMD_RREG | 0x00;   /* 读 00h 号寄存器 */
    tx[1] = 0x00;              /* 读 1 个 */
    tx[2] = 0x00;              /* 占位，用来把数据换回来 */
    spi_read_write(tx, rx, 3);

    sprintf(msg, "ID = 0x%02X  ", rx[2]);   /* 数据在第 3 个字节 */
    uart_send(msg);

    /* 检查那三个固定位：bit4 必须是 1，bit3 和 bit2 必须是 0 */
    if ((rx[2] & 0b00011100) != 0b00010000)
    {
        uart_send("[失败] SPI 不通\r\n");
        return -1;
    }

    uart_send("[正常]\r\n");
    return 0;
}

/* ══════════════════════════════════════════════════════════════════════
 *  第 2 步：写 11 个配置寄存器，然后读回来校验
 *  参数传 cfg_ecg（电极采集）或 cfg_test（内部测试信号）
 *  返回 0 = 成功，-2 = 回读的值跟写进去的不一致
 * ══════════════════════════════════════════════════════════════════════ */
static int ads_config(const uint8_t *cfg)
{
    uint8_t tx[13];
    uint8_t rx[13];
    char    msg[48];
    int     i;

    /* ── 写：命令格式是 [0x40+起始地址] [个数-1] [数据1] [数据2] ... ──
       11 个寄存器地址连续，一条命令全部写完                          */
    tx[0] = CMD_WREG | 0x01;   /* 从 01h 号寄存器开始写 */
    tx[1] = 11 - 1;            /* 写 11 个，手册规定这里填「个数减 1」 */
    for (i = 0; i < 11; i++)
    {
        tx[2 + i] = cfg[i];
    }
    spi_read_write(tx, rx, 13);

    /* 写 CONFIG1 / RESP1 / RESP2 会让芯片内部的数字滤波器自动复位，
       需要一点时间重新稳定 */
    HAL_Delay(10);

    /* ── 读回来：命令格式是 [0x20+起始地址] [个数-1] [11个占位字节] ──
       这是唯一能确认"配置真的生效了"的手段。
       不做这一步的话，如果上面的 SDATAC 漏了导致写入被忽略，
       你要一直到看波形不对时才发现，那时候已经分不清是配置问题
       还是电极问题了。                                              */
    tx[0] = CMD_RREG | 0x01;
    tx[1] = 11 - 1;
    for (i = 0; i < 11; i++)
    {
        tx[2 + i] = 0x00;      /* 占位，把数据换回来 */
    }
    spi_read_write(tx, rx, 13);

    /* 打印读回来的 11 个字节，方便对照 */
    uart_send("寄存器回读 = ");
    for (i = 0; i < 11; i++)
    {
        sprintf(msg, "%02X ", rx[2 + i]);
        uart_send(msg);
    }
    uart_send("\r\n");

    /* ── 逐个比对，但只校验 01h ~ 07h（下标 0~6）────────────────────
       ★ 为什么跳过 08h 和 0Bh：
         08h LOFF_STAT 的 bit4~0 是只读状态位（RLD 连接状态、电极脱落
                       状态），读回来是芯片的实际状态，不是写进去的值
         0Bh GPIO      的 bit1~0 读回来是 GPIO 引脚的实际电平
         这两个寄存器读回来跟写进去不一样是正常现象，
         如果也拿来比对会误报失败。
         09h RESP1 和 0Ah RESP2 是可读写的，但为了简单一起放行。    */
    for (i = 0; i <= 6; i++)
    {
        if (rx[2 + i] != cfg[i])
        {
            sprintf(msg, "[失败] 寄存器 %02Xh: 写入 %02X 读回 %02X\r\n",
                    i + 1, cfg[i], rx[2 + i]);
            uart_send(msg);
            return -2;
        }
    }

    uart_send("寄存器配置校验通过\r\n");
    return 0;
}

/* ══════════════════════════════════════════════════════════════════════
 *  第 3 步：启动转换并打开中断
 * ══════════════════════════════════════════════════════════════════════ */
static void ads_start(void)
{
    /* ── 等基准电压建立 ───────────────────────────────────────────────
       手册 p9 给的建立时间：
         VREFP 达到 0.2% 精度需要 100 毫秒（外接 10uF 电容）
         VCAP1 达到 1%  精度需要 500 毫秒（外接 1uF 电容）
       VCAP1 是芯片内部模拟电源的滤波电容，它建立最慢。
       手册的参考流程直接等 1 秒，我们照做。
       不等的话前几百毫秒的数据会有基线漂移。                        */
    uart_send("等待基准电压建立（1 秒）...\r\n");
    HAL_Delay(1000);

    /* ── START 拉高，芯片开始转换 ─────────────────────────────────────
       ★ 手册 8.5.1.9：START 为低电平时芯片根本不进行转换，
         也就不会产生 DRDY 信号。
       如果你发现程序卡在"初始化完成"一个数据都没有，
       第一个要查的就是 PB0 这个引脚是不是 3.3V。                    */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_SET);

    /* ── 进入连续读模式 ───────────────────────────────────────────────
       之后每次 DRDY 拉低，直接读 9 个字节就行，
       不用每次都先发一条 RDATA 命令。                                */
    ads_send_cmd(CMD_RDATAC);

    /* ── 等数字滤波器建立 ─────────────────────────────────────────────
       手册 8.3.5：芯片内部的 SINC 数字滤波器在输入发生阶跃后
       需要 3 个数据周期才能完全建立 = 3 × 2ms = 6 毫秒。
       这期间的数据是无效的，等过去了再开中断就不会采到它们。        */
    HAL_Delay(20);

    /* ── 清干净挂起标志，再打开中断 ───────────────────────────────────
       ★ 前面十几个步骤里 DRDY 引脚跳变过很多次。虽然中断被关掉了
         不会执行，但 EXTI 和 NVIC 的「挂起标志位」还是被硬件置起来了。
         如果直接开中断，这些积攒的标志会立刻触发一次中断，
         去读一帧根本不存在的数据。
         所以要把两层标志都清掉：                                     */
    g_ready = 0;
    __HAL_GPIO_EXTI_CLEAR_IT(GPIO_PIN_0);   /* 清 EXTI 外设的挂起标志 */
    NVIC_ClearPendingIRQ(EXTI0_IRQn);        /* 清 NVIC 控制器的挂起标志 */
    HAL_NVIC_EnableIRQ(EXTI0_IRQn);          /* 真正打开中断 */
}

/* ══════════════════════════════════════════════════════════════════════
 *  DRDY 下降沿中断
 *
 *  调用链（前两步都是自动的，不用你写）：
 *      DRDY 引脚下降沿
 *        → EXTI0_IRQHandler()            在 stm32f1xx_it.c，CubeMX 生成
 *        → HAL_GPIO_EXTI_IRQHandler()    HAL 库里，负责清中断标志
 *        → HAL_GPIO_EXTI_Callback()      就是这个函数
 *
 *  HAL 库里的 HAL_GPIO_EXTI_Callback 被声明成 __weak（弱函数），
 *  意思是"这是个空的默认实现，你要是自己定义一个同名的就用你的"。
 *  所以我们在这里写一个同名函数，不需要任何注册动作，自动就被调用了。
 *
 *  这个函数里只做「读数据 + 存起来」，串口发送留给主循环。
 *  耗时约 170 微秒，中断周期是 2000 微秒，占用不到 9%。
 * ══════════════════════════════════════════════════════════════════════ */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    uint8_t tx[9] = {0};    /* 全发 0x00，只是为了把 SPI 时钟转起来 */
    uint8_t rx[9];          /* 收到的 9 个字节放这里 */
    int32_t value;

    /* 所有 EXTI 中断最后都汇集到这一个回调函数，
       所以要先判断是哪个引脚触发的。现在只有一个中断源，
       但以后加按键之类的也会跑进来，加上这句是好习惯。 */
    if (GPIO_Pin != GPIO_PIN_0)
    {
        return;
    }

    /* ── 读一帧 9 个字节 ──────────────────────────────────────────────
       在连续读模式下不需要发命令，拉低 CS 直接读就行。
       9 个字节的含义：
         rx[0] rx[1] rx[2]  状态字（24位），这里不用
         rx[3] rx[4] rx[5]  通道 1 数据（24位），这是我们要的
         rx[6] rx[7] rx[8]  通道 2 数据（24位），已关闭，是噪声    */
    spi_read_write(tx, rx, 9);

    /* ── 把 3 个字节拼成一个数 ────────────────────────────────────────
       芯片是高位在前发送的，所以第一个字节要左移 16 位。
       例：rx[3]=0xFF rx[4]=0xAE rx[5]=0x30
           0x00FF0000 | 0x0000AE00 | 0x00000030 = 0x00FFAE30        */
    value = ((int32_t)rx[3] << 16) | ((int32_t)rx[4] << 8) | (int32_t)rx[5];

    /* ── 符号扩展（★ 这一步不能省）────────────────────────────────────
       芯片输出的是「24 位」二进制补码，范围 -8388608 ~ +8388607。
       但我们放进了 32 位变量里，高 8 位是 0。
       正数没问题，负数就错了：
           24位的 -1 = 0xFFFFFF
           放进32位  = 0x00FFFFFF = +16777215   ← 变成了大正数，错！
           正确的应该 = 0xFFFFFFFF = -1         ← 高 8 位要补满 1

       怎么判断正负：看第 24 位（也就是 0x800000 这一位）是不是 1。
       是 1 说明是负数，就把高 8 位全部填 1。

       漏掉这一步的现象：波形一半正常，低于 0 的那一半会突然跳到
       +8388607 附近，画出来是满屏尖刺。                             */
    if ((value & 0x800000) != 0)
    {
        value = value | (int32_t)0xFF000000;
    }

    /* ── 交给主循环 ───────────────────────────────────────────────────
       如果上一个数据主循环还没取走，说明串口跟不上采样速度，
       计个数（g_overrun），然后用新数据覆盖旧的。
       正常情况下 g_overrun 应该一直是 0。                            */
    if (g_ready == 1)
    {
        g_overrun++;
    }
    g_sample = value;
    g_ready  = 1;
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  char    line[20];
  int32_t value;
  int     result;
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_SPI1_Init();
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */

  /* 打个招呼，确认串口本身是通的 */
  uart_send("\r\n\r\n===== ADS1292 心电采集 =====\r\n");

  /* 检查主频。如果外部 8MHz 晶振没起振，HAL 会自动退回内部 8MHz 振荡器，
     主频变成 8MHz 而不是 72MHz，所有延时都会短 9 倍，
     SPI 时序全部违规，现象是"时好时坏"，极难排查。
     打印出来一眼就能看到。 */
  sprintf(line, "主频 = %lu Hz\r\n", (unsigned long)SystemCoreClock);
  uart_send(line);

  /* 第 1 步：上电时序。失败就每 3 秒重试一次，不往下走。
     这样调试时可以一边看串口一边拿表笔量电压，不用反复按复位键。 */
  while (ads_power_up() != 0)
  {
      uart_send("3 秒后重试...\r\n\r\n");
      HAL_Delay(3000);
  }

  /* 第 2 步：写配置寄存器。用哪张表由文件开头的 TEST_MODE 决定 */
#if TEST_MODE
  uart_send("模式：内部测试信号（不用接电极）\r\n");
  result = ads_config(cfg_test);
#else
  uart_send("模式：电极采集\r\n");
  result = ads_config(cfg_ecg);
#endif

  if (result != 0)
  {
      /* 配置失败就停在这里，不要输出垃圾数据误导人 */
      uart_send("配置失败，程序停止\r\n");
      while (1)
      {
      }
  }

  /* 第 3 步：启动转换，打开中断 */
  ads_start();

  uart_send("初始化完成，开始采集\r\n");
#if TEST_MODE
  uart_send("# 应该看到 +20960 和 -20960 之间每 250 个点跳变一次\r\n");
#endif
  uart_send("# 每行一个通道1的原始码，电压(V) = 原始码 x 0.000000048\r\n");

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */

    /* 有新数据就发出去。没有就空转，反正也没别的事干。
       采样的时间由 DRDY 中断保证，跟这里的快慢完全无关。 */
    if (g_ready == 1)
    {
        /* 先把数据复制出来再清标志，顺序反了的话
           中断可能在这个空档写入新值，把还没读的数据覆盖掉 */
        value   = g_sample;
        g_ready = 0;

        /* 转成文本发出去。sprintf 的返回值就是写了几个字符，
           不用再 strlen 一遍 */
        sprintf(line, "%ld\r\n", (long)value);
        uart_send(line);
    }

  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief SPI1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI1_Init(void)
{

  /* USER CODE BEGIN SPI1_Init 0 */

  /* USER CODE END SPI1_Init 0 */

  /* USER CODE BEGIN SPI1_Init 1 */

  /* USER CODE END SPI1_Init 1 */
  /* SPI1 parameter configuration*/
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_2EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_128;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN SPI1_Init 2 */

  /* USER CODE END SPI1_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0|GPIO_PIN_1, GPIO_PIN_RESET);

  /*Configure GPIO pin : PA0 */
  GPIO_InitStruct.Pin = GPIO_PIN_0;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : PA4 */
  GPIO_InitStruct.Pin = GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PB0 PB1 */
  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI0_IRQn, 3, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
