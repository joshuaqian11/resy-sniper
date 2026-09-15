#!/bin/bash
# EC2 User Data — runs on every instance start.
# Pulls latest code from S3 and runs the snipe.
set -e

exec > /var/log/resy-bot.log 2>&1
echo "$(date) — Resy bot starting"

APP_DIR="/opt/resy-bot"
cd "$APP_DIR"

# Run the snipe
python3.12 snipe_runner.py

echo "$(date) — Snipe runner finished, instance will stop"
# Instance stops itself from within snipe_runner.py
