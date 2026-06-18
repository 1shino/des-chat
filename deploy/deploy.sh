#!/bin/bash
# DES加密聊天 — 一键部署脚本
# 适用于 Ubuntu/Debian 系统（腾讯云轻量推荐 Ubuntu 22.04）
# 用法：sudo bash deploy.sh your-domain.com

set -e

DOMAIN=${1:-""}
CHAT_DIR="/opt/chat"

echo "=========================================="
echo "  DES加密聊天 — 服务器部署脚本"
echo "=========================================="

# 1. 安装系统依赖
echo "[1/6] 安装系统依赖..."
apt update -y
apt install -y python3 python3-pip nginx certbot python3-certbot-nginx

# 2. 创建项目目录
echo "[2/6] 部署项目文件..."
mkdir -p $CHAT_DIR/data/history

# 复制项目文件（假设脚本和项目文件在同一目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/../app.py" $CHAT_DIR/
cp "$SCRIPT_DIR/../crypto_utils.py" $CHAT_DIR/
cp "$SCRIPT_DIR/../protocol.py" $CHAT_DIR/
cp -r "$SCRIPT_DIR/../templates" $CHAT_DIR/
cp -r "$SCRIPT_DIR/../data" $CHAT_DIR/ 2>/dev/null || true

# 3. 安装 Python 依赖
echo "[3/6] 安装 Python 依赖..."
pip3 install pycryptodome flask flask-socketio

# 4. 修改 app.py 为生产模式
echo "[4/6] 配置生产模式..."
sed -i 's/debug=True/debug=False/' $CHAT_DIR/app.py
sed -i 's/host="127.0.0.1"/host="0.0.0.0"/' $CHAT_DIR/app.py
sed -i "s|http://localhost:5000|http://0.0.0.0:5000|" $CHAT_DIR/app.py

# 5. 配置 systemd 服务
echo "[5/6] 配置系统服务..."
cp "$SCRIPT_DIR/chat.service" /etc/systemd/system/
systemctl daemon-reload
systemctl start chat
systemctl enable chat

# 6. 配置 Nginx
echo "[6/6] 配置 Nginx..."
if [ -n "$DOMAIN" ]; then
    sed "s/YOUR_DOMAIN/$DOMAIN/g" "$SCRIPT_DIR/chat.nginx.conf" > /etc/nginx/conf.d/chat.conf
else
    echo "  [!] 未指定域名，使用默认配置（后续需手动修改）"
    cp "$SCRIPT_DIR/chat.nginx.conf" /etc/nginx/conf.d/chat.conf
fi

nginx -t && systemctl restart nginx

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "  服务状态："
systemctl status chat --no-pager -l | head -5
echo ""

if [ -n "$DOMAIN" ]; then
    echo "  访问地址：http://$DOMAIN"
    echo ""
    echo "  申请 HTTPS 证书（推荐）："
    echo "    certbot --nginx -d $DOMAIN"
else
    echo "  访问地址：http://你的服务器IP"
    echo ""
    echo "  后续步骤："
    echo "  1. 域名 DNS 解析到此服务器 IP"
    echo "  2. 修改 /etc/nginx/conf.d/chat.conf 中的 YOUR_DOMAIN"
    echo "  3. 运行: certbot --nginx -d 你的域名"
fi

echo ""
echo "  常用命令："
echo "    systemctl status chat    # 查看服务状态"
echo "    systemctl restart chat   # 重启服务"
echo "    journalctl -u chat -f    # 查看实时日志"
echo ""
