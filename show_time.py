#!/home/juro/.venv/bin/python

import os
import time
import datetime
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

FONT_TIME  = _load_font(22)
FONT_DATE  = _load_font(14)
FONT_SMALL = _load_font(9)

# Work schedule in minutes from midnight
_WORK_START  = 7 * 60         # 420
_WORK_END    = 16 * 60        # 960
_LUNCH_START = 12 * 60        # 720
_LUNCH_END   = 12 * 60 + 30   # 750
_WORK_SPAN   = _WORK_END - _WORK_START  # 540
_LUNCH_SPAN  = _LUNCH_END - _LUNCH_START  # 30
_PAID_SPAN   = _WORK_SPAN - _LUNCH_SPAN  # 510 minutes = 8.5 h
_RATE_EUR_H  = 40.0  # EUR per hour


class ShowTimeAction(Action):

    @property
    def title(self):
        return "Show Time"

    def execute(self, lcd):
        image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
        draw = ImageDraw.Draw(image)

        ALL_BUTTONS = [
            lcd.GPIO_KEY_UP_PIN,
            lcd.GPIO_KEY_DOWN_PIN,
            lcd.GPIO_KEY_LEFT_PIN,
            lcd.GPIO_KEY_RIGHT_PIN,
            lcd.GPIO_KEY1_PIN,
            lcd.GPIO_KEY2_PIN,
            lcd.GPIO_KEY3_PIN,
            lcd.GPIO_KEY_PRESS_PIN,
        ]
        prev = {pin: lcd.digital_read(pin) for pin in ALL_BUTTONS}

        while True:
            for pin in ALL_BUTTONS:
                val = lcd.digital_read(pin)
                if val == 1 and prev[pin] == 0:
                    return
                prev[pin] = val

            now_dt   = datetime.datetime.now()
            now_str  = now_dt.strftime("%H:%M:%S")
            date_str = now_dt.strftime("%d.%m.%Y")
            t = now_dt.time()
            now_min  = t.hour * 60 + t.minute + t.second / 60.0

            draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")

            # --- Earned today ---
            if now_min <= _WORK_START:
                earned_min = 0.0
            elif now_min <= _LUNCH_START:
                earned_min = now_min - _WORK_START
            elif now_min <= _LUNCH_END:
                earned_min = _LUNCH_START - _WORK_START
            elif now_min <= _WORK_END:
                earned_min = (_LUNCH_START - _WORK_START) + (now_min - _LUNCH_END)
            else:
                earned_min = _PAID_SPAN
            earned_eur = earned_min / 60.0 * _RATE_EUR_H
            earn_str = f"{earned_eur:.2f} €"

            ew = draw.textlength(earn_str, font=FONT_DATE)
            draw.text(((lcd.width - ew) / 2, 65), earn_str, fill="#00DD00", font=FONT_DATE)

            # --- Time (top) ---
            tw = draw.textlength(now_str, font=FONT_TIME)
            draw.text(((lcd.width - tw) / 2, 14), now_str, fill="WHITE", font=FONT_TIME)

            # --- Date ---
            dw = draw.textlength(date_str, font=FONT_DATE)
            draw.text(((lcd.width - dw) / 2, 40), date_str, fill="WHITE", font=FONT_DATE)

            # --- Progress bar ---
            bar_x1 = 4
            bar_x2 = lcd.width - 4   # 124
            bar_y1 = 90
            bar_y2 = 105
            bar_w  = bar_x2 - bar_x1  # 120

            def time_to_x(minutes):
                frac = max(0.0, min(1.0, (minutes - _WORK_START) / _WORK_SPAN))
                return bar_x1 + int(frac * bar_w)

            lunch_x1 = time_to_x(_LUNCH_START)
            lunch_x2 = time_to_x(_LUNCH_END)
            cur_x    = time_to_x(now_min)

            # Background (gray = remaining work)
            draw.rectangle((bar_x1, bar_y1, bar_x2, bar_y2), fill="#444444")

            # Green = work done
            if now_min > _WORK_START:
                if now_min < _LUNCH_START:
                    draw.rectangle((bar_x1, bar_y1, cur_x, bar_y2), fill="#00CC00")
                elif now_min <= _LUNCH_END:
                    # During lunch: green only up to lunch start
                    draw.rectangle((bar_x1, bar_y1, lunch_x1, bar_y2), fill="#00CC00")
                else:
                    # After lunch: green on both sides of lunch zone
                    draw.rectangle((bar_x1, bar_y1, lunch_x1, bar_y2), fill="#00CC00")
                    draw.rectangle((lunch_x2, bar_y1, cur_x, bar_y2), fill="#00CC00")

            # Orange = lunch break zone
            draw.rectangle((lunch_x1, bar_y1, lunch_x2, bar_y2), fill="#FF8800")

            # White marker = current time
            draw.rectangle((cur_x - 1, bar_y1 - 3, cur_x + 1, bar_y2 + 3), fill="WHITE")

            # Labels below bar
            label_y = bar_y2 + 4
            draw.text((bar_x1, label_y), "7", fill="#888888", font=FONT_SMALL)
            lw12 = draw.textlength("12", font=FONT_SMALL)
            draw.text((lunch_x1 - lw12 / 2, label_y), "12", fill="#FF8800", font=FONT_SMALL)
            lw16 = draw.textlength("16", font=FONT_SMALL)
            draw.text((bar_x2 - lw16, label_y), "16", fill="#888888", font=FONT_SMALL)

            lcd.LCD_ShowImage(image, 0, 0)

            time.sleep(0.2)


action = ShowTimeAction()

if __name__ == "__main__":
    action.run_standalone()
