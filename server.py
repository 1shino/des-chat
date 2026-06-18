"""DES加密TCP聊天 — Telegram风格服务端"""

import hashlib
import json
import os
import socket
import threading
import time

from protocol import send_msg, recv_msg

HOST = "0.0.0.0"
PORT = 9999

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# 运行时状态
users_db: dict[str, str] = {}            # {username: sha256_password}
online_users: dict[str, socket.socket] = {}  # {username: conn}
groups: dict[str, set[str]] = {}          # {group_name: {members}}
lock = threading.Lock()

# ============================================================
#  数据持久化
# ============================================================

def load_users():
    global users_db
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users_db = json.load(f)


def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)


def save_history(category: str, record: dict):
    """保存聊天记录到 data/history/{category}.json"""
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


def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def send_system(conn: socket.socket, text: str):
    send_msg(conn, "system", {"text": text, "time": timestamp()})


def send_error(conn: socket.socket, text: str):
    send_msg(conn, "error", {"text": text})


def broadcast_lobby(sender: str, text: str, exclude=None):
    """大厅广播"""
    ts = timestamp()
    record = {"from": sender, "text": text, "time": ts}
    save_history("_lobby", record)
    with lock:
        for user, conn in online_users.items():
            if conn is exclude:
                continue
            try:
                send_msg(conn, "chat", {"from": sender, "text": text, "time": ts})
            except Exception:
                pass


def broadcast_group(group_name: str, sender: str, text: str, exclude=None):
    """群组广播"""
    ts = timestamp()
    record = {"from": sender, "text": text, "time": ts}
    save_history(f"group_{group_name}", record)
    with lock:
        members = groups.get(group_name, set())
        for member in members:
            conn = online_users.get(member)
            if conn and conn is not exclude:
                try:
                    send_msg(conn, "group_msg", {
                        "group": group_name, "from": sender,
                        "text": text, "time": ts,
                    })
                except Exception:
                    pass


# ============================================================
#  客户端处理
# ============================================================

def handle_client(conn: socket.socket, addr):
    username = None
    try:
        while True:
            result = recv_msg(conn)
            if result is None:
                break
            msg_type, payload = result

            # ---- 注册 ----
            if msg_type == "register":
                u, p = payload["username"].strip(), payload["password"]
                if not u or not p:
                    send_error(conn, "用户名和密码不能为空")
                    continue
                with lock:
                    if u in users_db:
                        send_error(conn, "用户名已存在")
                        continue
                    users_db[u] = hash_password(p)
                    save_users()
                send_system(conn, "注册成功，请登录")
                print(f"[注册] {u} from {addr}")

            # ---- 登录 ----
            elif msg_type == "login":
                u, p = payload["username"].strip(), payload["password"]
                with lock:
                    if u not in users_db or users_db[u] != hash_password(p):
                        send_error(conn, "用户名或密码错误")
                        continue
                    if u in online_users:
                        send_error(conn, "该账号已在其他地方登录")
                        continue
                    online_users[u] = conn
                username = u
                send_system(conn, f"登录成功！欢迎回来，{u}")
                broadcast_lobby("系统", f"{u} 上线了", exclude=conn)
                print(f"[登录] {u} from {addr}")

            # ---- 需要登录的操作 ----
            elif username is None:
                send_error(conn, "请先登录")

            # ---- 大厅消息 ----
            elif msg_type == "chat":
                text = payload.get("text", "").strip()
                if text:
                    print(f"[大厅] {username}: {text}")
                    broadcast_lobby(username, text, exclude=conn)

            # ---- 私聊 ----
            elif msg_type == "private":
                target = payload.get("to", "").strip()
                text = payload.get("text", "").strip()
                if not target or not text:
                    send_error(conn, "用法: /msg 用户名 消息")
                    continue
                with lock:
                    target_conn = online_users.get(target)
                if not target_conn:
                    send_error(conn, f"用户 {target} 不在线")
                    continue
                ts = timestamp()
                save_history(f"priv_{min(username,target)}_{max(username,target)}",
                             {"from": username, "to": target, "text": text, "time": ts})
                try:
                    send_msg(target_conn, "private", {
                        "from": username, "text": text, "time": ts,
                    })
                    send_system(conn, f"[私聊→{target}] {text}")
                except Exception:
                    send_error(conn, f"发送失败")

            # ---- 创建群组 ----
            elif msg_type == "group_create":
                gname = payload.get("name", "").strip()
                if not gname:
                    send_error(conn, "群名不能为空")
                    continue
                with lock:
                    if gname in groups:
                        send_error(conn, f"群 {gname} 已存在")
                        continue
                    groups[gname] = {username}
                send_system(conn, f"群 [{gname}] 创建成功，你是第一个成员")
                print(f"[建群] {username} 创建了 {gname}")

            # ---- 加入群组 ----
            elif msg_type == "group_join":
                gname = payload.get("name", "").strip()
                with lock:
                    if gname not in groups:
                        send_error(conn, f"群 {gname} 不存在")
                        continue
                    groups[gname].add(username)
                send_system(conn, f"已加入群 [{gname}]")
                broadcast_group(gname, "系统", f"{username} 加入了群聊", exclude=conn)
                print(f"[加群] {username} 加入 {gname}")

            # ---- 群组消息 ----
            elif msg_type == "group_msg":
                gname = payload.get("group", "").strip()
                text = payload.get("text", "").strip()
                with lock:
                    if gname not in groups or username not in groups[gname]:
                        send_error(conn, f"你不在群 {gname} 中")
                        continue
                if text:
                    print(f"[群:{gname}] {username}: {text}")
                    broadcast_group(gname, username, text, exclude=conn)

            # ---- 在线用户 ----
            elif msg_type == "user_list":
                with lock:
                    users = list(online_users.keys())
                send_msg(conn, "user_list", {"users": users, "time": timestamp()})

            # ---- 群组列表 ----
            elif msg_type == "group_list":
                with lock:
                    gl = {g: list(m) for g, m in groups.items()}
                send_msg(conn, "group_list", {"groups": gl, "time": timestamp()})

            # ---- 历史记录 ----
            elif msg_type == "history":
                target = payload.get("target", "_lobby")
                records = load_history(target)
                send_msg(conn, "history", {"target": target, "records": records[-30:]})

            # ---- 退出 ----
            elif msg_type == "quit":
                break

            else:
                send_error(conn, f"未知消息类型: {msg_type}")

    except Exception as e:
        print(f"[!] {addr} 错误: {e}")
    finally:
        if username:
            with lock:
                online_users.pop(username, None)
            broadcast_lobby("系统", f"{username} 下线了")
            print(f"[离线] {username}")
        conn.close()


# ============================================================
#  主函数
# ============================================================

def main():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    load_users()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    print(f"[*] 服务端已启动，监听 {HOST}:{PORT}")
    print(f"[*] 已注册用户: {len(users_db)} 人")

    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[*] 服务端关闭")
    finally:
        server.close()


if __name__ == "__main__":
    main()
