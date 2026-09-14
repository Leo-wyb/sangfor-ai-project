# -*- coding: utf-8 -*-
"""配置密钥加密/解密（仅用 Python 标准库，零第三方依赖）。

用途：把 fastgpt.config（明文 KEY=VALUE）加密为 fastgpt.config.enc，
server.py 启动时在内存中解密使用，磁盘上不再留存明文密钥。
不绑定机器：加密文件拷到任何电脑、配合本目录自带 runtime 均可正常解密。

算法（与 TLS 1.3 同源的构造，纯标准库实现）：
- 密钥派生：PBKDF2-HMAC-SHA256，200,000 次迭代 + 16 字节随机盐
- 加密：HMAC-SHA256 计数器密钥流 XOR（流加密，每次加密随机 nonce）
- 完整性：Encrypt-then-MAC（HMAC-SHA256 标签，防篡改，篡改即解密失败）

文件格式（纯文本，便于备份/传输）：
  第 1 行: CYBERNWT-ENC-1
  第 2 行起: base64(salt | nonce | ciphertext | tag)，每 76 字符换行
"""
import base64
import hashlib
import hmac
import os
import struct

MAGIC = 'CYBERNWT-ENC-1'
_PBKDF2_ITERS = 200_000
_SALT_LEN = 16
_NONCE_LEN = 12
_TAG_LEN = 32

# 内置口令：参与密钥派生，保证加密文件在任意电脑上均可解密（可移植、零配置）。
# 与代码一同保管即可；若怀疑泄露，重新执行 encrypt_config.py 会换新盐/新 nonce 重加密。
_PASSPHRASE = 'ptq4cs8ewg0uc+xwngjX/n42V/ZfEK3yNNvkn1UOdKLc212v'


def _derive_key(salt):
    return hashlib.pbkdf2_hmac(
        'sha256', _PASSPHRASE.encode('utf-8'), salt, _PBKDF2_ITERS, dklen=32)


def _keystream(key, nonce, n):
    """HMAC-SHA256 计数器模式密钥流（HKDF-Expand 同款构造）。"""
    out = bytearray()
    counter = 0
    while len(out) < n:
        block = hmac.new(key, nonce + struct.pack('>I', counter),
                         hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:n])


def encrypt_text(text):
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key(salt)
    data = text.encode('utf-8')
    ct = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    blob = base64.b64encode(salt + nonce + ct + tag).decode('ascii')
    lines = [blob[i:i + 76] for i in range(0, len(blob), 76)]
    return MAGIC + '\n' + '\n'.join(lines) + '\n'


def decrypt_text(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0] != MAGIC:
        raise ValueError('不是本产品生成的加密文件（缺少 %s 头）' % MAGIC)
    blob = base64.b64decode(''.join(lines[1:]))
    if len(blob) < _SALT_LEN + _NONCE_LEN + _TAG_LEN:
        raise ValueError('加密文件不完整')
    salt = blob[:_SALT_LEN]
    nonce = blob[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    ct = blob[_SALT_LEN + _NONCE_LEN:-_TAG_LEN]
    tag = blob[-_TAG_LEN:]
    key = _derive_key(salt)
    want = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, want):
        raise ValueError('完整性校验失败：文件被篡改或已损坏')
    return bytes(a ^ b for a, b in
                 zip(ct, _keystream(key, nonce, len(ct)))).decode('utf-8')


def encrypt_to_file(src_text, dst_path):
    with open(dst_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(encrypt_text(src_text))


def decrypt_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return decrypt_text(f.read())


def is_encrypted_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.readline().strip() == MAGIC
    except Exception:
        return False
