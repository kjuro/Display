#!/home/juro/.venv/bin/python

import os
import subprocess
import time
from PIL import Image, ImageDraw
from action import Action


class ShutdownAction(Action):

    @property
    def title(self):
        return "Shutdown"

    def execute(self, lcd):
        image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
        draw = ImageDraw.Draw(image)

        # Confirmation screen
        draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")
        draw.text((15, 30), "Shutdown?", fill="RED")
        draw.text((10, 55), "K1: Yes  K3: No", fill="WHITE")
        lcd.LCD_ShowImage(image, 0, 0)

        prev_key1 = prev_press = prev_key3 = 1
        while True:
            key1 = lcd.digital_read(lcd.GPIO_KEY1_PIN)
            press = lcd.digital_read(lcd.GPIO_KEY_PRESS_PIN)
            key3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)

            # Cancel
            if key3 == 1 and prev_key3 == 0:
                return

            # Confirm
            ok = (key1 == 1 and prev_key1 == 0) or (press == 1 and prev_press == 0)
            if ok:
                draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")
                draw.text((10, 50), "Shutting down...", fill="RED")
                lcd.LCD_ShowImage(image, 0, 0)
                time.sleep(1)
                lcd.module_exit()
                subprocess.run(["sudo", "shutdown", "-h", "now"])
                return

            prev_key1 = key1
            prev_press = press
            prev_key3 = key3
            time.sleep(0.05)


action = ShutdownAction()

if __name__ == "__main__":
    action.run_standalone()
