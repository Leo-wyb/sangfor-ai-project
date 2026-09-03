# -*- coding: utf-8 -*-
"""CyberNWT 内网测速对端 (speedpeer)

零依赖单文件：在一台内网机器上运行后，同一局域网内的工程师
打开 CyberNWT「灵犀测速 → 内网测速」填入本机 IP 即可测内网带宽。

用法：
    python speedpeer.py            # 默认端口 8644
    python speedpeer.py 9000       # 自定义端口
    python speedpeer.py --host 0.0.0.0   # 允许其他机器测本机（默认仅本机+局域网）

接口（与前端约定）：
    GET  /peer/ping            HEAD 探活/延迟采样，返回 204
    GET  /peer/down?bytes=N    流式吐出 N 字节伪随机数据（不落盘、零拷贝节奏）
    POST /peer/up              读取并丢弃请求体，返回 {"ok":true,"bytes":N}
    GET  /peer/info            返回对端基本信息（主机名/系统/时间）
"""
import json
import os
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

CHUNK = 256 * 1024
_BLOCK = (os.urandom(CHUNK) * 4)  # 1MB 伪随机块（内存常驻，避免实时生成开销）


class PeerHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_HEAD(self):
        path = self.path.split('?')[0]
        if path == '/peer/ping':
            self.send_response(204)
            self._cors()
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(404)
            self._cors()
            self.send_header('Content-Length', '0')
            self.end_headers()

    def do_GET(self):
        parsed = self.path.split('?')
        path, query = parsed[0], parsed[1] if len(parsed) > 1 else ''
        if path == '/peer/info':
            body = json.dumps({
                'ok': True,
                'host': socket.gethostname(),
                'system': sys.platform,
                'time': time.time(),
            }).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == '/peer/down':
            try:
                n = max(1024, min(int(self._q(query, 'bytes', '8388608')), 2 * 1024 * 1024 * 1024))
            except ValueError:
                n = 8 * 1024 * 1024
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(n))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            sent = 0
            try:
                while sent < n:
                    part = min(len(_BLOCK), n - sent)
                    self.wfile.write(_BLOCK[:part])
                    sent += part
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        self.send_response(404)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if self.path.split('?')[0] != '/peer/up':
            self.send_response(404)
            self._cors()
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        length = int(self.headers.get('Content-Length', 0) or 0)
        received = 0
        try:
            while received < length:
                block = self.rfile.read(min(262144, length - received))
                if not block:
                    break
                received += len(block)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        body = json.dumps({'ok': True, 'bytes': received}).encode()
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _q(self, query, key, default):
        for kv in query.split('&'):
            if kv.startswith(key + '='):
                return kv[len(key) + 1:]
        return default

    def log_message(self, fmt, *args):
        print('[%s] %s' % (time.strftime('%H:%M:%S'), fmt % args))


def main():
    port = 8644
    host = '127.0.0.1'
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--host' and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i].isdigit():
            port = int(args[i])
            i += 1
        else:
            i += 1
    srv = ThreadingHTTPServer((host, port), PeerHandler)
    srv.daemon_threads = True
    print('[ok] CyberNWT 内网测速对端已启动: http://%s:%d  (Ctrl+C 停止)' % (host, port))
    if host == '127.0.0.1':
        print('[提示] 当前仅本机可访问。若要在其他机器上对本机测速，请使用:')
        print('       python speedpeer.py --host 0.0.0.0 %d' % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n[bye] peer stopped')


if __name__ == '__main__':
    main()
