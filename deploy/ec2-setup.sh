#!/bin/bash
# Run once on a fresh EC2 instance (Amazon Linux 2023) to install dependencies.
set -e

echo "Installing system packages..."
sudo dnf update -y
sudo dnf install -y python3.12 python3.12-pip git

echo "Installing Chromium system dependencies..."
sudo dnf install -y nss atk at-spi2-atk cups-libs libdrm libXcomposite \
  libXdamage libXrandr mesa-libgbm pango alsa-lib libXtst libxkbcommon

echo "Installing Python dependencies..."
pip3.12 install playwright boto3

echo "Installing Chromium for Playwright..."
# AL2023 isn't officially supported — install without --with-deps (which needs apt-get)
python3.12 -m playwright install chromium

echo "Creating app directory..."
sudo mkdir -p /opt/resy-bot
sudo chown ec2-user:ec2-user /opt/resy-bot

echo "Installing systemd service..."
sudo tee /etc/systemd/system/resy-bot.service > /dev/null << 'SVC'
[Unit]
Description=Resy Bot Snipe Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/resy-bot
ExecStart=/usr/bin/python3.12 /opt/resy-bot/snipe_runner.py
Environment=PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
TimeoutStartSec=600
StandardOutput=append:/var/log/resy-bot/snipe_runner.log
StandardError=append:/var/log/resy-bot/snipe_runner.log

[Install]
WantedBy=multi-user.target
SVC
sudo mkdir -p /var/log/resy-bot
sudo systemctl daemon-reload
sudo systemctl enable resy-bot.service

echo "Installing CloudWatch agent..."
sudo dnf install -y amazon-cloudwatch-agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCFG'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/resy-bot/snipe_runner.log",
            "log_group_name": "/resy-bot/snipe-runner",
            "log_stream_name": "{instance_id}",
            "retention_in_days": 14
          }
        ]
      }
    }
  }
}
CWCFG
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
sudo systemctl enable amazon-cloudwatch-agent

echo "EC2 setup complete."
