#!/usr/bin/env bash
# @file deploy-v2.sh
# @brief Linux Storage Manager 升级部署脚本
#
# 用于在服务器上执行带备份的增量升级：
# 1. 备份现有代码
# 2. 备份审计日志数据
# 3. 解压新代码（排除 data 目录，避免覆盖数据）
# 4. 恢复审计日志数据
# 5. 安装依赖、语法检查、重启服务
#
# @author 李泽源、谢子墨
# @date 2026
# @copyright MIT License
# @note 武汉大学开源软件与技术课程 2026

set -euo pipefail

APP_DIR="/opt/storage-manager"
PORT="8010"
TAR_FILE="/tmp/storage-manager-v2.tar.gz"

echo "=== 1. 备份现有代码 ==="
BACKUP_DIR="/opt/storage-manager.bak.$(date +%Y%m%d_%H%M%S)"
cp -r "$APP_DIR" "$BACKUP_DIR"
echo "备份完成: $BACKUP_DIR"

echo "=== 2. 保留数据目录和审计日志 ==="
mkdir -p /tmp/storage-manager-data-backup
if [ -d "$APP_DIR/data" ]; then
    cp -r "$APP_DIR/data" /tmp/storage-manager-data-backup/
    echo "审计日志已备份到 /tmp/storage-manager-data-backup/data/"
fi

echo "=== 3. 解压新代码 ==="
cd "$APP_DIR"
tar -xzf "$TAR_FILE" --exclude='data' -C "$APP_DIR"

echo "=== 4. 恢复数据目录 ==="
if [ -d "/tmp/storage-manager-data-backup/data" ]; then
    cp -r /tmp/storage-manager-data-backup/data/* "$APP_DIR/data/" 2>/dev/null || true
    echo "审计日志已恢复"
fi

echo "=== 5. 安装新依赖 ==="
cd "$APP_DIR"
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== 6. 语法检查 ==="
python3 -m compileall app src tests

echo "=== 7. 重启服务 ==="
systemctl daemon-reload
systemctl restart storage-manager
sleep 2

echo "=== 8. 验证状态 ==="
systemctl --no-pager --full status storage-manager

echo "=== 9. 端口检查 ==="
ss -tlnp | grep ':8010' || echo "警告：8010 端口未监听"

echo "=== 10. Nginx 配置检查 ==="
nginx -t

echo ""
echo "部署完成！"
echo "备份目录: $BACKUP_DIR"
echo "访问地址: https://112.124.15.21/storage-manager/"
