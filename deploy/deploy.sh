#!/usr/bin/env bash
# @file deploy.sh
# @brief Linux Storage Manager 服务器部署脚本
#
# 在目标服务器上执行，自动创建虚拟环境、安装依赖、注册 systemd 服务并启动。
#
# @author 李泽源、谢子墨
# @date 2026
# @copyright MIT License
# @note 武汉大学开源软件与技术课程 2026

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/storage-manager}"
PORT="${PORT:-8010}"

cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

sed "s/--port 8010/--port ${PORT}/" deploy/storage-manager.service > /etc/systemd/system/storage-manager.service
systemctl daemon-reload
systemctl enable --now storage-manager
systemctl restart storage-manager
systemctl --no-pager --full status storage-manager
