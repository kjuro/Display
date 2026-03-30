"""
Pygame-based simulator for the 1.44" LCD HAT.

Provides the same interface as the real LCD class so the application
can run on a normal PC without Raspberry Pi hardware.

Key mapping:
    Arrow keys  → UP / DOWN / LEFT / RIGHT
    Enter       → Joystick press  (KEY_PRESS)
    Space       → KEY1
    Escape      → KEY3
"""

import pygame

SCALE = 4
LCD_WIDTH = 128
LCD_HEIGHT = 128


class _SimPin:
    """Simulated GPIO pin backed by one or more pygame key constants."""

    def __init__(self, *keys):
        self._keys = keys

    @property
    def value(self):
        pressed = pygame.key.get_pressed()
        return int(any(pressed[k] for k in self._keys))


class SimLCD:
    width = LCD_WIDTH
    height = LCD_HEIGHT

    def __init__(self):
        self._screen = None
        self.GPIO_KEY_UP_PIN = _SimPin(pygame.K_UP)
        self.GPIO_KEY_DOWN_PIN = _SimPin(pygame.K_DOWN)
        self.GPIO_KEY_LEFT_PIN = _SimPin(pygame.K_LEFT)
        self.GPIO_KEY_RIGHT_PIN = _SimPin(pygame.K_RIGHT)
        self.GPIO_KEY_PRESS_PIN = _SimPin(pygame.K_RETURN)
        self.GPIO_KEY1_PIN = _SimPin(pygame.K_SPACE)
        self.GPIO_KEY2_PIN = _SimPin()  # unmapped
        self.GPIO_KEY3_PIN = _SimPin(pygame.K_ESCAPE)

    def LCD_Init(self, scan_dir):
        pygame.init()
        self._screen = pygame.display.set_mode(
            (LCD_WIDTH * SCALE, LCD_HEIGHT * SCALE)
        )
        pygame.display.set_caption("LCD 1.44\" Simulator")

    def LCD_Clear(self):
        if self._screen:
            self._screen.fill((0, 0, 0))
            pygame.display.flip()

    def LCD_ShowImage(self, image, x, y):
        if self._screen is None:
            return
        raw = image.convert("RGB").tobytes()
        surface = pygame.image.frombuffer(raw, image.size, "RGB")
        scaled = pygame.transform.scale(
            surface, (LCD_WIDTH * SCALE, LCD_HEIGHT * SCALE)
        )
        self._screen.blit(scaled, (0, 0))
        pygame.display.flip()

    def digital_read(self, pin):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
        return pin.value

    def Brightness(self, duty):
        pass

    def module_exit(self):
        pygame.quit()
