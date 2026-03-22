#!/home/juro/.venv/bin/python

import os
import time
from PIL import Image, ImageDraw, ImageFont
from action import Action

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def _load_font(size):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

FONT_TIME = _load_font(22)
FONT_DATE = _load_font(14)


class ShowTimeAction(Action):

    @property
    def title(self):
        return "Show Time"

    def execute(self, lcd):
        image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
        draw = ImageDraw.Draw(image)

        prev_key3 = 0
        while True:
            key3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)
            if key3 == 1 and prev_key3 == 0:
                return
            prev_key3 = key3

            now = time.strftime("%H:%M:%S")
            date = time.strftime("%d.%m.%Y")

            draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")

            # Center time
            tw = draw.textlength(now, font=FONT_TIME)
            draw.text(((lcd.width - tw) / 2, 40), now, fill="WHITE", font=FONT_TIME)

            # Center date
            dw = draw.textlength(date, font=FONT_DATE)
            draw.text(((lcd.width - dw) / 2, 72), date, fill="WHITE", font=FONT_DATE)

            lcd.LCD_ShowImage(image, 0, 0)

            time.sleep(0.2)


action = ShowTimeAction()

if __name__ == "__main__":
    action.run_standalone()
