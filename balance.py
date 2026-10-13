#!/home/juro/.venv/bin/python
"""
balance.py — Wii Balance Board balance game.

Steer the red ball with your body weight and hit the coloured targets.
Each hit scores a point and spawns a new target.
"""

import os
import random
import socket
import threading
import time

from PIL import Image, ImageDraw, ImageFont
from action import Action

# Reuse BT helpers and constants from scale.py
from scale import (
    DEVICE_ADDRESS, HID_CONTROL, HID_INTERRUPT,
    connect, drain, avg_raw, read_frames,
)

# ── fonts ─────────────────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size):
    for path in _FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


_FONT_TITLE = _load_font(11)
_FONT_LARGE = _load_font(20)
_FONT_SMALL = _load_font(9)

# Target colours cycling in order
_TARGET_COLORS = ["GREEN", "CYAN", "MAGENTA", "ORANGE", "YELLOW"]

# Play-field constants (128×128 screen, 1 px inset)
PAD       = 1
BALL_R    = 5     # red ball radius
TGT_MIN   = 5     # target min side length (px)
TGT_MAX   = 32    # target max side length (px) – 1/4 of 128
BALANCE_SCALE = 2.0   # amplifier for sensor imbalance → screen offset


def _new_target(bx, by, bw, bh, color_idx):
    """Return (x1, y1, x2, y2, color) for a new filled rect fully inside the box."""
    tw = random.randint(TGT_MIN, TGT_MAX)
    th = random.randint(TGT_MIN, TGT_MAX)
    x1 = random.randint(bx + 2, bx + bw - tw - 2)
    y1 = random.randint(by + 2, by + bh - th - 2)
    color = _TARGET_COLORS[color_idx % len(_TARGET_COLORS)]
    return x1, y1, x1 + tw, y1 + th, color


class BalanceAction(Action):

    @property
    def title(self):
        return "Balance"

    def execute(self, lcd):
        W = lcd.width   # 128
        H = lcd.height  # 128
        image = Image.new("RGB", (W, H), "BLACK")
        draw  = ImageDraw.Draw(image)

        def _render_status(msg1, msg2="", msg3=""):
            draw.rectangle((0, 0, W, H), fill="BLACK")
            draw.rectangle((0, 0, W, 14), fill="BLUE")
            draw.text((4, 2), "Balance", font=_FONT_TITLE, fill="WHITE")
            draw.text((4, 18), msg1, font=_FONT_SMALL, fill="YELLOW")
            if msg2:
                draw.text((4, 30), msg2, font=_FONT_SMALL, fill="WHITE")
            if msg3:
                draw.text((4, 42), msg3, font=_FONT_SMALL, fill="WHITE")
            draw.text((4, H - 12), "K3: Back", font=_FONT_SMALL, fill=(80, 80, 255))
            lcd.LCD_ShowImage(image, 0, 0)

        # ── connect ───────────────────────────────────────────────────────────
        ctrl = intr = None
        for attempt in range(1, 6):
            if lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
                return
            _render_status(f"Connecting {attempt}/5...", "Press SYNC button", "on the board")
            result     = [None]

            def _try_connect():
                try:
                    result[0] = connect(timeout=8)
                except OSError:
                    pass

            t = threading.Thread(target=_try_connect, daemon=True)
            t.start()
            deadline = time.time() + 9
            while t.is_alive() and time.time() < deadline:
                if lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
                    return
                time.sleep(0.1)
            t.join(timeout=1)

            if result[0] is not None:
                ctrl, intr = result[0]
                break
            if attempt < 5:
                _render_status(f"Retry {attempt}/5", "Press SYNC again", "")
                for _ in range(20):
                    if lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
                        return
                    time.sleep(0.1)

        if ctrl is None:
            _render_status("Connect failed!", "Board powered on?", "K3 to go back")
            self.wait_for_key3(lcd)
            return

        try:
            # ── initialise board ──────────────────────────────────────────────
            drain(intr)
            intr.send(bytes([0xa2, 0x11, 0x10]))
            time.sleep(0.2)
            drain(intr)
            intr.send(bytes([0xa2, 0x12, 0x00, 0x32]))
            last_keepalive = time.time()

            # ── tare ──────────────────────────────────────────────────────────
            for secs in range(3, 0, -1):
                _render_status("Step OFF board!", f"Taring in {secs}s...", "")
                if lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
                    return
                time.sleep(1.0)

            _render_status("Taring...", "Hold still", "")
            drain(intr)
            tare_frames = read_frames(intr, n=30, timeout=8.0)
            if len(tare_frames) < 5:
                _render_status("Tare failed!", "Check connection", "K3 to go back")
                self.wait_for_key3(lcd)
                return
            tare = avg_raw(tare_frames)

            # ── game state ────────────────────────────────────────────────────
            bx, by = PAD, PAD
            bw, bh = W - 2 * PAD, H - 2 * PAD
            cx = bx + bw // 2
            cy = by + bh // 2

            score      = 0
            color_idx  = 0
            tgt_x1, tgt_y1, tgt_x2, tgt_y2, tgt_color = _new_target(bx, by, bw, bh, color_idx)

            # Ball starts at centre
            ball_x, ball_y = cx, cy

            prev_k3 = 0
            tr_r = br_r = tl_r = bl_r = None

            while True:
                k3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)
                if k3 == 1 and prev_k3 == 0:
                    break
                prev_k3 = k3

                if time.time() - last_keepalive >= 10:
                    try:
                        intr.send(bytes([0xa2, 0x11, 0x10]))
                        last_keepalive = time.time()
                    except OSError:
                        break

                # Drain all queued packets; keep freshest frame
                intr.settimeout(0.0)
                got_frame = False
                conn_lost = False
                for _ in range(30):
                    try:
                        d = intr.recv(23)
                    except BlockingIOError:
                        break
                    except socket.timeout:
                        break
                    except OSError:
                        conn_lost = True
                        break
                    if not d:
                        conn_lost = True
                        break
                    if len(d) >= 2 and d[1] == 0x20:
                        try:
                            intr.send(bytes([0xa2, 0x15, 0x00]))
                        except OSError:
                            pass
                    elif len(d) >= 12 and d[1] == 0x32:
                        tr_r = (d[4]  << 8) | d[5]
                        br_r = (d[6]  << 8) | d[7]
                        tl_r = (d[8]  << 8) | d[9]
                        bl_r = (d[10] << 8) | d[11]
                        got_frame = True

                if conn_lost:
                    break

                if not got_frame:
                    time.sleep(0.02)
                    continue

                # Compute balance offsets from tare
                tr = max(0.0, (tr_r - tare[0]))
                br = max(0.0, (br_r - tare[1]))
                tl = max(0.0, (tl_r - tare[2]))
                bl = max(0.0, (bl_r - tare[3]))
                total = tr + br + tl + bl

                if total > 500:  # only move ball when standing on board
                    x_off = (tr + br - tl - bl) / total
                    y_off = (tr + tl - br - bl) / total
                    x_off = max(-1.0, min(1.0, x_off * BALANCE_SCALE))
                    y_off = max(-1.0, min(1.0, y_off * BALANCE_SCALE))
                    half_x = bw // 2 - BALL_R - 2
                    half_y = bh // 2 - BALL_R - 2
                    ball_x = int(cx + x_off * half_x)
                    ball_y = int(cy - y_off * half_y)
                    ball_x = max(bx + BALL_R + 1, min(bx + bw - BALL_R - 1, ball_x))
                    ball_y = max(by + BALL_R + 1, min(by + bh - BALL_R - 1, ball_y))

                # Hit detection: ball circle overlaps target rectangle
                closest_x = max(tgt_x1, min(ball_x, tgt_x2))
                closest_y = max(tgt_y1, min(ball_y, tgt_y2))
                dist2 = (ball_x - closest_x) ** 2 + (ball_y - closest_y) ** 2
                if dist2 <= BALL_R * BALL_R:
                    score += 1
                    color_idx += 1
                    tgt_x1, tgt_y1, tgt_x2, tgt_y2, tgt_color = _new_target(bx, by, bw, bh, color_idx)

                self._draw_frame(lcd, draw, image,
                                 W, H, bx, by, bw, bh, cx, cy,
                                 ball_x, ball_y,
                                 tgt_x1, tgt_y1, tgt_x2, tgt_y2, tgt_color,
                                 score, total > 500)

        finally:
            for sock in (ctrl, intr):
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass

    @staticmethod
    def _draw_frame(lcd, draw, image,
                    W, H, bx, by, bw, bh, cx, cy,
                    ball_x, ball_y,
                    tgt_x1, tgt_y1, tgt_x2, tgt_y2, tgt_color,
                    score, on_board):
        draw.rectangle((0, 0, W, H), fill="BLACK")

        # Board outline
        draw.rectangle((bx, by, bx + bw, by + bh), outline=(80, 80, 80))

        # Cross-hair
        draw.line((bx + 1, cy, bx + bw - 1, cy), fill=(60, 60, 60), width=1)
        draw.line((cx, by + 1, cx, by + bh - 1), fill=(60, 60, 60), width=1)

        # Score – 4 digits, bottom-right corner
        score_str = f"{score:04d}"
        try:
            sb = _FONT_TITLE.getbbox(score_str)
            sw = sb[2] - sb[0]
            sh = sb[3] - sb[1]
        except AttributeError:
            sw, sh = len(score_str) * 7, 12
        draw.text((bx + bw - sw - 3, by + bh - sh - 7), score_str, font=_FONT_TITLE, fill=(200, 200, 200))

        # Target – filled rectangle
        draw.rectangle((tgt_x1, tgt_y1, tgt_x2, tgt_y2), fill=tgt_color)

        # Red ball (dimmed when not on board)
        ball_color = "RED" if on_board else (100, 0, 0)
        draw.ellipse(
            (ball_x - BALL_R, ball_y - BALL_R,
             ball_x + BALL_R, ball_y + BALL_R),
            fill=ball_color,
        )

        lcd.LCD_ShowImage(image, 0, 0)


action = BalanceAction()
