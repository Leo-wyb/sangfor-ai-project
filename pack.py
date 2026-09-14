# -*- coding: utf-8 -*-
"""一键打包 CyberNWT.zip：把产品目录完整快照打成 download/CyberNWT.zip。

用法：python pack.py（需在 CyberNWT 产品根目录结构下执行，即 app 的上一级
目录须有 CyberNWT.exe、runtime\\、README.txt）

结构（与下载页展示一致，解压后零安装）：
  CyberNWT/
    CyberNWT.exe          ← 启动器：调 runtime\\python.exe 运行 app\\server.py
    runtime/              ← 自带 Python 3.11 运行环境（目标电脑无需装 Python）
    app/                  ← 当前目录完整快照（排除开发垃圾与密钥，见 EXCLUDE_*）
    README.txt            ← 使用说明（UTF-8 BOM，记事本双击即读）

设计原则（踩过的坑）：
- 快照式打包：demo 页依赖的 docs/videos、产品文档等资源全部随包携带，
  保证解压后所有功能可用（演示视频为本地播放，不依赖网络）；
- 不再自嵌入 zip：包内 demo 页的「下载 CyberNWT.zip」按钮在打包时改写为
  GitHub Release 公网直链（产品体积减半；能打开本包的人本就已有产品，
  home 页不设下载入口）；
- 密钥安全边界：明文 fastgpt.config 永不入包；加密形态 fastgpt.config.enc
  随包分发（不绑定机器），保证评委下载后 AI 诊断 / 复盘 / 拓扑识别即为真实大模型；
  用户数据 data.db 永不入包（首次启动自动重建）。
"""
import os
import shutil
import zipfile
from fnmatch import fnmatch

ROOT = os.path.dirname(os.path.abspath(__file__))          # app/
PARENT = os.path.dirname(ROOT)                              # 产品根目录
EXE_SRC = os.path.join(PARENT, "CyberNWT.exe")
RUNTIME_SRC = os.path.join(PARENT, "runtime")
README_SRC = os.path.join(PARENT, "README.txt")
OUT_DIR = os.path.join(ROOT, "download")
OUT = os.path.join(OUT_DIR, "CyberNWT.zip")
STAGE = os.path.join(OUT_DIR, "_stage")
RELEASE_ZIP_URL = "https://github.com/Leo-wyb/sangfor-ai-project/releases/download/v1.0/CyberNWT.zip"

# 不入包的目录（任意深度按目录名匹配）
EXCLUDE_DIRS = {
    ".git", ".zcode", "node_modules", "__pycache__", ".piptmp", ".pylibs",
    "ppt_assets",       # PPT 生成素材（仅开发期使用）
    "_stage", "_check", # 打包暂存 / 视频校验
    "_originals",       # 视频重编码前的原始高码率备份（仅本地留存）
    "_old",             # 已被 V2 取代的第一代产品文档等旧文件（仅本地留存）
}
# 不入包的文件（按文件名匹配）
EXCLUDE_FILES = {
    "data.db",          # 用户数据库：首次启动自动重建
    "fastgpt.config",   # AI 密钥明文：绝不随包分发（只允许加密形态随包）
    "server_run.log",
    "CyberNWT.zip",     # 旧包不嵌套（新包由两遍打包机制自嵌入）
}
# 不入包的相对路径通配（与 .gitignore 口径一致的开发产物）
EXCLUDE_PATTERNS = [
    "_*",               # 下划线开头 = 开发期临时产物（_patch*.py / _test_* 等）
    "verify_*.png",
    "ck4.txt",
    "灵犀测速-*.doc",    # 本机跑测速留下的报告，不随包分发
    "docs/videos/record.py",
    "docs/videos/cut.py",
    "docs/videos/check_demo.py",
]

# 使用说明兜底文案：优先读产品根目录 README.txt（与 exe 交付包同源），缺失时用这份
README_FALLBACK = r"""CyberNWT 本地产品包
=================================

一、这是什么
一个可直接运行的完整产品包，与开发目录完全同构。包含全部功能模块：
灵犀测速（全链路透视 / JSON / Prometheus）、内网感知（真实探针引擎）、
AI 故障诊断助手、案例复盘（可导出报告）、随心记录悬浮白板，
以及公开演示页（demo.html，含功能演示视频）与《CyberNWT-产品文档V2.docx》。

二、如何启动
1. 解压本压缩包到任意目录
2. 进入 CyberNWT 文件夹，双击「CyberNWT.exe」
   - 自带 Python 运行环境（runtime 目录），目标电脑无需安装任何东西
   - 启动后自动打开登录页（若未打开，浏览器访问 http://127.0.0.1:8642）
   - 若提示端口已有服务在运行，说明已启动过一次，会直接为你打开登录页
   - 关闭 CyberNWT 窗口即停止服务
   - 换端口启动：命令行运行  CyberNWT.exe 8643
   - 也可直接访问 demo.html 查看功能演示（无需登录）
3. 登录账号：admin / admin（也可在登录页自行注册）

三、要求
- Windows 10/11 即可（自带 Python 3.11 运行环境，零依赖、免安装、无需管理员权限）
- 想让局域网其他电脑访问：本机防火墙放行 8642 端口，
  其他电脑浏览器打开 http://<本机IP>:8642

四、灵犀测速使用要点
- 内网测速可选「测速线路」（本机网卡 = 一条线路，多网卡场景可针对性测试）；
- 对端地址留空 = 默认对所选线路的网关测延迟；填内网其他机器 IP
  （对方运行 CyberNWT 站点）可互测完整上下行带宽；
- 测速过程自动逐跳采样，点「查看线路」可打开物理线路视图，
  延迟突增段标红定位瓶颈，支持判断慢在接入段还是运营商段；
- 「最近测试」自动保存历史记录，鼠标悬停任一条可查看完整指标
  （延迟/抖动/上下行/负载丢包/灵犀摘要）并与最近一次结果自动对比。

五、说明
- AI 诊断 / 案例复盘在未配置密钥时以「演示模式」运行（功能完整），
  对接 FastGPT 后即切换为真实大模型回答（双知识库：故障诊断知识库 + 设备部署知识库）。
  在 app 目录创建 fastgpt.config（KEY=VALUE 每行一条）：
    LLM_BASE=https://cloud.fastgpt.cn/api/v1   （FastGPT 的 OpenAI 兼容地址）
    LLM_KEY=fastgpt-xxx                        （FastGPT「API 密钥」处创建）
    LLM_MODEL_DIAG=模型名
    LLM_MODEL_REVIEW=模型名
    （可选）LLM_THINKING=on   默认关闭模型思考以加快出答案速度，配置为 on 可恢复深度思考

六、常见问题
- 双击 exe 提示文件不完整：没有完整解压，请解压整个压缩包后再运行
- 端口被占用且不是本产品：命令行进入 CyberNWT 目录，运行  CyberNWT.exe 8643
"""


def excluded(rel, name):
    if name in EXCLUDE_FILES or name in EXCLUDE_DIRS:
        return True
    for pat in EXCLUDE_PATTERNS:
        if fnmatch(rel.replace("\\", "/"), pat) or fnmatch(name, pat):
            return True
    return False


def load_readme_bytes():
    if os.path.isfile(README_SRC):
        with open(README_SRC, "rb") as f:
            data = f.read()
        print("[readme] 使用产品根目录 README.txt（%d 字节）" % len(data))
        return data
    print("[readme] 根目录无 README.txt，使用内置兜底文案")
    return README_FALLBACK.encode("utf-8-sig")


def stage_copy():
    """把 app 快照 + exe 启动器 + runtime 复制到 download/_stage/CyberNWT。"""
    for src in (EXE_SRC, RUNTIME_SRC):
        if not os.path.exists(src):
            raise SystemExit("缺少 %s —— 请在产品根目录结构（CyberNWT.exe + runtime/ + app/）下执行打包" % src)
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    base = os.path.join(STAGE, "CyberNWT")
    app = os.path.join(base, "app")
    n_file = 0
    for cur, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_dir = os.path.relpath(cur, ROOT)
        for f in files:
            rel = os.path.normpath(os.path.join(rel_dir, f))
            if excluded(rel, f):
                continue
            src = os.path.join(cur, f)
            dst = os.path.join(app, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.copy2(src, dst)
                n_file += 1
            except PermissionError:
                print("[warn] 跳过被占用文件:", rel)
    print("[stage] app 快照：%d 个文件" % n_file)
    if not os.path.isfile(os.path.join(app, "server.py")):
        raise SystemExit("快照缺少 server.py，中止打包")
    shutil.copy2(EXE_SRC, os.path.join(base, "CyberNWT.exe"))
    shutil.copytree(RUNTIME_SRC, os.path.join(base, "runtime"))
    print("[stage] 已加入 CyberNWT.exe 与 runtime/（自带运行环境）")


def patch_staged_pages():
    """包内 demo 页的下载按钮改写为 Release 公网直链（包里不再自嵌 zip 副本）。"""
    demo = os.path.join(STAGE, "CyberNWT", "app", "demo.html")
    with open(demo, "r", encoding="utf-8") as f:
        html = f.read()
    n = html.count('download/CyberNWT.zip')
    html = html.replace('download/CyberNWT.zip', RELEASE_ZIP_URL)
    with open(demo, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    print("[stage] demo 页下载按钮已指向公网直链：%d 处" % n)


def write_zip(readme_bytes):
    if os.path.exists(OUT):
        os.remove(OUT)
    base = os.path.join(STAGE, "CyberNWT")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("CyberNWT/README.txt", readme_bytes)
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                full = os.path.join(cur, f)
                arc = os.path.relpath(full, STAGE).replace("\\", "/")
                z.write(full, arc)


readme_bytes = load_readme_bytes()
stage_copy()
patch_staged_pages()
write_zip(readme_bytes)
shutil.rmtree(STAGE)            # 清理暂存副本

size = os.path.getsize(OUT)
print("打包完成: %s (%.1f MB)" % (OUT, size / 1024 / 1024))
