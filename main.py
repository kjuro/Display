#!/home/juro/.venv/bin/python

import LCD_1in44
import time

from PIL import Image, ImageDraw, ImageFont, ImageColor

from show_time import action as show_time_action
from shutdown import action as shutdown_action
from restart import action as restart_action
from battery_status import action as battery_status_action
from fifteen import action as fifteen_action
from walking_pad import action as walking_pad_action

# Register all actions here
ACTIONS = [
    show_time_action,
    battery_status_action,
    walking_pad_action,
    fifteen_action,
    restart_action,
    shutdown_action,
]

EXIT_LABEL = "Exit"


def draw_menu(lcd, draw, image, menu_items, selected, scroll_offset):
    draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")

    # Title bar
    draw.rectangle((0, 0, lcd.width, 16), fill="BLUE")
    draw.text((30, 2), "= MENU =", fill="WHITE")

    # Footer
    draw.rectangle((0, lcd.height - 14, lcd.width, lcd.height), fill="BLUE")
    draw.text((8, lcd.height - 13), "UP/DN:Nav K1:OK K3:Back", fill="WHITE")

    # Visible area for menu items
    item_height = 16
    menu_top = 18
    menu_bottom = lcd.height - 14
    visible_count = (menu_bottom - menu_top) // item_height

    # Draw visible items
    y = menu_top
    for i in range(scroll_offset, min(scroll_offset + visible_count, len(menu_items))):
        item = menu_items[i]
        if i == selected:
            draw.rectangle((2, y, lcd.width - 2, y + item_height - 2), fill="WHITE")
            draw.text((8, y + 1), "> " + item, fill="BLACK")
        else:
            draw.text((8, y + 1), "  " + item, fill="WHITE")
        y += item_height

    # Scroll indicators
    if scroll_offset > 0:
        draw.text((lcd.width - 12, menu_top), "^", fill="YELLOW")
    if scroll_offset + visible_count < len(menu_items):
        draw.text((lcd.width - 12, menu_bottom - item_height), "v", fill="YELLOW")

    lcd.LCD_ShowImage(image, 0, 0)


def main():
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

    try:
        lcd.LCD_Clear()

        # Show splash image for 3 seconds
        splash = Image.open("images/sky.bmp")
        lcd.LCD_ShowImage(splash, 0, 0)
        time.sleep(3)

        # Show time until any button is pressed
        show_time_action.execute(lcd)

        # Build menu: action titles + Exit
        actions_by_title = {a.title: a for a in ACTIONS}
        menu_items = [a.title for a in ACTIONS] + [EXIT_LABEL]

        image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
        draw = ImageDraw.Draw(image)

        selected = 0
        scroll_offset = 0
        item_height = 16
        menu_top = 18
        menu_bottom = lcd.height - 14
        visible_count = (menu_bottom - menu_top) // item_height
        prev_up = prev_down = prev_key1 = prev_press = prev_key3 = 1

        draw_menu(lcd, draw, image, menu_items, selected, scroll_offset)

        while True:
            up    = lcd.digital_read(lcd.GPIO_KEY_UP_PIN)
            down  = lcd.digital_read(lcd.GPIO_KEY_DOWN_PIN)
            key1  = lcd.digital_read(lcd.GPIO_KEY1_PIN)
            press = lcd.digital_read(lcd.GPIO_KEY_PRESS_PIN)
            key3  = lcd.digital_read(lcd.GPIO_KEY3_PIN)

            redraw = False

            # Buttons: 0 = released, 1 = pressed (from key_demo.py)
            if up == 1 and prev_up == 0:
                selected = (selected - 1) % len(menu_items)
                if selected < scroll_offset:
                    scroll_offset = selected
                elif selected == len(menu_items) - 1:
                    scroll_offset = max(0, len(menu_items) - visible_count)
                redraw = True
            if down == 1 and prev_down == 0:
                selected = (selected + 1) % len(menu_items)
                if selected >= scroll_offset + visible_count:
                    scroll_offset = selected - visible_count + 1
                elif selected == 0:
                    scroll_offset = 0
                redraw = True
            ok = (key1 == 1 and prev_key1 == 0) or (press == 1 and prev_press == 0)
            if ok:
                item = menu_items[selected]
                if item == EXIT_LABEL:
                    break
                action = actions_by_title[item]
                action.execute(lcd)
                redraw = True

            prev_up = up
            prev_down = down
            prev_key1 = key1
            prev_press = press
            prev_key3 = key3

            if redraw:
                draw_menu(lcd, draw, image, menu_items, selected, scroll_offset)

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        lcd.module_exit()

if __name__ == '__main__':
    main()