# Display

Scripts for controlling a 1.44" LCD on Raspberry Pi Zero.

## Scripts

- **on.py** — Turn on LCD backlight
- **off.py** — Turn off LCD backlight
- **show-image.py** — Show an image on the LCD (defaults to `sky.bmp`)
- **main.py** — Demo: draws shapes, text, and cycles through images
- **black.py** — Fill display with black
- **install.sh** — Install systemd services for boot/shutdown images

## Usage

```bash
./on.py
./show-image.py                    # shows images/sky.bmp
./show-image.py images/time.bmp    # shows images/time.bmp
./off.py
```

## Auto-start on boot / shutdown

Run the install script to set up systemd services that show `sky.bmp` on boot and `time.bmp` before shutdown:

```bash
./install.sh
```

This creates and enables two services:
- **lcd-boot.service** — shows `sky.bmp` at startup
- **lcd-shutdown.service** — shows `time.bmp` before shutdown

To check status:

```bash
sudo systemctl status lcd-boot.service
sudo systemctl status lcd-shutdown.service
```

To disable:

```bash
sudo systemctl disable lcd-boot.service
sudo systemctl disable lcd-shutdown.service
```

## Setup

```bash
python3 -m venv ~/.venv
source ~/.venv/bin/activate
pip install RPi.GPIO Pillow
```
