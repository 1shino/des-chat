"""DES加密TCP聊天 — Web前端（Flask + SocketIO）
支持：用户注册登录、大厅聊天、私聊、好友系统、群组（公开/私有+邀请）
"""

import hashlib
import json
import os
import uuid
from datetime import datetime

from flask import Flask, render_template
from flask_socketio import SocketIO, emit

from crypto_utils import encrypt, decrypt, generate_key

app = Flask(__name__)
app.config["SECRET_KEY"] = "des-chat-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

DES_KEY = b"8bytekey"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")

# 运行时状态
# users_db: {username: {password, friends: [], friend_requests: {from: [], to: []}}}
users_db: dict[str, dict] = {}
# groups_db: {uid: {name, members: [], creator, public: bool, invites: []}}
groups_db: dict[str, dict] = {}
online_users: dict[str, str] = {}  # {username: sid}


# ============================================================
#  数据持久化
# ============================================================

def load_users():
    global users_db
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users_db = json.load(f)
    # 兼容旧格式 + 补充缺失字段
    for u, v in list(users_db.items()):
        if isinstance(v, str):
            users_db[u] = {
                "password": v,
                "friends": [],
                "friend_requests": {"from": [], "to": []},
            }
        if "key" not in users_db[u]:
            users_db[u]["key"] = generate_key().hex()
    save_users()


def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)


def load_groups():
    global groups_db
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            groups_db = json.load(f)


def save_groups():
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups_db, f, ensure_ascii=False, indent=2)


def save_history(category: str, record: dict):
    path = os.path.join(HISTORY_DIR, f"{category}.json")
    records = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
    records.append(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def load_history(category: str) -> list[dict]:
    path = os.path.join(HISTORY_DIR, f"{category}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ============================================================
#  工具函数
# ============================================================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def request_sid() -> str:
    from flask import request
    return request.sid


def find_user_by_sid(sid: str) -> str | None:
    for u, s in online_users.items():
        if s == sid:
            return u
    return None


def emit_to_user(username: str, event: str, data: dict):
    """向指定在线用户发送消息"""
    sid = online_users.get(username)
    if sid:
        emit(event, data, to=sid)


def serialize_groups() -> dict:
    """序列化群组信息（set->list），key为uid"""
    return {
        uid: {
            "name": v["name"],
            "members": list(v["members"]),
            "creator": v["creator"],
            "public": v["public"],
            "invites": v.get("invites", []),
        }
        for uid, v in groups_db.items()
    }


def get_user_friends(username: str) -> list[str]:
    return users_db.get(username, {}).get("friends", [])


def get_user_friend_requests(username: str) -> dict:
    return users_db.get(username, {}).get("friend_requests", {"from": [], "to": []})


# ============================================================
#  路由
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
#  SocketIO 事件
# ============================================================

@socketio.on("connect")
def on_connect():
    print(f"[连接] {request_sid()}")


@socketio.on("disconnect")
def on_disconnect():
    sid = request_sid()
    username = find_user_by_sid(sid)
    if username:
        online_users.pop(username, None)
        save_history("_lobby", {"from": "系统", "text": f"{username} 下线了", "time": now_str()})
        emit("system", {"text": f"{username} 下线了", "time": now_str()}, broadcast=True)
        emit("user_list", {"users": list(online_users.keys())}, broadcast=True)
        print(f"[离线] {username}")


# ---------- 注册/登录 ----------

@socketio.on("register")
def on_register(data):
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        emit("error", {"text": "用户名和密码不能为空"})
        return
    if username in users_db:
        emit("error", {"text": "用户名已存在"})
        return
    user_key = generate_key().hex()  # 每个用户独有的DES密钥
    users_db[username] = {
        "password": hash_password(password),
        "key": user_key,
        "friends": [],
        "friend_requests": {"from": [], "to": []},
    }
    save_users()
    emit("system", {"text": "注册成功，请登录", "time": now_str()})
    print(f"[注册] {username} key={user_key[:8]}...")


@socketio.on("login")
def on_login(data):
    sid = request_sid()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if username not in users_db or users_db[username]["password"] != hash_password(password):
        emit("error", {"text": "用户名或密码错误"})
        return
    if username in online_users:
        emit("error", {"text": "该账号已在其他地方登录"})
        return
    online_users[username] = sid
    user_key = users_db[username].get("key", generate_key().hex())
    emit("login_ok", {"username": username, "key": user_key, "time": now_str()})
    save_history("_lobby", {"from": "系统", "text": f"{username} 上线了", "time": now_str()})
    emit("system", {"text": f"{username} 上线了", "time": now_str()}, broadcast=True)
    emit("user_list", {"users": list(online_users.keys())}, broadcast=True)
    emit("group_list", {"groups": serialize_groups()})
    # 发送好友信息
    emit("friend_data", {
        "friends": get_user_friends(username),
        "requests": get_user_friend_requests(username),
    })
    print(f"[登录] {username}")


# ---------- 大厅聊天 ----------

@socketio.on("chat")
def on_chat(data):
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    text = data.get("text", "").strip()
    if not text:
        return
    ts = now_str()
    # 大厅消息用传输密钥DES加密（非E2E，服务端可解密）
    encrypted = encrypt(text, DES_KEY).hex()
    save_history("_lobby", {"from": username, "text": text, "time": ts, "encrypted": encrypted})
    emit("chat", {"from": username, "text": text, "time": ts, "encrypted": encrypted}, broadcast=True)
    print(f"[大厅] {username}: {text}")


# ---------- 私聊（E2E：客户端加密，服务端只转发密文） ----------

@socketio.on("private")
def on_private(data):
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    target = data.get("to", "").strip()
    encrypted = data.get("encrypted", "").strip()  # 客户端已用共享密钥加密
    if not target or not encrypted:
        return
    if target not in online_users:
        emit("error", {"text": f"用户 {target} 不在线"})
        return
    ts = now_str()
    key = f"priv_{min(username, target)}_{max(username, target)}"
    save_history(key, {"from": username, "to": target, "encrypted": encrypted, "time": ts})
    # 服务端只转发密文，无法解密
    emit_to_user(target, "private", {"from": username, "encrypted": encrypted, "time": ts})
    emit("private_echo", {"to": target, "encrypted": encrypted, "time": ts})
    print(f"[私聊] {username} -> {target}: [E2E加密]")


# ---------- 好友系统 ----------

@socketio.on("friend_request")
def on_friend_request(data):
    """发送好友请求"""
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    target = data.get("to", "").strip()
    if not target:
        emit("error", {"text": "请输入用户名"})
        return
    if target == username:
        emit("error", {"text": "不能添加自己为好友"})
        return
    if target not in users_db:
        emit("error", {"text": f"用户 {target} 不存在"})
        return
    if target in get_user_friends(username):
        emit("error", {"text": f"{target} 已经是你的好友"})
        return
    reqs = get_user_friend_requests(username)
    if target in reqs.get("to", []):
        emit("error", {"text": f"已向 {target} 发送过请求"})
        return
    # 如果对方已经向你发过请求，直接接受
    if target in reqs.get("from", []):
        _do_accept_friend(username, target)
        return
    # 发送请求
    users_db[username]["friend_requests"]["to"].append(target)
    users_db[target]["friend_requests"]["from"].append(username)
    save_users()
    emit("system", {"text": f"已向 {target} 发送好友请求", "time": now_str()})
    emit_to_user(target, "friend_data", {
        "friends": get_user_friends(target),
        "requests": get_user_friend_requests(target),
    })
    emit("friend_data", {
        "friends": get_user_friends(username),
        "requests": get_user_friend_requests(username),
    })
    print(f"[好友请求] {username} -> {target}")


@socketio.on("friend_accept")
def on_friend_accept(data):
    """接受好友请求"""
    username = find_user_by_sid(request_sid())
    if not username:
        return
    target = data.get("from", "").strip()
    _do_accept_friend(username, target)


def _do_accept_friend(user_a: str, user_b: str):
    """双向添加好友"""
    if user_b not in users_db[user_a]["friend_requests"].get("from", []):
        return
    # 从请求列表移除
    users_db[user_a]["friend_requests"]["from"] = [
        x for x in users_db[user_a]["friend_requests"]["from"] if x != user_b
    ]
    users_db[user_b]["friend_requests"]["to"] = [
        x for x in users_db[user_b]["friend_requests"]["to"] if x != user_a
    ]
    # 互相加好友
    if user_b not in users_db[user_a]["friends"]:
        users_db[user_a]["friends"].append(user_b)
    if user_a not in users_db[user_b]["friends"]:
        users_db[user_b]["friends"].append(user_a)
    save_users()
    # 通知双方
    emit("system", {"text": f"你和 {user_b} 已成为好友", "time": now_str()})
    emit_to_user(user_b, "system", {"text": f"你和 {user_a} 已成为好友", "time": now_str()})
    emit("friend_data", {"friends": get_user_friends(user_a), "requests": get_user_friend_requests(user_a)})
    emit_to_user(user_b, "friend_data", {"friends": get_user_friends(user_b), "requests": get_user_friend_requests(user_b)})
    print(f"[好友] {user_a} <-> {user_b}")


@socketio.on("friend_reject")
def on_friend_reject(data):
    """拒绝好友请求"""
    username = find_user_by_sid(request_sid())
    if not username:
        return
    target = data.get("from", "").strip()
    users_db[username]["friend_requests"]["from"] = [
        x for x in users_db[username]["friend_requests"]["from"] if x != target
    ]
    users_db[target]["friend_requests"]["to"] = [
        x for x in users_db[target]["friend_requests"]["to"] if x != username
    ]
    save_users()
    emit("system", {"text": f"已拒绝 {target} 的好友请求", "time": now_str()})
    emit("friend_data", {"friends": get_user_friends(username), "requests": get_user_friend_requests(username)})
    emit_to_user(target, "friend_data", {"friends": get_user_friends(target), "requests": get_user_friend_requests(target)})


@socketio.on("friend_list")
def on_friend_list():
    """获取好友列表"""
    username = find_user_by_sid(request_sid())
    if not username:
        return
    emit("friend_data", {
        "friends": get_user_friends(username),
        "requests": get_user_friend_requests(username),
    })


# ---------- 群组 ----------

@socketio.on("group_create")
def on_group_create(data):
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    gname = data.get("name", "").strip()
    is_public = data.get("public", True)
    if not gname:
        emit("error", {"text": "群名不能为空"})
        return
    uid = str(uuid.uuid4())[:8]
    groups_db[uid] = {
        "name": gname,
        "members": [username],
        "creator": username,
        "public": is_public,
        "invites": [],
    }
    save_groups()
    visibility = "公开" if is_public else "私有"
    emit("system", {"text": f"群 [{gname}] 创建成功（{visibility}）", "time": now_str()})
    emit("group_list", {"groups": serialize_groups()}, broadcast=True)
    print(f"[建群] {username} 创建了 {gname} uid={uid} ({visibility})")


@socketio.on("group_join")
def on_group_join(data):
    """加入公开群"""
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    uid = data.get("uid", "").strip()
    if uid not in groups_db:
        emit("error", {"text": "群不存在"})
        return
    group = groups_db[uid]
    gname = group["name"]
    if not group["public"]:
        emit("error", {"text": f"群 [{gname}] 是私有群，需要邀请才能加入"})
        return
    if username in group["members"]:
        emit("error", {"text": "你已在群中"})
        return
    group["members"].append(username)
    save_groups()
    ts = now_str()
    save_history(f"group_{uid}", {"from": "系统", "text": f"{username} 加入了群聊", "time": ts})
    for member in group["members"]:
        if member != username:
            emit_to_user(member, "group_system", {"group_uid": uid, "group_name": gname, "text": f"{username} 加入了群聊", "time": ts})
    emit("system", {"text": f"已加入群 [{gname}]", "time": now_str()})
    emit("group_list", {"groups": serialize_groups()}, broadcast=True)
    print(f"[加群] {username} 加入 {gname} uid={uid}")


@socketio.on("group_invite")
def on_group_invite(data):
    """邀请好友加入群组"""
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    uid = data.get("uid", "").strip()
    target = data.get("to", "").strip()
    if uid not in groups_db:
        emit("error", {"text": "群不存在"})
        return
    group = groups_db[uid]
    gname = group["name"]
    if username not in group["members"]:
        emit("error", {"text": "你不在群中，无法邀请"})
        return
    if target not in users_db:
        emit("error", {"text": f"用户 {target} 不存在"})
        return
    if target in group["members"]:
        emit("error", {"text": f"{target} 已在群中"})
        return
    if target in group.get("invites", []):
        emit("error", {"text": f"已向 {target} 发送过邀请"})
        return
    group.setdefault("invites", []).append(target)
    save_groups()
    emit("system", {"text": f"已向 {target} 发送群邀请", "time": now_str()})
    emit_to_user(target, "group_invite", {
        "uid": uid,
        "name": gname,
        "from": username,
        "public": group["public"],
    })
    emit("group_list", {"groups": serialize_groups()}, broadcast=True)
    print(f"[群邀请] {username} 邀请 {target} 加入 {gname} uid={uid}")


@socketio.on("group_accept")
def on_group_accept(data):
    """接受群邀请"""
    username = find_user_by_sid(request_sid())
    if not username:
        return
    uid = data.get("uid", "").strip()
    if uid not in groups_db:
        emit("error", {"text": "群不存在"})
        return
    group = groups_db[uid]
    gname = group["name"]
    if username not in group.get("invites", []):
        emit("error", {"text": "没有收到该群的邀请"})
        return
    group["invites"].remove(username)
    group["members"].append(username)
    save_groups()
    ts = now_str()
    save_history(f"group_{uid}", {"from": "系统", "text": f"{username} 通过邀请加入了群聊", "time": ts})
    for member in group["members"]:
        if member != username:
            emit_to_user(member, "group_system", {"group_uid": uid, "group_name": gname, "text": f"{username} 加入了群聊", "time": ts})
    emit("system", {"text": f"已加入群 [{gname}]", "time": now_str()})
    emit("group_list", {"groups": serialize_groups()}, broadcast=True)
    print(f"[受邀加群] {username} 加入 {gname} uid={uid}")


@socketio.on("group_reject")
def on_group_reject(data):
    """拒绝群邀请"""
    username = find_user_by_sid(request_sid())
    if not username:
        return
    uid = data.get("uid", "").strip()
    if uid in groups_db and username in groups_db[uid].get("invites", []):
        groups_db[uid]["invites"].remove(username)
        save_groups()
    gname = groups_db.get(uid, {}).get("name", "")
    emit("system", {"text": f"已拒绝群 [{gname}] 的邀请", "time": now_str()})
    emit("group_list", {"groups": serialize_groups()})


@socketio.on("group_msg")
def on_group_msg(data):
    username = find_user_by_sid(request_sid())
    if not username:
        emit("error", {"text": "请先登录"})
        return
    uid = data.get("uid", "").strip()
    encrypted = data.get("encrypted", "").strip()  # 客户端已用群共享密钥加密
    if uid not in groups_db or username not in groups_db[uid]["members"]:
        emit("error", {"text": "你不在该群中"})
        return
    if not encrypted:
        return
    group = groups_db[uid]
    gname = group["name"]
    ts = now_str()
    save_history(f"group_{uid}", {"from": username, "encrypted": encrypted, "time": ts})
    # 服务端转发密文给所有群成员（包括发送者）
    for member in group["members"]:
        emit_to_user(member, "group_msg", {
            "group_uid": uid, "group_name": gname, "from": username,
            "encrypted": encrypted, "time": ts,
        })
    print(f"[群:{gname}] {username}: [E2E加密]")


@socketio.on("user_list")
def on_user_list():
    emit("user_list", {"users": list(online_users.keys())})


@socketio.on("get_user_key")
def on_get_user_key(data):
    """获取指定用户的DES密钥（用于客户端派生共享密钥）"""
    target = data.get("username", "").strip()
    if target in users_db:
        emit("user_key", {"username": target, "key": users_db[target].get("key", "")})
    else:
        emit("error", {"text": f"用户 {target} 不存在"})


@socketio.on("test_des")
def on_test_des(data):
    """DES兼容性测试：用指定密钥加密hello，返回密文"""
    key_hex = data.get("key", "aabbccdd11223344")
    key = bytes.fromhex(key_hex)
    ct = encrypt("hello", key)
    emit("test_des_result", {"key": key_hex, "plaintext": "hello", "ciphertext": ct.hex()})
    print(f"[测试] key={key_hex} pt=hello ct={ct.hex()}")


@socketio.on("group_list")
def on_group_list():
    emit("group_list", {"groups": serialize_groups()})


@socketio.on("history")
def on_history(data):
    target = data.get("target", "_lobby")
    records = load_history(target)
    emit("history", {"target": target, "records": records[-50:]})


# ============================================================
#  启动
# ============================================================

if __name__ == "__main__":
    os.makedirs(HISTORY_DIR, exist_ok=True)
    load_users()
    load_groups()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    print(f"[*] Web服务启动: http://0.0.0.0:{port}")
    print(f"[*] 已注册用户: {len(users_db)} 人")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
