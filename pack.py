# -*- coding: utf-8 -*-
"""一键打包 CyberNWT.zip：把最新产品文件打成 download/CyberNWT.zip。

用法：python pack.py
设计原则（踩过的坑）：
- 启动脚本与目录名全部 ASCII，杜绝任何代码页（GBK/UTF-8）下的乱码炸弹；
- 使用说明 txt 用 UTF-8 BOM，记事本双击即读；
- zip 内文件名用英文，Windows 自带解压在任何区域设置下都不会乱码。
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "download")
OUT = os.path.join(OUT_DIR, "CyberNWT.zip")

# 资源目录内文件（贴着 server.py 放）
RES_FILES = [
    "server.py", "speedpeer.py",
    "login.html", "home.html", "speedtest.html", "topology.html",
    "diagnose.html", "review.html",
    "whiteboard.js", "bg-live.js", "html2canvas.min.js",
    "logo.png", "logo-mark.png", "sangfor-mark.svg",
    os.path.join("kb", "sangfor_kb.md"),
]

# 启动脚本：纯 ASCII，任何代码页下都不会乱码
START_BAT = r"""@echo off
setlocal
title CyberNWT Server
cd /d "%~dp0app"

echo ============================================
echo     CyberNWT starting...
echo     The login page will open in your browser.
echo     Keep this window OPEN. Closing it stops the service.
echo ============================================
echo.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py" )

if not defined PY (
    echo [ERROR] Python not found.
    echo This product needs only Python 3 standard library.
    echo Please install Python 3 first:
    echo     https://www.python.org/downloads/
    echo Remember to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo Interpreter: %PY%
echo Address: http://127.0.0.1:8642
echo Account: admin / admin
echo.
echo ------------------------------------------------------------
echo Keep this window open. Close it to stop the server.
echo ------------------------------------------------------------
echo.

%PY% server.py

echo.
echo Server stopped. Press any key to close...
pause >nul
"""

# 使用说明：UTF-8 BOM，记事本直接可读
README = """CyberNWT 本地产品包
=================================

一、这是什么
一个可直接运行的完整产品包（登录页 + 功能页 + server.py），
包含：灵犀测速 / 内网感知 / AI 诊断 / 案例复盘 / 悬浮白板。解压即用。

二、如何启动
1. 解压本压缩包到任意目录
2. 进入 CyberNWT 文件夹，双击「Start-CyberNWT.bat」
   - 自动检测 Python 并在 app 目录运行 server.py
   - 启动后自动打开登录页（若未打开，浏览器访问 http://127.0.0.1:8642）
3. 登录账号：admin / admin（也可在登录页自行注册）

三、要求
- Windows 10/11 + Python 3.8 及以上（仅标准库，无需 pip 安装任何东西）
- 想让局域网其他电脑访问：本机防火墙放行 8642 端口，
  其他电脑浏览器打开 http://<本机IP>:8642

四、常见问题
- 双击 bat 闪退：未装 Python 或未加入 PATH，看窗口内英文提示安装 Python 3
- 端口被占用：命令行进入 app 目录，运行  python server.py 8643
"""

os.makedirs(OUT_DIR, exist_ok=True)
if os.path.exists(OUT):
    os.remove(OUT)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    z.writestr("CyberNWT/README.txt", README.encode("utf-8-sig"))
    z.writestr("CyberNWT/Start-CyberNWT.bat", START_BAT.encode("ascii"))
    for rel in RES_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.isfile(src):
            raise SystemExit("缺少文件: %s" % src)
        z.write(src, os.path.join("CyberNWT", "app", rel))

size = os.path.getsize(OUT)
print("打包完成: %s (%.1f KB)" % (OUT, size / 1024))
