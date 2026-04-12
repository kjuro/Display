from PIL import Image, ImageDraw
import LCD_1in44
import time

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

image = Image.new("RGB", (LCD.width, LCD.height), "RED")
LCD.LCD_ShowImage(image, 0, 0)

time.sleep(2)

image = Image.new("RGB", (LCD.width, LCD.height), "BLACK")
LCD.LCD_ShowImage(image, 0, 0)

time.sleep(2)
