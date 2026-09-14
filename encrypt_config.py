# -*- coding: utf-8 -*-
"""fastgpt.config 密钥加密工具：磁盘上不留明文密钥，服务功能不受影响。

用法（在本目录执行；推荐用产品自带运行环境）：
  ..\runtime\python.exe encrypt_config.py             加密 fastgpt.config → fastgpt.config.enc，
                                                      校验通过后删除明文文件（默认行为）
  ..\runtime\python.exe encrypt_config.py --keep      加密但保留明文（仅开发调试用）
  ..\runtime\python.exe encrypt_config.py --decrypt   解密还原 fastgpt.config（改密钥前先解密，
                                                      改完再执行一次默认加密），可加 --remove-enc 同时删除 .enc

说明：
- server.py 启动时优先读取 fastgpt.config.enc 并在内存中解密，功能与交互完全不变；
- 加密文件不绑定机器，整包拷贝到任何电脑均可正常解密使用；
- 若没有 fastgpt.config 也没有 fastgpt.config.enc，AI 功能照常走「演示模式」。
"""
import os
import sys

# 自带 runtime 为嵌入式发行版（python311._pth 隔离），需显式把本目录加入模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import secrets_util

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAIN = os.path.join(ROOT, 'fastgpt.config')
ENC = os.path.join(ROOT, 'fastgpt.config.enc')


def do_encrypt(keep_plain):
    if not os.path.isfile(PLAIN):
        sys.exit('[!] 未找到 fastgpt.config，无需加密（如已加密过则直接使用 fastgpt.config.enc）')
    with open(PLAIN, 'r', encoding='utf-8') as f:
        text = f.read()
    secrets_util.encrypt_to_file(text, ENC)
    # 回读校验：解密结果必须与明文逐字节一致，才允许删除明文
    back = secrets_util.decrypt_file(ENC)
    if back != text:
        sys.exit('[!] 加密校验失败，已保留原明文文件，请勿删除 fastgpt.config')
    print('[ok] 已加密生成 fastgpt.config.enc（完整性校验通过）')
    if keep_plain:
        print('[i] 按要求保留明文 fastgpt.config（服务优先使用加密文件）')
    else:
        os.remove(PLAIN)
        print('[ok] 已删除明文 fastgpt.config，磁盘上不再留存密钥明文')
        print('[i] 以后要改密钥：先  python encrypt_config.py --decrypt，改完再运行一次加密')


def do_decrypt(remove_enc):
    if not os.path.isfile(ENC):
        sys.exit('[!] 未找到 fastgpt.config.enc，无需解密')
    text = secrets_util.decrypt_file(ENC)
    with open(PLAIN, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('[ok] 已解密还原 fastgpt.config')
    if remove_enc:
        os.remove(ENC)
        print('[ok] 已删除 fastgpt.config.enc')


def main():
    argv = sys.argv[1:]
    if '--decrypt' in argv:
        do_decrypt(remove_enc='--remove-enc' in argv)
    else:
        do_encrypt(keep_plain='--keep' in argv)


if __name__ == '__main__':
    main()
