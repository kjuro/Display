#!/home/juro/.venv/bin/python

import sys
import time
import LCD_1in44
from PIL import Image

image_path = sys.argv[1] if len(sys.argv) > 1 else 'sky.bmp'

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
LCD.LCD_Clear()

image = Image.open(image_path)
LCD.LCD_ShowImage(image, 0, 0)
time.sleep(5)
