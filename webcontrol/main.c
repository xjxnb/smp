/**
 ****************************************************************************************************
 * @file        main.c
 * @author      正点原子团队(ALIENTEK)
 * @version     V1.0
 * @date        2021-10-25
 * @brief       触摸屏 实验
 * @license     Copyright (c) 2020-2032, 广州市星翼电子科技有限公司
 ****************************************************************************************************
 * @attention
 *
 * 实验平台:正点原子 探索者 F407开发板
 * 在线视频:www.yuanzige.com
 * 技术论坛:www.openedv.com
 * 公司网址:www.alientek.com
 * 购买地址:openedv.taobao.com
 *
 ****************************************************************************************************
 */

#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/LED/led.h"
#include "./BSP/LCD/lcd.h"
#include "./BSP/KEY/key.h"
#include "./BSP/TOUCH/touch.h"
#include "./BSP/CAN/can.h"          // 添加CAN驱动头文件

// ========== 按钮区域定义（根据屏幕分辨率调整，这里以 480x320 为例） ==========
#define BTN_ON_X1     100
#define BTN_ON_Y1     200
#define BTN_ON_X2     200
#define BTN_ON_Y2     240

#define BTN_OFF_X1    220
#define BTN_OFF_Y1    200
#define BTN_OFF_X2    320
#define BTN_OFF_Y2    240

#define BTN_MODE_X1   340
#define BTN_MODE_Y1   200
#define BTN_MODE_X2   440
#define BTN_MODE_Y2   240

// 全局变量，用于在CAN接收回调中更新
volatile uint8_t led_state = 0;      // 0:灭, 1:亮
volatile uint8_t can_rx_flag = 0;
volatile uint8_t can_rx_data[8];
volatile uint32_t can_rx_id;

// ========== CAN接收中断回调（需在 can.c 中实现或直接在此处） ==========
// 注意：如果 can.c 中已经有此回调，请删除下面的重复定义
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan)
{
    CAN_RxHeaderTypeDef rxHeader;
    HAL_CAN_GetRxMessage(hcan, CAN_RX_FIFO0, &rxHeader, (uint8_t*)can_rx_data);
    can_rx_id = rxHeader.StdId;
    can_rx_flag = 1;
}

// ========== 绘制按钮和界面 ==========
void draw_ui(void)
{
    // 清屏
    lcd_clear(WHITE);

    // 标题
    lcd_show_string(30, 30, 200, 16, 16, "STM32 CAN + TOUCH", RED);
    lcd_show_string(30, 60, 200, 16, 16, "Face: Unknown", BLUE);
    lcd_show_string(30, 90, 200, 16, 16, "LED: OFF", BLUE);

    // 按钮区域
    lcd_draw_rectangle(BTN_ON_X1, BTN_ON_Y1, BTN_ON_X2, BTN_ON_Y2, BLUE);
    lcd_show_string(BTN_ON_X1+30, BTN_ON_Y1+10, 80, 16, 16, "LED ON", BLUE);

    lcd_draw_rectangle(BTN_OFF_X1, BTN_OFF_Y1, BTN_OFF_X2, BTN_OFF_Y2, BLUE);
    lcd_show_string(BTN_OFF_X1+30, BTN_OFF_Y1+10, 80, 16, 16, "LED OFF", BLUE);

    lcd_draw_rectangle(BTN_MODE_X1, BTN_MODE_Y1, BTN_MODE_X2, BTN_MODE_Y2, BLUE);
    lcd_show_string(BTN_MODE_X1+30, BTN_MODE_Y1+10, 80, 16, 16, "MODE", BLUE);
}

// ========== 更新LED状态显示 ==========
void update_led_display(void)
{
    if (led_state)
        lcd_show_string(30, 90, 200, 16, 16, "LED: ON ", BLUE);
    else
        lcd_show_string(30, 90, 200, 16, 16, "LED: OFF", BLUE);
}

int main(void)
{
    uint8_t key;
    uint8_t i;
	  

    HAL_Init();
    sys_stm32_clock_init(336, 8, 2, 7);
    delay_init(168);
    usart_init(115200);
    led_init();
    lcd_init();
    key_init();
    tp_dev.init();

    // 初始化CAN，普通模式，波特率500kbps
    can_init(CAN_SJW_1TQ, CAN_BS2_6TQ, CAN_BS1_7TQ, 6, CAN_MODE_NORMAL);

    // 绘制用户界面
    draw_ui();

    // 显示触摸屏校准提示（如果是电阻屏）
    if (tp_dev.touchtype != 0xFF)
    {
        lcd_show_string(30, 120, 200, 16, 16, "Press KEY0 to Adjust", RED);
    }

    delay_ms(1500); // 等待界面稳定

    // 主循环
    while (1)
    {
        // ---------- 按键扫描（用于触摸屏校准） ----------
        key = key_scan(0);
        if (key == KEY0_PRES)
        {
            lcd_clear(WHITE);
            tp_adjust();            // 电阻屏校准
            tp_save_adjust_data();
            draw_ui();              // 校准后重绘界面
            update_led_display();
            delay_ms(500);
        }

        // ---------- 触摸检测 ----------
        tp_dev.scan(0);             // 扫描触摸屏
        if (tp_dev.sta & TP_PRES_DOWN)
        {
            uint16_t x = tp_dev.x[0];
            uint16_t y = tp_dev.y[0];

            // 判断按钮区域
            if (x >= BTN_ON_X1 && x <= BTN_ON_X2 && y >= BTN_ON_Y1 && y <= BTN_ON_Y2)
            {
                // 发送 CAN 指令 'A' (亮灯)
                uint8_t data[1] = {'A'};
                can_send_msg(0x13, data, 1);
                // 直接控制LED（也可以让树莓派控制，这里为了方便直接控制）
                LED0(0);
                led_state = 1;
                update_led_display();
                delay_ms(200);      // 简单防抖
            }
            else if (x >= BTN_OFF_X1 && x <= BTN_OFF_X2 && y >= BTN_OFF_Y1 && y <= BTN_OFF_Y2)
            {
                uint8_t data[1] = {'B'};
                can_send_msg(0x13, data, 1);
                LED0(1);
                led_state = 0;
                update_led_display();
                delay_ms(200);
            }
            else if (x >= BTN_MODE_X1 && x <= BTN_MODE_X2 && y >= BTN_MODE_Y1 && y <= BTN_MODE_Y2)
            {
                uint8_t data[1] = {'M'};
                can_send_msg(0x13, data, 1);
                lcd_show_string(30, 120, 200, 16, 16, "Mode Switch!", RED);
                delay_ms(500);
                lcd_show_string(30, 120, 200, 16, 16, "                ", RED); // 清除提示
            }
        }
				uint8_t canbuf[8];
				uint8_t rxlen = can_receive_msg(0x12,canbuf);
        // ---------- CAN 接收处理（轮询标志） ----------
        if (rxlen)
        {
            if (canbuf[0] == 'A')
            {
                LED0(0);
                led_state = 1;
                update_led_display();
                lcd_show_string(30, 60, 200, 16, 16, "Face: Detected", BLUE);
            }
            else if (canbuf[0] ==  'B')
            {
                LED0(1);
                led_state = 0;
                update_led_display();
                lcd_show_string(30, 60, 200, 16, 16, "Face: Unknown", BLUE);
            }
            // 如果树莓派发送了名字，可以在这里解析并显示
        }

        // ---------- 心跳指示（用LED1） ----------
        static uint32_t cnt = 0;
        cnt++;
        if (cnt >= 100)
        {
            LED1_TOGGLE();   // LED1（绿色）闪烁，表示程序运行
            cnt = 0;
        }

        delay_ms(10);       // 主循环周期
    }
}







