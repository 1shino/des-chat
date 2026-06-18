"""DES加解密工具模块"""

import hashlib
import os

from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad

BLOCK_SIZE = DES.block_size  # 8字节


def generate_key() -> bytes:
    """生成随机8字节DES密钥"""
    return os.urandom(8)


def derive_shared_key(key_a: bytes, key_b: bytes) -> bytes:
    """从两个用户密钥派生共享密钥：SHA256(较小key + 较大key)[:8]，保证顺序一致"""
    if key_a <= key_b:
        combined = key_a + key_b
    else:
        combined = key_b + key_a
    return hashlib.sha256(combined).digest()[:8]


def encrypt(plaintext: str, key: bytes) -> bytes:
    """DES-ECB加密，返回密文bytes"""
    cipher = DES.new(key, DES.MODE_ECB)
    padded = pad(plaintext.encode("utf-8"), BLOCK_SIZE)
    return cipher.encrypt(padded)


def decrypt(ciphertext: bytes, key: bytes) -> str:
    """DES-ECB解密，返回明文str"""
    cipher = DES.new(key, DES.MODE_ECB)
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, BLOCK_SIZE).decode("utf-8")
