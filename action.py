#!/home/juro/.venv/bin/python

import LCD_1in44
import time
from abc import ABC, abstractmethod


class Action(ABC):

    @property
    @abstractmethod
    def title(self):
        pass

    @abstractmethod
    def execute(self, lcd):
        """Run the action. Return when KEY3 is pressed or action is done."""
        pass

    def wait_for_key3(self, lcd):
        """Block until KEY3 is pressed and released."""
        while lcd.digital_read(lcd.GPIO_KEY3_PIN) == 0:
            time.sleep(0.05)
        while lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
            time.sleep(0.05)

    def is_key3_pressed(self, lcd):
        """Return True if KEY3 just transitioned to pressed."""
        return lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1

    def run_standalone(self):
        """Run this action standalone, then exit."""
        lcd = LCD_1in44.LCD()
        lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        lcd.LCD_Clear()
        try:
            self.execute(lcd)
        except KeyboardInterrupt:
            pass
        finally:
            lcd.module_exit()
