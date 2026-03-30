#!/home/juro/.venv/bin/python

import os
import random
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


FONT_TILE = _load_font(14)
FONT_MSG = _load_font(11)

CELL = 32  # 128 / 4
COLORS = {
    "bg": "#1a1a2e",
    "tile": "#16213e",
    "tile_text": "#e2e2e2",
    "empty": "#0f0f0f",
    "border": "#0f3460",
    "win_bg": "#004d00",
    "win_text": "#00ff00",
}


class FifteenAction(Action):

    @property
    def title(self):
        return "Fifteen"

    def execute(self, lcd):
        board = self._scramble()
        image = Image.new("RGB", (lcd.width, lcd.height), COLORS["bg"])
        draw = ImageDraw.Draw(image)

        self._draw_board(lcd, draw, image, board)

        prev_up = prev_down = prev_left = prev_right = prev_key3 = 0

        while True:
            up = lcd.digital_read(lcd.GPIO_KEY_UP_PIN)
            down = lcd.digital_read(lcd.GPIO_KEY_DOWN_PIN)
            left = lcd.digital_read(lcd.GPIO_KEY_LEFT_PIN)
            right = lcd.digital_read(lcd.GPIO_KEY_RIGHT_PIN)
            key3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)

            if key3 == 1 and prev_key3 == 0:
                return

            moved = False

            # D-pad moves the tile INTO the empty space from that direction
            # UP: tile below empty moves up
            if up == 1 and prev_up == 0:
                moved = self._move(board, 1, 0)
            elif down == 1 and prev_down == 0:
                moved = self._move(board, -1, 0)
            elif left == 1 and prev_left == 0:
                moved = self._move(board, 0, 1)
            elif right == 1 and prev_right == 0:
                moved = self._move(board, 0, -1)
            prev_up, prev_down = up, down
            prev_left, prev_right = left, right
            prev_key3 = key3

            if moved:
                self._draw_board(lcd, draw, image, board)
                if self._is_solved(board):
                    self._draw_win(lcd, draw, image)
                    self.wait_for_key3(lcd)
                    return

            time.sleep(0.05)

    def _scramble(self):
        """Create a solvable scrambled board by making random moves."""
        board = [[(r * 4 + c + 1) % 16 for c in range(4)] for r in range(4)]
        # board[3][3] = 0 (empty)
        er, ec = 3, 3
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for _ in range(200):
            dr, dc = random.choice(directions)
            nr, nc = er + dr, ec + dc
            if 0 <= nr < 4 and 0 <= nc < 4:
                board[er][ec], board[nr][nc] = board[nr][nc], board[er][ec]
                er, ec = nr, nc
        return board

    def _find_empty(self, board):
        for r in range(4):
            for c in range(4):
                if board[r][c] == 0:
                    return r, c
        return 3, 3

    def _move(self, board, dr, dc):
        """Move tile from (er+dr, ec+dc) into empty space (er, ec)."""
        er, ec = self._find_empty(board)
        sr, sc = er + dr, ec + dc
        if 0 <= sr < 4 and 0 <= sc < 4:
            board[er][ec], board[sr][sc] = board[sr][sc], board[er][ec]
            return True
        return False

    def _is_solved(self, board):
        expected = 1
        for r in range(4):
            for c in range(4):
                if r == 3 and c == 3:
                    return board[r][c] == 0
                if board[r][c] != expected:
                    return False
                expected += 1
        return True

    def _draw_board(self, lcd, draw, image, board):
        draw.rectangle((0, 0, lcd.width, lcd.height), fill=COLORS["bg"])
        for r in range(4):
            for c in range(4):
                x = c * CELL
                y = r * CELL
                val = board[r][c]
                if val == 0:
                    draw.rectangle((x + 1, y + 1, x + CELL - 1, y + CELL - 1),
                                   fill=COLORS["empty"])
                else:
                    draw.rectangle((x + 1, y + 1, x + CELL - 1, y + CELL - 1),
                                   fill=COLORS["tile"], outline=COLORS["border"])
                    txt = str(val)
                    tw = draw.textlength(txt, font=FONT_TILE)
                    tx = x + (CELL - tw) / 2
                    ty = y + (CELL - 16) / 2
                    draw.text((tx, ty), txt, fill=COLORS["tile_text"], font=FONT_TILE)
        lcd.LCD_ShowImage(image, 0, 0)

    def _draw_win(self, lcd, draw, image):
        draw.rectangle((14, 48, 114, 80), fill=COLORS["win_bg"], outline=COLORS["win_text"])
        msg = "YOU WIN!"
        tw = draw.textlength(msg, font=FONT_MSG)
        draw.text(((lcd.width - tw) / 2, 56), msg, fill=COLORS["win_text"], font=FONT_MSG)
        lcd.LCD_ShowImage(image, 0, 0)


action = FifteenAction()

if __name__ == "__main__":
    action.run_standalone()
