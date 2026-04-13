#!/home/juro/.venv/bin/python
#
# Walking Pad action — requires: pip install bleak
#
# WalkingPad BLE protocol (KingSmith KS-BLC2):
#   Service              : 0000fe00-0000-1000-8000-00805f9b34fb
#   Notify characteristic: 0000fe01-0000-1000-8000-00805f9b34fb
#   Write characteristic : 0000fe02-0000-1000-8000-00805f9b34fb
#   Command              : f7 a2 <cmd> <param> <checksum> fd  (6 bytes)
#   Status response      : f8 a2 <state> <speed*10> ?? <time:3> <dist:3> <steps:3> ...
#     state : 2=running, 5=standby
#     speed : byte / 10  → km/h
#     time  : UInt24 seconds
#     dist  : UInt24 / 100  → km
#     steps : UInt24

import os
import asyncio
import time
from PIL import Image, ImageDraw, ImageFont
from action import Action

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------
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


FONT_TITLE = _load_font(11)
FONT_LABEL = _load_font(10)
FONT_VALUE = _load_font(13)
FONT_SMALL = _load_font(9)

# ---------------------------------------------------------------------------
# BLE constants
# ---------------------------------------------------------------------------
NOTIFY_UUID = "0000fe01-0000-1000-8000-00805f9b34fb"
WRITE_UUID  = "0000fe02-0000-1000-8000-00805f9b34fb"
# 6-byte command: [0xF7, 0xA2, cmd, param, checksum, 0xFD]
# checksum = (0xA2 + cmd + param) % 256
# cmd 0x00 = query status
# cmd 0x01 = change speed (param: speed * 10, 0 = stop)
# cmd 0x04 = start belt   (param: 1 = start at configured start speed)
CMD_STATUS = bytes([0xf7, 0xa2, 0x00, 0x00, 0xa2, 0xfd])
CMD_START  = bytes([0xf7, 0xa2, 0x04, 0x01, 0xa7, 0xfd])
CMD_STOP   = bytes([0xf7, 0xa2, 0x01, 0x00, 0xa3, 0xfd])

SPEED_MIN = 1.0   # km/h  (device minimum)
SPEED_MAX = 6.0   # km/h


def _make_speed_cmd(speed_kmh: float) -> bytes:
    """Build a set-speed command (opcode 0x01)."""
    param = round(max(0.0, speed_kmh) * 10)
    checksum = (0xa2 + 0x01 + param) % 256
    return bytes([0xf7, 0xa2, 0x01, param, checksum, 0xfd])

# Device name fragments to match (case-insensitive)
PAD_NAME_HINTS = ("walkingpad", "ks-", "walking pad", "treadmill")

STATE_LABELS = {1: "running", 5: "standby"}


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
class PadStatus:
    def __init__(self):
        self.speed    = 0.0   # km/h
        self.steps    = 0
        self.distance = 0.0   # km
        self.elapsed  = 0     # seconds
        self.state    = 0
        self.raw      = None

    @property
    def state_label(self):
        return STATE_LABELS.get(self.state, f"state={self.state}")

    @property
    def time_str(self):
        m, s = divmod(self.elapsed, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


def _parse_notification(data: bytes, status: PadStatus):
    """Parse a WalkingPad BLE notification packet into status."""
    if len(data) < 14 or data[0] != 0xf8 or data[1] != 0xa2:
        return
    status.state    = data[2]
    status.speed    = data[3] / 10.0
    status.elapsed  = (data[5] << 16) | (data[6] << 8) | data[7]
    status.distance = ((data[8] << 16) | (data[9] << 8) | data[10]) / 100.0
    status.steps    = (data[11] << 16) | (data[12] << 8) | data[13]
    status.raw      = data


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------
class WalkingPadAction(Action):

    @property
    def title(self):
        return "Walking Pad"

    # ------------------------------------------------------------------
    # Synchronous entry-point called by the menu
    # ------------------------------------------------------------------
    def execute(self, lcd):
        try:
            import bleak  # noqa: F401
        except ImportError:
            self._show_message(lcd, "bleak not installed", "Run:", "pip install bleak")
            self.wait_for_key3(lcd)
            return

        asyncio.run(self._async_main(lcd))

    # ------------------------------------------------------------------
    # Async main — scan → connect → display loop
    # ------------------------------------------------------------------
    async def _async_main(self, lcd):
        from bleak import BleakScanner, BleakClient

        # --- 1. Scan ---------------------------------------------------
        self._show_message(lcd, "Scanning BLE...", "", "")

        devices = await BleakScanner.discover(timeout=5.0)

        # --- 2. Find walking pad by name hint ---------------------------
        pad_device = None
        for d in devices:
            if d.name and any(h in d.name.lower() for h in PAD_NAME_HINTS):
                pad_device = d
                break

        if pad_device is None:
            self._show_message(lcd, "WalkingPad", "not found", "KEY3: back")
            self.wait_for_key3(lcd)
            return

        self._show_message(lcd, "Connecting...", pad_device.name or "", pad_device.address)

        # --- 3. Connect and stream data ---------------------------------
        status = PadStatus()

        def _on_notify(_sender, data: bytes):
            _parse_notification(data, status)

        try:
            async with BleakClient(pad_device.address) as client:
                await client.start_notify(NOTIFY_UUID, _on_notify)
                await client.write_gatt_char(WRITE_UUID, CMD_STATUS, response=False)

                image = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
                draw  = ImageDraw.Draw(image)

                exit_event = asyncio.Event()

                async def _watch_keys():
                    """Poll all keys every 50 ms."""
                    prev_k1 = prev_up = prev_dn = prev_k3 = 0
                    while not exit_event.is_set():
                        k1 = lcd.digital_read(lcd.GPIO_KEY1_PIN)
                        up = lcd.digital_read(lcd.GPIO_KEY_UP_PIN)
                        dn = lcd.digital_read(lcd.GPIO_KEY_DOWN_PIN)
                        k3 = lcd.digital_read(lcd.GPIO_KEY3_PIN)

                        if k1 == 1 and prev_k1 == 0:
                            if status.state == 1:  # running → stop
                                try:
                                    await client.write_gatt_char(WRITE_UUID, CMD_STOP, response=False)
                                except Exception:
                                    pass
                            else:  # stopped → start
                                try:
                                    await client.write_gatt_char(WRITE_UUID, CMD_START, response=False)
                                except Exception:
                                    pass

                        if up == 1 and prev_up == 0 and status.state == 1:
                            new_speed = min(SPEED_MAX, round(status.speed + 0.5, 1))
                            try:
                                await client.write_gatt_char(WRITE_UUID, _make_speed_cmd(new_speed), response=False)
                            except Exception:
                                pass

                        if dn == 1 and prev_dn == 0 and status.state == 1:
                            new_speed = max(SPEED_MIN, round(status.speed - 0.5, 1))
                            try:
                                await client.write_gatt_char(WRITE_UUID, _make_speed_cmd(new_speed), response=False)
                            except Exception:
                                pass

                        if k3 == 1 and prev_k3 == 0:
                            self._show_message(lcd, "Exiting...", "", "")
                            exit_event.set()
                            return

                        prev_k1, prev_up, prev_dn, prev_k3 = k1, up, dn, k3
                        await asyncio.sleep(0.05)

                key_task = asyncio.create_task(_watch_keys())

                while not exit_event.is_set():
                    try:
                        await client.write_gatt_char(WRITE_UUID, CMD_STATUS, response=False)
                    except Exception:
                        pass

                    if status.raw is None:
                        self._show_waiting(lcd, pad_device.name or "WalkingPad")
                    else:
                        self._draw_status(lcd, draw, image, status, pad_device.name or "WalkingPad")

                    try:
                        await asyncio.wait_for(exit_event.wait(), timeout=0.8)
                    except asyncio.TimeoutError:
                        pass

                key_task.cancel()
                await client.stop_notify(NOTIFY_UUID)

        except Exception as exc:
            self._show_message(lcd, "BLE Error", str(exc)[:20], "KEY3: back")
            self.wait_for_key3(lcd)

    # ------------------------------------------------------------------
    # LCD rendering helpers
    # ------------------------------------------------------------------
    def _draw_status(self, lcd, draw, image, status: PadStatus, device_name: str):
        W, H = lcd.width, lcd.height

        draw.rectangle((0, 0, W, H), fill="#000000")

        # Title bar
        draw.rectangle((0, 0, W, 15), fill="#1a5276")
        draw.text((4, 2), "Walking Pad", font=FONT_TITLE, fill="WHITE")

        # State badge (top-right)
        state_color = "#27ae60" if status.state == 1 else "#7f8c8d"
        draw.text((W - 42, 2), status.state_label, font=FONT_SMALL, fill=state_color)

        # Data rows
        rows = [
            ("Speed",  f"{status.speed:.1f} km/h", "#f39c12"),
            ("Steps",  f"{status.steps}",           "#2980b9"),
            ("Dist",   f"{status.distance:.2f} km", "#27ae60"),
            ("Time",   status.time_str,              "#8e44ad"),
        ]

        y = 20
        row_h = 24
        for label, value, color in rows:
            draw.text((6,  y),      label + ":", font=FONT_LABEL, fill="#aaaaaa")
            draw.text((52, y - 1),  value,       font=FONT_VALUE, fill=color)
            y += row_h

        # Device name (small, near bottom)
        draw.text((4, H - 22), device_name[:20], font=FONT_SMALL, fill="#555555")

        # Footer — show controls
        draw.rectangle((0, H - 12, W, H), fill="#1a5276")
        draw.text((4, H - 11), "K1:\u25ae/\u25b6  \u25b2\u25bc:spd  K3:back", font=FONT_SMALL, fill="WHITE")

        lcd.LCD_ShowImage(image, 0, 0)

    def _show_message(self, lcd, line1: str, line2: str, line3: str = ""):
        W, H = lcd.width, lcd.height
        image = Image.new("RGB", (W, H), "BLACK")
        draw  = ImageDraw.Draw(image)

        draw.rectangle((0, 0, W, 15), fill="#1a5276")
        draw.text((4, 2), "Walking Pad", font=FONT_TITLE, fill="WHITE")

        draw.text((4, 24), line1, font=FONT_LABEL, fill="WHITE")
        draw.text((4, 42), line2, font=FONT_LABEL, fill="#aaaaaa")
        draw.text((4, 58), line3, font=FONT_SMALL,  fill="#aaaaaa")

        draw.rectangle((0, H - 12, W, H), fill="#1a5276")
        draw.text((4, H - 11), "KEY3: back", font=FONT_SMALL, fill="WHITE")

        lcd.LCD_ShowImage(image, 0, 0)

    def _show_waiting(self, lcd, device_name: str):
        W, H = lcd.width, lcd.height
        image = Image.new("RGB", (W, H), "BLACK")
        draw  = ImageDraw.Draw(image)

        draw.rectangle((0, 0, W, 15), fill="#1a5276")
        draw.text((4, 2), "Walking Pad", font=FONT_TITLE, fill="WHITE")

        draw.text((4, 24), "Connected", font=FONT_LABEL, fill="#27ae60")
        draw.text((4, 40), device_name[:20], font=FONT_SMALL, fill="#aaaaaa")
        draw.text((4, 58), "Start belt to", font=FONT_LABEL, fill="#f39c12")
        draw.text((4, 74), "see data...", font=FONT_LABEL, fill="#f39c12")

        draw.rectangle((0, H - 12, W, H), fill="#1a5276")
        draw.text((4, H - 11), "KEY3: back", font=FONT_SMALL, fill="WHITE")

        lcd.LCD_ShowImage(image, 0, 0)


action = WalkingPadAction()

if __name__ == "__main__":
    action.run_standalone()
