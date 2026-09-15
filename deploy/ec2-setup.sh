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

echo "EC2 setup complete."
