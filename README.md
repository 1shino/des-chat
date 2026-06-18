# 基于DES加密的TCP聊天程序（Telegram风格）

信息安全实践课程设计 — 选题一

## 功能特性

- **用户注册/登录** — 账号密码SHA256哈希存储
- **大厅聊天** — 所有在线用户可见的公共频道
- **私聊** — 端到端加密，服务端无法解密
- **群组聊天** — 创建群（公开/私有）、邀请好友、群内E2E加密
- **好友系统** — 发送/接受/拒绝好友请求，在线状态显示
- **聊天记录** — 自动持久化存储，随时查看历史
- **DES加密** — 全程DES加密传输
- **Web前端** — Telegram风格网页界面，弹窗通知

## 环境要求

- Python 3.10+

## 安装依赖

```bash
pip install pycryptodome flask flask-socketio
```

## 运行方式

### Web版（推荐）

```bash
python app.py
```

浏览器打开 http://localhost:5000

### 公网部署

详见 [DEPLOY.md](DEPLOY.md) — 包含云服务器、宝塔面板、Docker三种部署方式。

### TCP命令行版

```bash
python server.py    # 终端1
python client.py    # 终端2/3
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `crypto_utils.py` | DES加解密 + 密钥生成 + 共享密钥派生 |
| `app.py` | Web版服务端（Flask + SocketIO） |
| `templates/index.html` | Telegram风格Web前端（HTML + CSS + JS） |
| `protocol.py` | TCP版消息协议（JSON + DES） |
| `server.py` | TCP版多线程服务端 |
| `client.py` | TCP版命令行客户端 |
| `data/users.json` | 用户账号数据 |
| `data/groups.json` | 群组数据 |
| `data/history/` | 聊天记录 |

## 代码分析

### 加密架构

本系统采用**两层加密**设计：

| 层级 | 适用场景 | 密钥来源 | 服务端能否解密 |
|------|---------|---------|--------------|
| 传输加密 | 大厅聊天 | 硬编码 `DES_KEY` | ✅ 能 |
| 端到端加密 | 私聊/群聊 | 用户密钥动态派生 | ❌ 不能 |

### 密钥管理

```
注册 → 服务端生成随机8字节DES密钥 → 存入users.json → 登录时返回客户端
                ↓
私聊 → 双方密钥按字典序拼接 → SHA256 → 取前8字节 = 共享密钥
群聊 → SHA256(群主密钥 + 群uid) → 取前8字节 = 群共享密钥
```

**共享密钥派生算法（crypto_utils.py）：**
```python
def derive_shared_key(key_a: bytes, key_b: bytes) -> bytes:
    if key_a <= key_b:    # 固定顺序，保证双方算出相同结果
        combined = key_a + key_b
    else:
        combined = key_b + key_a
    return hashlib.sha256(combined).digest()[:8]
```

**浏览器端对应实现（index.html）：**
```javascript
function deriveSharedKey(keyA, keyB) {
  const [first, second] = keyA < keyB ? [keyA, keyB] : [keyB, keyA];
  const combined = CryptoJS.enc.Hex.parse(first + second);
  return CryptoJS.SHA256(combined).toString(CryptoJS.enc.Hex).substring(0, 16);
}
```

### 端到端加密流程

```
发送方                          服务端                     接收方
  │                              │                          │
  │ 1.派生共享密钥                │                          │
  │ 2.DES加密消息                 │                          │
  │ 3.发送密文 ──────────────────>│ 4.转发密文 ──────────────>│
  │                              │   (无法解密)              │ 5.派生共享密钥
  │                              │                          │ 6.DES解密消息
  │                              │                          │ 7.显示明文
```

### 密钥缓存机制

客户端按需请求用户密钥，首次请求后缓存复用：

```
收到消息 → 查缓存 → 有密钥 → 直接解密
                  → 无密钥 → 请求密钥 + 消息暂存pendingDecrypts
                                              ↓
                         收到user_key事件 → 缓存 → 解密所有等待该密钥的消息
```

### 通信协议

**Web版（Socket.IO）：**
- 传输层：WebSocket（基于TCP）
- 消息格式：JSON
- 加密层：DES-ECB + PKCS7填充

**TCP版（原始socket）：**
- 传输层：TCP socket
- 消息格式：`[4字节长度][DES加密的JSON]`

### DES参数

| 项目 | 值 |
|------|-----|
| 算法 | DES |
| 模式 | ECB |
| 填充 | PKCS5/PKCS7 |
| 分组大小 | 8字节 |
| 密钥长度 | 8字节（64位，有效56位） |

### 安全性分析

**能防御：**
- 网络窃听（密文传输）
- 服务端泄露（E2E消息服务端无明文）
- 单密钥泄露（每用户独立密钥）

**局限性：**
- DES密钥仅56位有效长度，不适合生产环境
- 无消息完整性校验（ECB模式）
- 无密钥认证机制（无中间人防护）

### 页面交互

- 登录/注册弹窗
- 左侧栏：聊天列表 + 好友标签页（切换）
- 右侧区：消息气泡 + DES密文展示（🔒标识）
- 弹窗通知：右上角滑入提示条（好友请求/群邀请/私聊/系统消息）
- 刷新按钮：同步最新数据 + 重新加载历史

## 命令参考

| 操作 | 说明 |
|------|------|
| 直接输入 | 大厅广播 |
| 点击在线用户 | 发起私聊 |
| 👤 按钮 | 添加好友 |
| ➕ 按钮 | 创建群组 |
| 🔗 按钮 | 加入公开群组 |
| 📨 按钮 | 邀请好友入群（群聊内） |
| 🔄 按钮 | 刷新数据 |
| /quit | 退出（TCP版） |
