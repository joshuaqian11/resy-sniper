#!/bin/bash
set -e

# Run as root on a fresh Amazon Linux 2023 t3.nano

# System packages
dnf update -y
dnf install -y python3.12 python3.12-pip git nginx certbot python3-certbot-nginx nodejs npm

# App directory
mkdir -p /opt/resy-bot
chown -R ec2-user:ec2-user /opt/resy-bot

# Clone repo (update URL)
if [ -d /opt/resy-bot/.git ]; then
  git -C /opt/resy-bot pull
else
  git clone https://github.com/YOUR_USERNAME/resy-bot.git /opt/resy-bot
fi
chown -R ec2-user:ec2-user /opt/resy-bot

# Backend
cd /opt/resy-bot/backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Frontend build
cd /opt/resy-bot/frontend
npm ci
npm run build

# Env file (edit after running)
[ -f /opt/resy-bot/.env ] || cp /opt/resy-bot/backend/.env.example /opt/resy-bot/.env
echo ">>> Edit /opt/resy-bot/.env before starting the service <<<"

# systemd
cp /opt/resy-bot/deploy/resy-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable resy-bot

# Nginx
cp /opt/resy-bot/deploy/nginx.conf /etc/nginx/conf.d/resy-bot.conf
systemctl enable nginx

echo ">>> Run: certbot --nginx -d YOUR_DOMAIN <<<"
echo ">>> Then: systemctl start resy-bot nginx <<<"
