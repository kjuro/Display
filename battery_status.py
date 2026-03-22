#!/home/juro/.venv/bin/python

import time
from PIL import Image, ImageDraw
from action import Action
from UPS import INA219


class BatteryStatusAction(Action):

    @property
    def title(self):
        return "Battery Status"

    def execute(self, lcd):
        ina219 = INA219(addr=0x43)
        image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
        draw = ImageDraw.Draw(image)

        prev_key3 = 0
        while True:
            key3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)
            if key3 == 1 and prev_key3 == 0:
                return
            prev_key3 = key3

            bus_voltage = ina219.getBusVoltage_V()
            current = ina219.getCurrent_mA()
            power = ina219.getPower_W()
            percent = (bus_voltage - 3) / 1.2 * 100
            percent = max(0, min(100, percent))

            draw.rectangle((0, 0, lcd.width, lcd.height), fill="BLACK")

            # Title
            draw.rectangle((0, 0, lcd.width, 16), fill="BLUE")
            draw.text((20, 2), "Battery Status", fill="WHITE")

            # Battery percentage with color
            if percent > 50:
                color = "GREEN"
            elif percent > 20:
                color = "YELLOW"
            else:
                color = "RED"

            y = 22
            draw.text((5, y), "{:.1f}%".format(percent), fill=color)

            # Battery bar
            bar_x = 55
            bar_w = lcd.width - bar_x - 5
            bar_h = 10
            draw.rectangle((bar_x, y, bar_x + bar_w, y + bar_h), outline="WHITE")
            fill_w = int(bar_w * percent / 100)
            if fill_w > 0:
                draw.rectangle((bar_x + 1, y + 1, bar_x + fill_w, y + bar_h - 1), fill=color)

            # Details
            y = 40
            draw.text((5, y),      "Voltage: {:.2f} V".format(bus_voltage), fill="WHITE")
            draw.text((5, y + 16), "Current: {:.0f} mA".format(current), fill="WHITE")
            draw.text((5, y + 32), "Power:   {:.2f} W".format(power), fill="WHITE")

            # Footer
            draw.rectangle((0, lcd.height - 14, lcd.width, lcd.height), fill="BLUE")
            draw.text((10, lcd.height - 13), "KEY3: Back", fill="YELLOW")

            lcd.LCD_ShowImage(image, 0, 0)
            time.sleep(1)


action = BatteryStatusAction()

if __name__ == "__main__":
    action.run_standalone()
