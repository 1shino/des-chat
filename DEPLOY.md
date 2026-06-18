# DES加密聊天 — 公网部署指南

## 方案一：云服务器部署（推荐）

### 1. 购买云服务器

| 平台 | 学生价 | 推荐配置 |
|------|--------|---------|
| 阿里云 | ~10元/月 | 1核2G CentOS/Ubuntu |
| 腾讯云 | ~10元/月 | 1核2G CentOS/Ubuntu |
| 华为云 | ~10元/月 | 1核2G CentOS/Ubuntu |

### 2. 上传代码

```bash
# 本地打包
cd D:\telegram
tar -czf chat.tar.gz *.py templates/ data/

# 上传到服务器（替换为你的服务器IP）
scp chat.tar.gz root@你的服务器IP:/opt/chat/
```

### 3. 服务器环境配置

```bash
# SSH登录服务器
ssh root@你的服务器IP

# 安装Python3
yum install -y python3 python3-pip   # CentOS
# 或
apt install -y python3 python3-pip   # Ubuntu

# 解压代码
cd /opt/chat
tar -xzf chat.tar.gz

# 安装依赖
pip3 install pycryptodome flask flask-socketio gunicorn eventlet
```

### 4. 修改启动配置

编辑 `app.py` 最后一行，改为：

```python
if __name__ == "__main__":
    os.makedirs(HISTORY_DIR, exist_ok=True)
    load_users()
    load_groups()
    print(f"[*] Web服务启动: http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)  # 关闭debug
```

### 5. 启动服务

```bash
# 直接启动（测试用）
python3 app.py

# 后台运行（生产用）
nohup python3 app.py > /opt/chat/log.txt 2>&1 &

# 或用gunicorn（更稳定）
gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 app:app --daemon
```

### 6. 配置Nginx反向代理 + HTTPS

```bash
# 安装nginx
yum install -y nginx   # CentOS
# 或
apt install -y nginx   # Ubuntu
```

编辑 `/etc/nginx/conf.d/chat.conf`：

```nginx
server {
    listen 80;
    server_name 你的域名.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# 测试并重启nginx
nginx -t
systemctl restart nginx
systemctl enable nginx
```

### 7. 域名解析

在你的域名注册商（阿里云/腾讯云/Cloudflare）添加DNS记录：

| 类型 | 主机记录 | 记录值 |
|------|---------|--------|
| A | @ | 你的服务器IP |
| A | www | 你的服务器IP |

### 8. 申请HTTPS证书（免费）

```bash
# 安装certbot
yum install -y certbot python3-certbot-nginx   # CentOS
# 或
apt install -y certbot python3-certbot-nginx   # Ubuntu

# 自动申请并配置
certbot --nginx -d 你的域名.com -d www.你的域名.com

# 自动续期（certbot会自动设置）
certbot renew --dry-run
```

完成后访问：`https://你的域名.com`

---

## 方案二：宝塔面板部署（更简单）

适合不熟悉命令行的用户。

### 1. 安装宝塔面板

```bash
# CentOS
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh

# Ubuntu
wget -O install.sh https://download.bt.cn/install/install-ubuntu_6.0.sh && sudo bash install.sh
```

### 2. 宝塔面板操作

1. 浏览器访问 `http://你的服务器IP:8888`
2. 安装：Nginx、Python项目管理器
3. 上传代码到 `/www/wwwroot/chat/`
4. Python项目管理器 → 添加项目：
   - 项目路径：`/www/wwwroot/chat`
   - 启动文件：`app.py`
   - 端口：5000
   - 启动方式：`flask-socketio`
5. 域名管理 → 绑定你的域名
6. SSL → 申请免费证书

---

## 方案三：Docker部署

### 1. 创建 Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir pycryptodome flask flask-socketio gunicorn eventlet
EXPOSE 5000
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]
```

### 2. 构建并运行

```bash
docker build -t des-chat .
docker run -d -p 5000:5000 -v /opt/chat/data:/app/data --name chat des-chat
```

### 3. Nginx配置同方案一

---

## 常见问题

### 防火墙放行端口

```bash
# CentOS 7+
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --reload

# Ubuntu
ufw allow 80
ufw allow 443

# 云服务器还需要在控制台安全组放行80和443端口
```

### 服务崩溃自动重启

创建 `/etc/systemd/system/chat.service`：

```ini
[Unit]
Description=DES Chat Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/chat
ExecStart=/usr/bin/python3 /opt/chat/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl start chat
systemctl enable chat
systemctl status chat   # 查看状态
journalctl -u chat -f   # 查看日志
```

### 数据备份

```bash
# 定期备份用户数据和聊天记录
tar -czf /backup/chat_$(date +%Y%m%d).tar.gz /opt/chat/data/
```

---

## 部署检查清单

- [ ] 服务器购买并配置好
- [ ] 域名DNS解析到服务器IP
- [ ] 代码上传到服务器
- [ ] Python依赖安装完成
- [ ] `app.py` 中 `debug=False`
- [ ] Nginx配置并启动
- [ ] 防火墙/安全组放行80、443端口
- [ ] HTTPS证书申请完成
- [ ] 服务设置开机自启
- [ ] 测试公网访问正常
