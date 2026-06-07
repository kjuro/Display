#!/home/juro/.venv/bin/python
"""
scale.py — Wii Balance Board weight reader.

As an LCD action: imported by main.py; shows live weight and a balance
visualisation (cross-hair + red dot) on the 128×128 LCD.

Standalone CLI (calibration / terminal live view):
  python3 scale.py          — live readings (requires scale_cal.json)
  python3 scale.py --recal  — interactive calibration
"""

import json
import os
import socket
import threading
import time

from PIL import Image, ImageDraw, ImageFont
from action import Action

DEVICE_ADDRESS = "00:22:4C:4E:8B:EE"
HID_CONTROL    = 0x11
HID_INTERRUPT  = 0x13
CAL_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scale_cal.json")

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

# ── low-level helpers ─────────────────────────────────────────────────────────

def connect(timeout=20):
    ctrl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    intr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    ctrl.settimeout(timeout)
    intr.settimeout(timeout)
    ctrl.connect((DEVICE_ADDRESS, HID_CONTROL))
    intr.connect((DEVICE_ADDRESS, HID_INTERRUPT))
    return ctrl, intr


def wait_for_enter(intr, prompt):
    """Wait for Enter while a background thread keeps the board connection alive."""
    stop = threading.Event()
    last_ka = [time.time()]

    def _pump():
        while not stop.is_set():
            try:
                intr.settimeout(0.5)
                data = intr.recv(23)
                if not data:
                    break
                if len(data) >= 2 and data[1] == 0x20:
                    try:
                        intr.send(bytes([0xa2, 0x15, 0x00]))
                    except OSError:
                        break
            except (TimeoutError, socket.timeout):
                pass
            except OSError:
                break
            if time.time() - last_ka[0] >= 5:
                try:
                    intr.send(bytes([0xa2, 0x11, 0x10]))
                    last_ka[0] = time.time()
                except OSError:
                    break

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    input(prompt)
    stop.set()
    t.join(timeout=2)


def drain(sock, seconds=0.5):
    """Discard incoming packets for up to `seconds` wall-clock time."""
    deadline = time.time() + seconds
    sock.settimeout(0.05)
    while time.time() < deadline:
        try:
            data = sock.recv(23)
            if not data:
                break
        except Exception:
            break


def read_frames(intr, n=10, timeout=5.0):
    """Read up to n balance data frames; return list of (tr, br, tl, bl) raw."""
    intr.settimeout(0.5)
    frames = []
    deadline = time.time() + timeout
    while len(frames) < n and time.time() < deadline:
        try:
            data = intr.recv(23)
        except (TimeoutError, socket.timeout):
            continue
        except OSError:
            break
        if len(data) >= 2 and data[1] == 0x20:
            try:
                intr.send(bytes([0xa2, 0x15, 0x00]))
            except OSError:
                break
            continue
        if len(data) >= 12 and data[1] == 0x32:
            frames.append((
                (data[4]  << 8) | data[5],
                (data[6]  << 8) | data[7],
                (data[8]  << 8) | data[9],
                (data[10] << 8) | data[11],
            ))
    return frames


def avg_raw(frames):
    if not frames:
        return (0, 0, 0, 0)
    n = len(frames)
    return tuple(sum(f[i] for f in frames) / n for i in range(4))


# ── LCD Action ────────────────────────────────────────────────────────────────

class ScaleAction(Action):

    @property
    def title(self):
        return "Scale"

    def execute(self, lcd):
        W = lcd.width   # 128
        H = lcd.height  # 128
        image = Image.new("RGB", (W, H), "BLACK")
        draw  = ImageDraw.Draw(image)

        def _render_status(msg1, msg2="", msg3=""):
            draw.rectangle((0, 0, W, H), fill="BLACK")
            draw.rectangle((0, 0, W, 14), fill="BLUE")
            draw.text((4, 2), "Scale", font=_FONT_TITLE, fill="WHITE")
            draw.text((4, 18), msg1, font=_FONT_SMALL, fill="YELLOW")
            if msg2:
                draw.text((4, 30), msg2, font=_FONT_SMALL, fill="WHITE")
            if msg3:
                draw.text((4, 42), msg3, font=_FONT_SMALL, fill="WHITE")
            draw.text((4, H - 12), "K3: Back", font=_FONT_SMALL, fill=(80, 80, 255))
            lcd.LCD_ShowImage(image, 0, 0)

        # ── check calibration ─────────────────────────────────────────────────
        if not os.path.exists(CAL_FILE):
            _render_status("No calibration!", "Run scale.py --recal", "from terminal")
            self.wait_for_key3(lcd)
            return

        with open(CAL_FILE) as f:
            saved = json.load(f)
        scale_factor = saved.get("kg_per_adc")
        if not scale_factor:
            _render_status("Bad cal file!", "Run scale.py --recal", "from terminal")
            self.wait_for_key3(lcd)
            return

        # ── connect ───────────────────────────────────────────────────────────
        ctrl = intr = None
        for attempt in range(1, 6):
            if lcd.digital_read(lcd.GPIO_KEY3_PIN) == 1:
                return
            _render_status(f"Connecting {attempt}/5...", "Press SYNC button", "on the board")
            result     = [None]
            exc_holder = [None]

            def _try_connect():
                try:
                    result[0] = connect(timeout=8)
                except OSError as e:
                    exc_holder[0] = e

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
            intr.send(bytes([0xa2, 0x11, 0x10]))        # LED on
            time.sleep(0.2)
            drain(intr)
            intr.send(bytes([0xa2, 0x12, 0x00, 0x32]))  # balance-board report mode
            last_keepalive = time.time()

            # ── tare with countdown (board must be empty) ─────────────────────
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

            # ── live display loop ─────────────────────────────────────────────
            prev_k3 = 0
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

                intr.settimeout(0.3)
                try:
                    data = intr.recv(23)
                except (TimeoutError, socket.timeout):
                    continue
                except OSError:
                    break

                if len(data) >= 2 and data[1] == 0x20:
                    try:
                        intr.send(bytes([0xa2, 0x15, 0x00]))
                    except OSError:
                        pass
                    continue
                if len(data) < 12 or data[1] != 0x32:
                    continue

                tr_r = (data[4]  << 8) | data[5]
                br_r = (data[6]  << 8) | data[7]
                tl_r = (data[8]  << 8) | data[9]
                bl_r = (data[10] << 8) | data[11]

                tr = max(0.0, (tr_r - tare[0]) * scale_factor)
                br = max(0.0, (br_r - tare[1]) * scale_factor)
                tl = max(0.0, (tl_r - tare[2]) * scale_factor)
                bl = max(0.0, (bl_r - tare[3]) * scale_factor)
                total = tr + br + tl + bl

                self._draw_live(lcd, draw, image, W, H, total, tr, br, tl, bl)

        finally:
            for sock in (ctrl, intr):
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass

    @staticmethod
    def _draw_live(lcd, draw, image, W, H, total, tr, br, tl, bl):
        """
        Render the live weight + balance visualisation.

        Layout (128 × 128):
          y  0-14  : blue title bar "Scale"
          y 16-37  : total weight in large font
          y 40-118 : balance box with cross-hair and red balance dot
          y 120-128: footer hint
        """
        draw.rectangle((0, 0, W, H), fill="BLACK")

        # Title bar
        draw.rectangle((0, 0, W, 14), fill="BLUE")
        draw.text((4, 2), "Scale", font=_FONT_TITLE, fill="WHITE")

        # Total weight – centred
        weight_str = f"{total:.1f} kg"
        try:
            bbox = _FONT_LARGE.getbbox(weight_str)
            tw = bbox[2] - bbox[0]
        except AttributeError:
            tw = len(weight_str) * 10
        draw.text(((W - tw) // 2, 16), weight_str, font=_FONT_LARGE, fill="WHITE")

        # Balance visualisation box (78 × 78 centred horizontally)
        BOX = 78
        bx = (W - BOX) // 2   # left edge  → 25
        by = 40                # top edge

        # Board outline (dark grey rectangle)
        draw.rectangle((bx, by, bx + BOX, by + BOX), outline=(80, 80, 80))

        # Cross-hair lines through the centre
        cx = bx + BOX // 2
        cy = by + BOX // 2
        draw.line((bx + 1, cy, bx + BOX - 1, cy), fill=(160, 160, 160), width=1)
        draw.line((cx, by + 1, cx, by + BOX - 1), fill=(160, 160, 160), width=1)

        # Red balance dot – only when board is bearing weight
        if total > 1.0:
            # x_off: +1 = all weight on right side, -1 = all weight on left side
            # y_off: +1 = all weight on top/back,   -1 = all weight on front
            x_off = (tr + br - tl - bl) / total
            y_off = (tr + tl - br - bl) / total
            radius = BOX // 2 - 7
            ball_x = int(cx + x_off * radius)
            ball_y = int(cy - y_off * radius)   # screen Y is inverted
            ball_r = 5
            draw.ellipse(
                (ball_x - ball_r, ball_y - ball_r,
                 ball_x + ball_r, ball_y + ball_r),
                fill="RED",
            )

        # Footer
        draw.text((4, H - 11), "K3: Back", font=_FONT_SMALL, fill=(80, 80, 255))

        lcd.LCD_ShowImage(image, 0, 0)


action = ScaleAction()


# ── standalone CLI (calibration / live terminal readings) ─────────────────────

if __name__ == "__main__":
    import sys

    READ_SECONDS = 60
    RECAL        = "--recal" in sys.argv

    print("Wii Balance Board")
    print(f"  Board: {DEVICE_ADDRESS}")
    print()

    ctrl = intr = None
    attempt = 0
    while True:
        attempt += 1
        print(f"  Press the RED SYNC button (bottom of board)…", end=" ", flush=True)
        try:
            ctrl, intr = connect(timeout=20)
            print("connected!")
            break
        except OSError as e:
            print(f"no connection ({e})")
            if attempt < 5:
                print(f"  Waiting 3 s — press SYNC again to retry.")
                time.sleep(3)
            else:
                print("  Too many failed attempts. Is the board powered on?")
                sys.exit(1)

    drain(intr)
    intr.send(bytes([0xa2, 0x11, 0x10]))        # LED on → stops blinking
    time.sleep(0.2)
    drain(intr)
    intr.send(bytes([0xa2, 0x12, 0x00, 0x32]))  # reporting mode: balance board
    last_keepalive = time.time()

    scale_factor = None
    tare = (0, 0, 0, 0)
    tare_total = 0

    if not RECAL and os.path.exists(CAL_FILE):
        with open(CAL_FILE) as f:
            saved = json.load(f)
        scale_factor = saved.get("kg_per_adc")
        print(f"  Calibration loaded: {scale_factor:.6f} kg/ADC")
        wait_for_enter(intr, "  Board empty? Press Enter to tare…")
        drain(intr)
        print("  Taring…", end=" ", flush=True)
        tare_frames = read_frames(intr, n=30, timeout=8.0)
        if len(tare_frames) < 5:
            print("failed (too few frames). Check connection.")
            ctrl.close(); intr.close(); sys.exit(1)
        tare = avg_raw(tare_frames)
        tare_total = sum(tare)
        print(f"ok  (tare={tare_total:.0f} raw)")

    if scale_factor is None:
        print()
        print("  ── Calibration needed ────────────────────────────────────────")
        print("  Board must be EMPTY for this step (nobody on it).")
        wait_for_enter(intr, "  Press Enter when board is empty and on flat ground…")
        drain(intr)
        time.sleep(0.5)

        print("  Measuring tare…", end=" ", flush=True)
        tare_frames = read_frames(intr, n=30, timeout=8.0)
        if len(tare_frames) < 5:
            print("failed — try again.")
            ctrl.close(); intr.close(); sys.exit(1)
        tare = avg_raw(tare_frames)
        tare_total = sum(tare)
        print(f"ok  (tare={tare_total:.0f} raw)")

        print()
        print("  Now stand on the board, hold STILL, then press Enter.")
        wait_for_enter(intr, "  Press Enter when standing still…")
        drain(intr)
        time.sleep(1.0)

        print("  Measuring load (taking 30 samples)…", end=" ", flush=True)
        load_frames = read_frames(intr, n=30, timeout=8.0)
        if len(load_frames) < 5:
            print("failed — try again.")
            ctrl.close(); intr.close(); sys.exit(1)
        loaded = avg_raw(load_frames)
        loaded_total = sum(loaded)
        delta = loaded_total - tare_total
        print(f"ok  (loaded={loaded_total:.0f}, delta={delta:.0f})")

        if delta < 2000:
            print(f"  ERROR: delta={delta:.0f} is too small.")
            print("  Make sure the board was EMPTY during tare, and you were")
            print("  standing firmly on it before pressing Enter for the load step.")
            print("  Delete scale_cal.json and re-run to try again.")
            ctrl.close(); intr.close(); sys.exit(1)

        try:
            ref_kg = float(input("  Enter your weight in kg: "))
        except ValueError:
            print("  Invalid input — aborting.")
            ctrl.close(); intr.close(); sys.exit(1)

        scale_factor = ref_kg / delta
        with open(CAL_FILE, "w") as f:
            json.dump({"kg_per_adc": scale_factor, "ref_kg": ref_kg, "delta": delta}, f)
        print(f"  Calibration saved: {scale_factor:.6f} kg/ADC  (delta={delta:.0f}  →  {ref_kg} kg)")
        print("  Step off the board now.")
        print("  Press SYNC to reconnect for the live reading session.")
        ctrl.close()
        intr.close()
        time.sleep(2)

        attempt = 0
        while True:
            attempt += 1
            print(f"  Press the RED SYNC button…", end=" ", flush=True)
            try:
                ctrl, intr = connect(timeout=20)
                print("connected!")
                break
            except OSError as e:
                print(f"no connection ({e})")
                if attempt < 5:
                    time.sleep(3)
                else:
                    print("  Too many failed attempts.")
                    sys.exit(1)
        drain(intr)
        intr.send(bytes([0xa2, 0x11, 0x10]))
        time.sleep(0.2)
        drain(intr)
        intr.send(bytes([0xa2, 0x12, 0x00, 0x32]))
        last_keepalive = time.time()

        wait_for_enter(intr, "  Board is empty? Press Enter to tare — then live readings start…")
        drain(intr)
        print("  Taring…", end=" ", flush=True)
        tare_frames = read_frames(intr, n=30, timeout=8.0)
        if tare_frames:
            tare = avg_raw(tare_frames)
            tare_total = sum(tare)
            print(f"ok  (tare={tare_total:.0f} raw)")
        else:
            print("failed — using initial tare")

    print()
    print(f"  Reading for {READ_SECONDS} s  (Ctrl-C to stop)")
    print(f"  {'Time':>5}  {'TOTAL':>8}  {'TR':>7}  {'BR':>7}  {'TL':>7}  {'BL':>7}")
    print(f"  {'(s)':>5}  {'kg':>8}  {'kg':>7}  {'kg':>7}  {'kg':>7}  {'kg':>7}")
    print("  " + "─" * 54)

    start = time.time()
    last_print = 0.0
    frames_read = 0

    try:
        while True:
            elapsed = time.time() - start
            if elapsed >= READ_SECONDS:
                break

            if time.time() - last_keepalive >= 10:
                intr.send(bytes([0xa2, 0x11, 0x10]))
                last_keepalive = time.time()

            intr.settimeout(1.0)
            try:
                data = intr.recv(23)
            except (TimeoutError, socket.timeout):
                continue
            except OSError as e:
                print(f"\n  Connection lost: {e}")
                break

            if len(data) >= 2 and data[1] == 0x20:
                try:
                    intr.send(bytes([0xa2, 0x15, 0x00]))
                except OSError:
                    pass
                continue
            if len(data) < 12 or data[1] != 0x32:
                continue

            tr_r = (data[4]  << 8) | data[5]
            br_r = (data[6]  << 8) | data[7]
            tl_r = (data[8]  << 8) | data[9]
            bl_r = (data[10] << 8) | data[11]
            frames_read += 1

            if elapsed - last_print < 0.25:
                continue
            last_print = elapsed

            tr    = max(0.0, (tr_r - tare[0]) * scale_factor)
            br    = max(0.0, (br_r - tare[1]) * scale_factor)
            tl    = max(0.0, (tl_r - tare[2]) * scale_factor)
            bl    = max(0.0, (bl_r - tare[3]) * scale_factor)
            total = tr + br + tl + bl
            print(f"  {elapsed:5.1f}  {total:8.2f}  {tr:7.2f}  {br:7.2f}  {tl:7.2f}  {bl:7.2f}")

    except KeyboardInterrupt:
        print()
        print("  Stopped.")
    finally:
        ctrl.close()
        intr.close()
