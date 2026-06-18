"""消息协议模块 — JSON消息的序列化与反序列化"""

import json
import struct
from crypto_utils import encrypt, decrypt

DES_KEY = b"8bytekey"  # DES密钥，必须8字节


def pack_msg(msg_type: str, payload: dict, key: bytes = DES_KEY) -> bytes:
    """构造加密消息：[4字节长度][DES加密的JSON]"""
    msg = json.dumps({"type": msg_type, "payload": payload}, ensure_ascii=False)
    ciphertext = encrypt(msg, key)
    return struct.pack("!I", len(ciphertext)) + ciphertext


def unpack_msg(data: bytes, key: bytes = DES_KEY) -> tuple[str, dict] | None:
    """解密并解析消息（data为纯密文，不含长度头），返回 (type, payload)"""
    try:
        plaintext = decrypt(data, key)
        msg = json.loads(plaintext)
        return msg["type"], msg["payload"]
    except Exception:
        return None


def recv_raw(sock) -> bytes | None:
    """从socket读取一条原始加密消息（含长度头），返回密文bytes"""
    header = sock.recv(4)
    if not header or len(header) < 4:
        return None
    length = struct.unpack("!I", header)[0]
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def send_msg(sock, msg_type: str, payload: dict):
    """发送一条加密消息"""
    raw = pack_msg(msg_type, payload)
    sock.sendall(raw)


def recv_msg(sock) -> tuple[str, dict] | None:
    """接收并解密一条消息"""
    data = recv_raw(sock)
    if data is None:
        return None
    return unpack_msg(data)
