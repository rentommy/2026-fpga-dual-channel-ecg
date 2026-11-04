/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : ADS1292 心电采集（精简版）
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include <stdio.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* ==========================================================================
 *  整个程序做的事：
 *    1. 按手册顺序给 ADS1292 上电、复位、写配置
 *    2. 芯片每 2 毫秒采完一个样本，就把 DRDY 拉低 → 单片机进中断，用 SPI 读走
 *    3. 主循环把样本转成文字，从串口发给上位机（一行一个数）
 * ========================================================================== */

/* ── ADS1292 用到的引脚（和 CubeMX 里配置的一致）── */
#define CS_PORT      GPIOA
#define CS_PIN       GPIO_PIN_4     /* 片选：低电平 = 选中芯片 */
#define START_PORT   GPIOB
#define START_PIN    GPIO_PIN_0     /* START：高电平 = 开始转换 */
#define RST_PORT     GPIOB
#define RST_PIN      GPIO_PIN_1     /* PWDN/RESET：低电平 = 复位 */
#define DRDY_PIN     GPIO_PIN_0     /* PA0 = DRDY：芯片采完一个样本就拉低，触发中断 */

/* ── SPI 命令（手册 Table 15）── */
#define CMD_RDATAC   0x10           /* 进入「连续读数据」模式 */
#define CMD_SDATAC   0x11           /* 退出「连续读数据」模式 */
#define CMD_RREG     0x20           /* 读寄存器，低 5 位是起始地址 */
#define CMD_WREG     0x40           /* 写寄存器，低 5 位是起始地址 */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
SPI_HandleTypeDef hspi1;

UART_HandleTypeDef huart1;

/* USER CODE BEGIN PV */

/* ==========================================================================
 *  11 个配置寄存器（地址 01h ~ 0Bh，一次连续写入）
 *
 *  ★ 为什么写十六进制：本工程用的是 Keil 的 ARM Compiler 5，
 *    它不支持 0b 开头的二进制写法，写了会编译报错。
 *    所以数值写十六进制，每一位的含义在注释里用二进制标出来。
 * ========================================================================== */
static const uint8_t ads_cfg[11] = {
    0x02,   /* 01h CONFIG1   = 0000 0010
               bit7   = 0    连续转换（不是单次）
               bit2~0 = 010  采样率 500 次/秒                                   */
    0xA0,   /* 02h CONFIG2   = 1010 0000
               bit7   = 1    手册规定必须为 1
               bit5   = 1    打开芯片内部基准电压
               bit4   = 0    基准选 2.42V（供电只有 3.3V，不能选 4.033V）
               bit1   = 0    不打开内部测试信号                                  */
    0x10,   /* 03h LOFF      = 0001 0000
               bit4   = 1    手册规定必须为 1，其余位保持默认                     */
    0x81,   /* 04h CH1SET    = 1000 0001
               bit7   = 1    通道1 掉电（没用到）
               bit3~0 = 0001 输入短接（手册要求：关掉的通道必须这样设）            */
    0x00,   /* 05h CH2SET    = 0000 0000
               bit7   = 0    通道2 正常工作（心电从这个通道采）
               bit6~4 = 000  放大 6 倍
               bit3~0 = 0000 接外部电极                                          */
    0x2C,   /* 06h RLD_SENS  = 0010 1100
               bit5   = 1    打开右腿驱动放大器（默认是关的！）
               bit3   = 1    取通道2 负极的电压
               bit2   = 1    取通道2 正极的电压
               → 右腿驱动把两个电极的共同干扰反相后送回人体，抑制 50 赫兹           */
    0x00,   /* 07h LOFF_SENS = 0000 0000   不用导联脱落检测                       */
    0x00,   /* 08h LOFF_STAT = 0000 0000
               bit6   = 0    使用芯片内部 512kHz 时钟                            */
    0x02,   /* 09h RESP1     = 0000 0010   手册规定：没有呼吸功能的型号必须写这个值 */
    0x07,   /* 0Ah RESP2     = 0000 0111
               bit2   = 1    手册规定：没有呼吸功能的型号必须为 1
               bit1   = 1    右腿驱动的参考电压用芯片内部产生的中点电压
               bit0   = 1    手册规定必须为 1                                    */
    0x0C    /* 0Bh GPIO      = 0000 1100   两个 GPIO 都设为输入（默认值）          */
};

static volatile int32_t sample       = 0;  //中断数据
static volatile uint8_t sample_ready = 0;  //中断数据标志

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_SPI1_Init(void);
static void MX_USART1_UART_Init(void);
/* USER CODE BEGIN PFP */

static void uart_print(const char *s);
static void ads_cmd(uint8_t cmd);
static int  ads_init(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static void uart_print(const char *s)  //串口发送函数
{
    HAL_UART_Transmit(&huart1, (uint8_t *)s, (uint16_t)strlen(s), 100);
}

static void ads_cmd(uint8_t cmd)  //命令发送函数
{
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET);   /* 选中芯片 */
    HAL_SPI_Transmit(&hspi1, &cmd, 1, 100);               /* 发出命令 */
    HAL_Delay(1);   /* 等待命令 */
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET);     /* 取消选中芯片 */
    HAL_Delay(1);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)  //中断函数
{
    uint8_t tx[9] = {0};    /* 读 9 个字节 */
    uint8_t rx[9];
    int32_t v;

    if (GPIO_Pin != DRDY_PIN)  //判断中断
    {
        return;
    }

    /* 读一帧 9 个字节：[0~2] 状态字  [3~5] 通道1  [6~8] 通道2 */
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET);  /* 选中芯片 */
    HAL_SPI_TransmitReceive(&hspi1, tx, rx, 9, 10);      /* 接收数据 */
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET);    /* 取消选中芯片 */ 

    /* 帧校验：状态字开头固定是二进制 1100，第 3 个字节固定全 0。
       对不上说明读错位了，丢掉这一帧，免得把乱码当成心电发出去 */
    if (((rx[0] & 0xF0) != 0xC0) || (rx[2] != 0x00))   //保留高 4 位，低 4 位清零
    {
        return;
    }

    /* 通道2 的 3 个字节拼成一个 24 位数（高字节在前） */
    v = ((int32_t)rx[6] << 16) | ((int32_t)rx[7] << 8) | (int32_t)rx[8];

    /* 24 位补码 → 32 位 */
    if (v & 0x00800000)            //判断符号位
    {
        v |= (int32_t)0xFF000000;  //负数高八位置1，正数不变
    }

    sample       = v;  //传出数据
    sample_ready = 1;  //标记数据有效
}

static int ads_init(void)  //ADS1292 初始化函数
{
    uint8_t tx[13];
    uint8_t rx[13];
    char    buf[32];
    uint8_t i;

    HAL_NVIC_DisableIRQ(EXTI0_IRQn);  //关闭DRDY中断

    HAL_GPIO_WritePin(RST_PORT,   RST_PIN,   GPIO_PIN_RESET);  //复位芯片
    HAL_GPIO_WritePin(START_PORT, START_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(CS_PORT,    CS_PIN,    GPIO_PIN_SET);
    HAL_Delay(100);
    HAL_GPIO_WritePin(RST_PORT, RST_PIN, GPIO_PIN_SET);
    HAL_Delay(20);

    HAL_GPIO_WritePin(RST_PORT, RST_PIN, GPIO_PIN_RESET);  //复位脉冲
    HAL_Delay(1);
    HAL_GPIO_WritePin(RST_PORT, RST_PIN, GPIO_PIN_SET);
    HAL_Delay(1);

    ads_cmd(CMD_SDATAC);  //发送，退出连续读数据模式命令

                          //配置读取寄存器命令
    tx[0] = CMD_RREG | 0x00;    /* 从地址 00h 开始读 */
    tx[1] = 0;                  /* 寄存器数量-1 */
    tx[2] = 0;

    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET); /* 选中芯片 */
    HAL_SPI_TransmitReceive(&hspi1, tx, rx, 3, 100);    /* 读取寄存器 */
    HAL_Delay(1);
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET);   /* 取消选中芯片 */

    sprintf(buf, "ID = 0x%02X\r\n", rx[2]);  //生成需要发送的字符串
    uart_print(buf);                         //发送字符串

    if ((rx[2] & 0x10) == 0)                 //判断是否成功通信
    {
        uart_print("SPI 不通\r\n");
        return -1;
    }

                                //配置写寄存器命令
    tx[0] = CMD_WREG | 0x01;    /* 从地址 01h 开始写 */
    tx[1] = 10;                 /* 寄存器数量-1 */
    for (i = 0; i < 11; i++)
    {
        tx[2 + i] = ads_cfg[i]; //导入配置好的寄存器值
    }

    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET);/* 选中芯片 */
    HAL_SPI_Transmit(&hspi1, tx, 13, 100);             /* 写入寄存器 */
    HAL_Delay(1);
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET);  /* 取消选中芯片 */
    HAL_Delay(10);

                                //验证是否写入成功
                                //配置读寄存器命令
    tx[0] = CMD_RREG | 0x01;    /* 从地址 01h 开始读 */
    tx[1] = 10;                 /* 寄存器数量-1 */
    for (i = 0; i < 11; i++)
    {
        tx[2 + i] = 0;          //清空发送缓冲区
    }

    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_RESET);/* 选中芯片 */
    HAL_SPI_TransmitReceive(&hspi1, tx, rx, 13, 100);  /* 读取寄存器 */
    HAL_Delay(1);
    HAL_GPIO_WritePin(CS_PORT, CS_PIN, GPIO_PIN_SET);  /* 取消选中芯片 */

    //输出读取结果
    uart_print("REG =");
    for (i = 0; i < 11; i++)
    {
        sprintf(buf, " %02X", rx[2 + i]);//生成需要发送的字符串
        uart_print(buf);
    }
    uart_print("\r\n");

    //读取结果和写入配置对比
    for (i = 0; i < 11; i++)
    {
        if (rx[2 + i] != ads_cfg[i])
        {
            uart_print("寄存器回读不一致\r\n"); //不同输出错误
            return -2;
        }
    }

    /* 等芯片内部基准电压稳定 */
    HAL_Delay(1000);

    /* START 拉高，进入连续读数据模式 */
    HAL_GPIO_WritePin(START_PORT, START_PIN, GPIO_PIN_SET);
    ads_cmd(CMD_RDATAC);
    HAL_Delay(20);

    /* 清除标记数据，打开 DRDY 中断 */
    sample_ready = 0;
    __HAL_GPIO_EXTI_CLEAR_IT(DRDY_PIN);
    NVIC_ClearPendingIRQ(EXTI0_IRQn);
    HAL_NVIC_EnableIRQ(EXTI0_IRQn);

    return 0;
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  char buf[16];
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

  uart_print("\r\n===== ECG 心电采集 =====\r\n");//输出调试日志

  while (ads_init() != 0)  //芯片初始化
  {
      uart_print("初始化失败，3 秒后重试\r\n");
      HAL_Delay(3000);
  }

  /* 这一句用纯英文：ARM Compiler 5 处理这句中文时会报「非法多字节字符」警告，可能输出乱码 */
  uart_print("START: 500 samples/s, voltage(V) = value x 48.081e-9\r\n");

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */

    if (sample_ready)
    {
        sample_ready = 0;
        sprintf(buf, "%ld\r\n", (long)sample);  //生成需要发送的字符串
        uart_print(buf);                        //发送心电数据
    }

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
