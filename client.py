"""DES加密TCP聊天 — Telegram风格客户端"""

import socket
import sys
import threading

from protocol import send_msg, recv_msg

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9999


def receive_loop(sock: socket.socket, stop_event: threading.Event):
    """持续接收并显示服务端消息"""
    while not stop_event.is_set():
        try:
            result = recv_msg(sock)
            if result is None:
                print("\n[*] 与服务器的连接已断开")
                stop_event.set()
                break
            msg_type, payload = result
            display(msg_type, payload)
        except Exception:
            if not stop_event.is_set():
                print("\n[*] 连接异常断开")
                stop_event.set()
            break


def display(msg_type: str, payload: dict):
    """格式化显示消息"""
    if msg_type == "system":
        print(f"  ✅ {payload['text']}")
    elif msg_type == "error":
        print(f"  ❌ {payload['text']}")
    elif msg_type == "chat":
        print(f"  [{payload['time']}] {payload['from']}: {payload['text']}")
    elif msg_type == "private":
        print(f"  💬 [{payload['time']}] {payload['from']} → 你: {payload['text']}")
    elif msg_type == "group_msg":
        print(f"  👥 [{payload['group']}] [{payload['time']}] {payload['from']}: {payload['text']}")
    elif msg_type == "user_list":
        users = payload["users"]
        print(f"  📋 在线用户({len(users)}): {', '.join(users)}")
    elif msg_type == "group_list":
        groups = payload["groups"]
        if not groups:
            print("  📋 暂无群组")
        else:
            print("  📋 群组列表:")
            for g, members in groups.items():
                print(f"    [{g}] 成员: {', '.join(members)}")
    elif msg_type == "history":
        records = payload["records"]
        target = payload["target"]
        if not records:
            print(f"  📜 {target}: 暂无记录")
        else:
            print(f"  📜 {target} 最近{len(records)}条记录:")
            for r in records:
                if "group" in r:
                    print(f"    [{r['time']}] {r['from']}: {r['text']}")
                elif "to" in r:
                    print(f"    [{r['time']}] {r['from']} → {r['to']}: {r['text']}")
                else:
                    print(f"    [{r['time']}] {r['from']}: {r['text']}")
    else:
        print(f"  [{msg_type}] {payload}")


def auth_flow(sock: socket.socket) -> bool:
    """注册/登录流程，成功返回True"""
    print("=" * 45)
    print("    DES加密聊天 — Telegram风格")
    print("=" * 45)
    print("  1. 注册")
    print("  2. 登录")
    print("=" * 45)

    while True:
        choice = input("请选择 (1/2): ").strip()
        if choice in ("1", "2"):
            break
        print("  请输入 1 或 2")

    username = input("用户名: ").strip()
    password = input("密  码: ").strip()

    if choice == "1":
        send_msg(sock, "register", {"username": username, "password": password})
        result = recv_msg(sock)
        if result:
            display(result[0], result[1])
            if result[0] == "error":
                return False
        # 注册成功后要求登录
        print("\n请登录：")
        username = input("用户名: ").strip()
        password = input("密  码: ").strip()

    send_msg(sock, "login", {"username": username, "password": password})
    result = recv_msg(sock)
    if result:
        display(result[0], result[1])
        if result[0] == "error":
            return False
        return True
    return False


def print_help():
    print("""
╔══════════════════════════════════════════════╗
║              命 令 帮 助                     ║
╠══════════════════════════════════════════════╣
║  直接输入文字    →  大厅广播（所有人可见）     ║
║  /msg 用户名 消息 →  私聊                     ║
║  /create 群名    →  创建群组                  ║
║  /join 群名      →  加入群组                  ║
║  /gmsg 群名 消息  →  群组消息                 ║
║  /list           →  查看在线用户              ║
║  /groups         →  查看群组列表              ║
║  /history 名称   →  查看历史记录              ║
║  /help           →  显示此帮助                ║
║  /quit           →  退出                     ║
╚══════════════════════════════════════════════╝
""")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
    except ConnectionRefusedError:
        print("[!] 无法连接服务端，请确认服务端已启动")
        sys.exit(1)

    # 认证流程
    if not auth_flow(sock):
        sock.close()
        sys.exit(1)

    # 登录成功，启动接收线程
    stop_event = threading.Event()
    recv_thread = threading.Thread(target=receive_loop, args=(sock, stop_event), daemon=True)
    recv_thread.start()

    print_help()

    # 主线程处理用户输入
    try:
        while not stop_event.is_set():
            msg = input().strip()
            if not msg:
                continue

            if msg == "/quit":
                send_msg(sock, "quit", {})
                print("[*] 已退出")
                break

            elif msg == "/help":
                print_help()

            elif msg == "/list":
                send_msg(sock, "user_list", {})

            elif msg == "/groups":
                send_msg(sock, "group_list", {})

            elif msg.startswith("/msg "):
                parts = msg.split(maxsplit=2)
                if len(parts) < 3:
                    print("  用法: /msg 用户名 消息")
                else:
                    send_msg(sock, "private", {"to": parts[1], "text": parts[2]})

            elif msg.startswith("/create "):
                name = msg.split(maxsplit=1)[1].strip()
                send_msg(sock, "group_create", {"name": name})

            elif msg.startswith("/join "):
                name = msg.split(maxsplit=1)[1].strip()
                send_msg(sock, "group_join", {"name": name})

            elif msg.startswith("/gmsg "):
                parts = msg.split(maxsplit=2)
                if len(parts) < 3:
                    print("  用法: /gmsg 群名 消息")
                else:
                    send_msg(sock, "group_msg", {"group": parts[1], "text": parts[2]})

            elif msg.startswith("/history "):
                target = msg.split(maxsplit=1)[1].strip()
                send_msg(sock, "history", {"target": target})

            else:
                # 普通消息 → 大厅广播
                send_msg(sock, "chat", {"text": msg})

    except (KeyboardInterrupt, EOFError):
        print("\n[*] 已退出")
    finally:
        stop_event.set()
        sock.close()


if __name__ == "__main__":
    main()
