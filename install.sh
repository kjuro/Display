#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

cat > /tmp/lcd-boot.service <<EOF
[Unit]
Description=LCD menu at boot
After=multi-user.target

[Service]
ExecStart=${DIR}/main.py
WorkingDirectory=${DIR}
User=juro
Type=simple
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat > /tmp/lcd-shutdown.service <<EOF
[Unit]
Description=Show image on LCD before shutdown
DefaultDependencies=no
Before=shutdown.target

[Service]
ExecStart=${DIR}/show_image.py time.bmp
WorkingDirectory=${DIR}
User=juro
Type=oneshot

[Install]
WantedBy=shutdown.target
EOF

sudo mv /tmp/lcd-boot.service /etc/systemd/system/
sudo mv /tmp/lcd-shutdown.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lcd-boot.service
sudo systemctl enable lcd-shutdown.service

echo "Services installed and enabled."
echo "  Boot:     lcd-boot.service (main.py)"
echo "  Shutdown: lcd-shutdown.service (time.bmp)"
