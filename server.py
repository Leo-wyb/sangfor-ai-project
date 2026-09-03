# -*- coding: utf-8 -*-
"""CyberNWT —— 本地演示服务器

零依赖：仅使用 Python 标准库（HTTP 服务 + SQLite 数据库）。
启动：  python server.py [端口]      （默认端口 8642，启动后自动打开浏览器）
演示账号：admin / admin
"""
import hashlib
import json
import os
import random
import re
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zlib
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, 'data.db')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8642
SESSION_TTL = 7 * 24 * 3600.0

# FastGPT 外接配置（可选）：设置后 AI 功能自动从演示回复切换为真实大模型。
# 两种方式，环境变量优先：
#   1) 环境变量  FASTGPT_BASE / FASTGPT_KEY / FASTGPT_TIMEOUT
#   2) 根目录下 fastgpt.config 文件（KEY=VALUE 每行一条，已加入 .gitignore）：
#        FASTGPT_BASE=https://cloud.fastgpt.cn/api/v1   （OpenAI 兼容 /chat/completions）
#        FASTGPT_KEY=fastgpt-xxxx
def _load_fastgpt_config():
    cfg = {}
    path = os.path.join(ROOT, 'fastgpt.config')
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for ln in f:
                    ln = ln.strip()
                    if ln and not ln.startswith('#') and '=' in ln:
                        k, v = ln.split('=', 1)
                        cfg[k.strip()] = v.strip()
        except Exception as e:
            print('[config] fastgpt.config 读取失败: %r' % e)
    return cfg

_FG_CFG = _load_fastgpt_config()   # 通用键值配置（现仅承载直连大模型 LLM_* 配置）
# 直连大模型通道（优先于 FastGPT）：OpenAI 兼容协议，省 token 模式
LLM_BASE = os.environ.get('LLM_BASE', _FG_CFG.get('LLM_BASE', '')).rstrip('/')
LLM_KEY = os.environ.get('LLM_KEY', _FG_CFG.get('LLM_KEY', ''))
LLM_MODEL = {
    'diagnose': os.environ.get('LLM_MODEL_DIAG', _FG_CFG.get('LLM_MODEL_DIAG', 'glm-5.3-flash')),
    'review': os.environ.get('LLM_MODEL_REVIEW', _FG_CFG.get('LLM_MODEL_REVIEW', 'deepseek-v4-flash-0731')),
}
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', _FG_CFG.get('LLM_TIMEOUT', '120')))
if LLM_BASE and LLM_KEY:
    print('[config] 直连大模型已接入: %s  诊断=%s 复盘=%s' % (LLM_BASE, LLM_MODEL['diagnose'], LLM_MODEL['review']))

# 本地知识库（迁移自 FastGPT 知识库）：按关键词检索，注入诊断提示词
KB_PATH = os.path.join(ROOT, 'kb', 'sangfor_kb.md')
_KB_SECTIONS = []
def _load_kb():
    if _KB_SECTIONS:
        return
    try:
        raw = open(KB_PATH, encoding='utf-8').read()
    except OSError:
        return
    for sec in raw.split('\n# ')[1:]:
        lines = sec.split('\n')
        title = lines[0].lstrip('#[] ').strip()
        kws, body = [], []
        for l in lines[1:]:
            if l.startswith('关键词:'):
                kws = [k.strip().lower() for k in l[len('关键词:'):].replace('，', ',').split(',') if k.strip()]
            else:
                body.append(l)
        if kws:
            _KB_SECTIONS.append({'title': title, 'kws': kws, 'body': '\n'.join(body).strip()})
def kb_lookup(text):
    """按关键词命中数取相关度最高的知识库小节，控制注入长度以省 token。"""
    _load_kb()
    if not _KB_SECTIONS:
        return ''
    t = text.lower()
    scored = []
    for sec in _KB_SECTIONS:
        score = sum(1 for k in sec['kws'] if k in t)
        if score:
            scored.append((score, sec))
    scored.sort(key=lambda x: -x[0])
    parts = ['【' + sec['title'] + '】\n' + sec['body'] for _, sec in scored[:2]]
    if not parts:
        return ''
    kb = '\n\n'.join(parts)
    return kb[:750]

# 测速下行缓冲：预生成 4MB 随机数据，避免测试时临时生成拖慢吞吐
_SPEED_CHUNK = os.urandom(4 * 1024 * 1024)

# 灵犀测速 · 定位服务（多源依次尝试，全部为国内源）
# 腾讯新闻 IP 接口（省市）→ 百度开放数据（运营商）→ ipip.net 文本接口（兜底）
SPEED_GEO_APIS = [
    'https://r.inews.qq.com/api/ip2city',
    'https://myip.ipip.net',
]

GEO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
}


def _geo_baidu_isp(ip):
    """用百度开放数据接口补充运营商信息。"""
    url = ('https://opendata.baidu.com/api.php?query=%s&co=&resource_id=6006&oe=utf8' % ip)
    req = urllib.request.Request(url, headers=GEO_HEADERS)
    with urllib.request.urlopen(req, timeout=4) as r:
        data = json.loads(r.read().decode('utf-8', errors='replace'))
    loc = str(((data.get('data') or [{}])[0]).get('location', ''))
    parts = loc.split()
    return parts[-1] if len(parts) > 1 else ''


# 大陆 Ookla 测速节点扫描：7 大区域中心并行查询，汇总大陆全部公开节点
# （大陆公开 Ookla 节点稀疏，单点查询会被港澳台节点挤掉，需按区域扫描）
OOKLA_SCAN_CENTERS = [
    ('华东', 31.23, 121.47), ('华南', 23.13, 113.26), ('华北', 39.90, 116.40),
    ('华中', 30.59, 114.30), ('西南', 30.57, 104.06), ('西北', 34.34, 108.94),
    ('东北', 41.80, 123.43),
]
_OOKLA_CN_CACHE = {'nodes': None, 'ts': 0.0}


def ookla_cn_nodes():
    """并行扫描大陆各区域中心，返回大陆全部公开 Ookla 上行测速节点（缓存 30 分钟）。"""
    now = time.time()
    if _OOKLA_CN_CACHE['nodes'] is not None and now - _OOKLA_CN_CACHE['ts'] < 1800:
        return _OOKLA_CN_CACHE['nodes']
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def scan(center):
        _, lat, lon = center
        url = ('https://www.speedtest.net/api/js/servers?engine=js&limit=40&lat=%s&lon=%s' % (lat, lon))
        try:
            req = urllib.request.Request(url, headers=GEO_HEADERS)
            raw = urllib.request.urlopen(req, timeout=8, context=ctx).read().decode('utf-8', errors='replace')
        except Exception:
            return []
        out = []
        for s in json.loads(raw):
            host = str(s.get('host', ''))
            if s.get('country') != 'China' or any(x in host for x in ('.hk', '.tw', '.mo')):
                continue
            if host:
                out.append((host, {'name': '%s · %s' % (s.get('name', ''), s.get('sponsor', '')),
                                   'url': s.get('url', ''), 'host': host}))
        return out

    seen = {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        for pairs in ex.map(scan, OOKLA_SCAN_CENTERS):
            for host, info in pairs:
                if host not in seen:
                    seen[host] = info
    nodes = sorted(seen.values(), key=lambda n: n['host'])
    if nodes:
        _OOKLA_CN_CACHE['nodes'] = nodes
        _OOKLA_CN_CACHE['ts'] = now
    return nodes

# 内网测速对端默认端口（与 speedpeer.py 一致）
PEER_DEFAULT_PORT = 8644

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
    '.zip': 'application/zip',
}


# ---------------- 数据库 ----------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 120000).hex()


def add_user(username, password):
    salt = secrets.token_hex(16)
    with db() as conn:
        conn.execute(
            'INSERT INTO users(username, pw_hash, salt, created_at) VALUES(?,?,?,?)',
            (username, hash_password(password, salt), salt, time.time()))


def verify_user(username, password):
    with db() as conn:
        row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if row is None:
        return False
    return secrets.compare_digest(hash_password(password, row['salt']), row['pw_hash'])


def create_session(username):
    token = secrets.token_hex(32)
    with db() as conn:
        conn.execute('INSERT INTO sessions(token, username, expires) VALUES(?,?,?)',
                     (token, username, time.time() + SESSION_TTL))
    return token


def session_user(token):
    if not token:
        return None
    with db() as conn:
        row = conn.execute('SELECT username, expires FROM sessions WHERE token=?',
                           (token,)).fetchone()
    if row is None or row['expires'] < time.time():
        return None
    return row['username']


def drop_session(token):
    if token:
        with db() as conn:
            conn.execute('DELETE FROM sessions WHERE token=?', (token,))


# ---------------- AI（FastGPT / 演示模式） ----------------

# 场景指令：追加到用户消息尾部，约束 agent 输出形态（知识库优先 / 追问 / 表格清单）
_SCENE_SYSTEM = {
    'diagnose': "你是深信服设备故障诊断专家，帮助网络工程师快速定位和解决故障。规则：1)回答直接精炼，控制在250字内，不用#标题，不用「」→等特殊符号，菜单路径用/分隔（如 系统/路由/静态路由）；2)需要给排查步骤时，用Markdown表格输出排查清单（列：步骤|执行动作/命令|预期结果|异常时的处理），最多6行；3)需要给解决方案时，分步骤写清具体操作（进入的页面/命令、参数、预期反馈）；4)用户信息不足（缺设备型号/版本、组网方式、现象细节、日志）时：先给初步方向，结尾以 追问1：、追问2：、追问3： 的格式（每行一条）提出最多3个追问；5)以深信服设备（AF/AC/AD/EDR/上网行为管理等）知识为主，可结合通用网络知识。",
    'review': "你是项目复盘报告生成器。根据用户输入生成「简历排版风格」的项目复盘报告（Markdown）：报告标题+一句话项目定位；基本信息表格（项目名称/所属阶段/时间窗口/担任角色）；项目概述；过程时间线表格（时间｜关键动作｜结果）；关键问题与根因表格（问题｜根因｜解决方式）；方法论要点；可复用文档清单表格。未填写处用（待补充：…）占位，不要编造事实；结尾附「建议补充的信息」清单。全文简体中文，约500字。"
}


def _msg_text(content):
    """取消息文本；兼容纯文本与多模态（文本+图片）数组格式。"""
    if isinstance(content, list):
        return ' '.join(str(p.get('text', '')) for p in content
                        if isinstance(p, dict) and p.get('type') == 'text').strip()
    return str(content or '').strip()


def _strip_images(messages):
    """仅保留最后一条消息中的图片（多模态），其余降级为文字标注，节省 token 与流量。"""
    out = []
    last = len(messages) - 1
    for i, m in enumerate(messages):
        c = m.get('content')
        if isinstance(c, list) and i != last:
            n = sum(1 for p in c if isinstance(p, dict) and p.get('type') == 'image_url')
            c = (_msg_text(c) + (' [已附图片×%d]' % n if n else '')) or '[图片]'
        out.append({'role': m.get('role', 'user'), 'content': c})
    return out


def _has_image(messages):
    return any(isinstance(m.get('content'), list) and
               any(isinstance(p, dict) and p.get('type') == 'image_url' for p in m['content'])
               for m in messages)


def _llm_chat(messages, scene='diagnose'):
    """直连大模型（OpenAI 兼容）。失败返回 None。系统提示词承载场景要求，历史截短省 token。"""
    if not LLM_BASE or not LLM_KEY:
        return None
    sys_txt = _SCENE_SYSTEM.get(scene, '')
    if scene == 'diagnose':
        kb = kb_lookup(_msg_text(messages[-1].get('content')) if messages else '')
        if kb:
            sys_txt += '\n\n以下是本站知识库中与该问题相关的参考资料（迁移自原知识库，可直接引用）：\n' + kb
    msgs = [{'role': 'system', 'content': sys_txt}]
    msgs += _strip_images(messages)[-4:]

    def _call(call_msgs):
        body = {'model': LLM_MODEL.get(scene, 'glm-5.3-flash'), 'messages': call_msgs,
                'stream': False, 'temperature': 0.5,
                'max_tokens': 3000 if scene == 'review' else 900}
        req = urllib.request.Request(
            LLM_BASE + '/chat/completions',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + LLM_KEY})
        # 网关偶发返回空 content：最多尝试 2 次
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                    data = json.loads(r.read().decode('utf-8'))
                content = (data.get('choices') or [{}])[0].get('message', {}).get('content')
                if content:
                    return content
                print('[ai] 直连大模型第 %d 次返回空内容' % attempt)
            except Exception as e:
                print('[ai] 直连大模型调用失败: %r' % e)
        return None

    r = _call(msgs)
    if r:
        return r
    # 模型 / 网关不支持图片输入时自动降级：去掉图片重试，避免整段对话掉到演示模式
    if _has_image(msgs):
        print('[ai] 疑似模型不支持图片输入，降级为纯文本重试')
        r = _call([{'role': m['role'],
                    'content': (_msg_text(m['content']) or '[图片]') if isinstance(m['content'], list)
                    else m['content']} for m in msgs])
        if r:
            return r
    return None


def ai_chat(messages, scene='diagnose'):
    """直连大模型（含本地知识库检索注入）；失败时回退演示回复。"""
    r = _llm_chat(messages, scene)
    if r:
        return r, 'llm'
    return None, 'demo'


def demo_diagnose(text):
    t = text.lower()
    if any(k in t for k in ('上架', '装机', '硬件', '加电', '面板')):
        key = '上架'
    elif any(k in t for k in ('割接', '切换', '迁移', '替换')):
        key = '割接'
    elif any(k in t for k in ('vpn', 'ssl', 'ipsec', '隧道')):
        key = 'vpn'
    elif any(k in t for k in ('丢包', '延迟', '变慢', '卡顿', '中断')):
        key = '丢包'
    else:
        return ('**【演示模式】** 当前未接入 FastGPT，以下为本地规则生成的通用排查思路。\n\n'
                '针对你描述的现象，建议按下面的顺序收敛问题：\n\n'
                '- **1. 现象固化**：记录故障时间点、影响范围、拓扑位置与最近变更\n'
                '- **2. 信息采集**：`show cpu-protect`、`show session`、接口错包计数与系统日志\n'
                '- **3. 分段定位**：从终端到网关到出口逐段验证连通性与性能\n'
                '- **4. 变更回退**：确认是否与近期配置变更相关，必要时先回退止血\n'
                '- **5. 根因闭环**：定位后补充监控与巡检项，形成复盘记录\n\n'
                '配置 `FASTGPT_BASE` / `FASTGPT_KEY` 环境变量后，这里将切换为你的 FastGPT 知识库大模型回答。')
    steps = _DEMO_STEPS[key]
    lines = ['**【演示模式】** 未接入 FastGPT，以下为「%s」场景的本地经验模板：\n' % key]
    for i, s in enumerate(steps, 1):
        lines.append('- **步骤 %d**：%s' % (i, s))
    lines.append('\n把具体报错、日志片段或 `show` 输出贴给我，可进一步缩小范围；'
                 '接入 FastGPT 后将由你的知识库给出针对性分析。')
    return '\n'.join(lines)


def demo_review(text):
    head = text.strip().replace('\n', ' ')[:60] or '（未填写项目过程）'
    return (
        '# 项目复盘报告（演示模式）\n\n'
        '> 当前未接入 FastGPT，以下为本地模板生成的报告骨架；'
        '配置 `FASTGPT_BASE` / `FASTGPT_KEY` 后自动切换为 AI 生成的深度复盘。\n\n'
        '## 一、项目概述\n\n%s%s\n\n'
        '## 二、过程时间线\n\n'
        '- **准备阶段**：方案评审、资源协调、配置预生成与备份\n'
        '- **实施阶段**：按窗口执行变更，逐段验证业务连通\n'
        '- **验证阶段**：业务观察与性能复核，输出验收结论\n\n'
        '## 三、关键问题与根因\n\n'
        '- 待补充：实施中遇到的具体问题、定位路径与根因结论\n\n'
        '## 四、方法论提炼（可复制的经验）\n\n'
        '- 变更前必备：配置备份、回退方案、责任分工表\n'
        '- 变更中原则：先旁路后串接、分段验证、全量留痕\n'
        '- 变更后动作：30 分钟观察期、监控补点、复盘归档\n\n'
        '## 五、风险与改进项\n\n'
        '- 待补充：本次暴露的流程/技术短板与对应改进措施\n\n'
        '## 六、总结\n\n'
        '本项目整体过程可控，建议将上述经验沉淀入团队知识库，供同类交付场景复用。\n'
        % (head, '……' if len(text.strip()) > 60 else ''))


# ---------------- 内网感知 NetSense ----------------

def read_local_nic():
    """真实读取本机网卡信息（Windows: ipconfig /all，兼容中英文系统输出）。"""
    try:
        raw = subprocess.run(['ipconfig', '/all'], capture_output=True, timeout=5).stdout
    except Exception:
        return None
    text = ''
    for enc in ('gbk', 'utf-8', 'cp437'):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text:
        text = raw.decode('gbk', 'replace')

    # 中英文关键字对照（系统显示语言可能为任一种）
    K = {
        'host': ('主机名', 'Host Name'),
        'ipv4': ('IPv4 地址', 'IPv4 Address'),
        'mask': ('子网掩码', 'Subnet Mask'),
        'gw': ('默认网关', 'Default Gateway'),
        'mac': ('物理地址', 'Physical Address'),
        'dhcp': ('DHCP 已启用', 'DHCP Enabled'),
        'dns': ('DNS 服务器', 'DNS Servers'),
        'desc': ('描述', 'Description'),
    }

    def pick(block, key):
        for ln in block:
            s = ln.strip()
            for nm in K[key]:
                if s.startswith(nm) and ':' in s:
                    return s.split(':', 1)[1].strip().rstrip(',').strip()
        return None

    hostname = ''
    blocks, cur = [], []
    for ln in text.splitlines():
        if ln and not ln.startswith(' ') and ln.rstrip().endswith(':'):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)
    for b in blocks:
        if b and pick(b, 'host'):
            hostname = pick(b, 'host')
            break

    best = None
    for b in blocks:
        head = b[0] if b else ''
        if ('适配器' not in head) and ('adapter' not in head.lower()):
            continue
        ip = pick(b, 'ipv4')
        gw = pick(b, 'gw')
        if not ip or not gw:
            continue
        name = ''
        for tag in ('适配器', 'adapter'):
            idx = head.rfind(tag)
            if idx >= 0:
                name = head[idx + len(tag):]
                break
        name = re.sub(r'[^\x20-\x7e\u4e00-\u9fff]', '', name).strip().rstrip(':')
        desc = pick(b, 'desc') or ''
        is_wifi = any(k in (name + desc).upper() for k in ('WLAN', '无线', 'WI-FI', 'WIFI', '802.11', 'WIRELESS'))

        def ipv4(s):
            m = re.search(r'\d+\.\d+\.\d+\.\d+', s or '')
            return m.group(0) if m else ''
        dhcp_val = (pick(b, 'dhcp') or '').lower()
        best = {
            'adapter': name or desc[:24], 'desc': desc, 'conn_type': 'wifi' if is_wifi else 'ethernet',
            'ip': ipv4(ip), 'mask': ipv4(pick(b, 'mask')) or '255.255.255.0',
            'gateway': ipv4(gw), 'mac': pick(b, 'mac') or '',
            'dhcp': dhcp_val.startswith('是') or dhcp_val.startswith('yes'),
            'dns': ipv4(pick(b, 'dns')), 'hostname': hostname,
        }
        if is_wifi:
            break  # 优先呈现无线网卡（对应工程师连 WiFi 的场景）
    return best


def mask_to_prefix(mask):
    try:
        return bin(int(mask.split('.')[0]) << 24 | int(mask.split('.')[1]) << 16 |
                   int(mask.split('.')[2]) << 8 | int(mask.split('.')[3])).count('1')
    except Exception:
        return 24


# ================= 内网真实感知引擎（ICMP + ARP + OUI + 端口 + BSSID 多指纹实测） =================

# 常见厂商 OUI 前缀（工程现场主流设备；未知前缀由端口/TTL 指纹兜底）
OUI_DB = {
    '00-18-82': ('华为', 'net'), '00-1e-10': ('华为', 'net'), '00-25-9e': ('华为', 'net'),
    '28-6e-d4': ('华为', 'net'), '34-29-12': ('华为', 'net'), '4c-1f-cc': ('华为', 'net'),
    '48-46-fb': ('华为', 'net'), '88-28-b3': ('华为', 'net'), 'c8-0e-14': ('华为', 'net'),
    'e0-24-7f': ('华为', 'net'), 'f4-4c-7f': ('华为', 'net'), '58-60-5f': ('华为', 'net'),
    '00-0f-e2': ('H3C', 'net'), '00-23-89': ('H3C', 'net'), '3c-8c-40': ('H3C', 'net'),
    '80-f6-2e': ('H3C', 'net'), 'd4-3a-e9': ('H3C', 'net'),
    '00-00-0c': ('思科', 'net'), '00-1b-0d': ('思科', 'net'), '00-1e-14': ('思科', 'net'),
    '00-26-0b': ('思科', 'net'), 'f8-72-ea': ('思科', 'net'),
    '00-14-a9': ('锐捷', 'net'), '90-55-de': ('锐捷', 'net'), 'c0-82-e1': ('锐捷', 'net'),
    '50-c7-bf': ('TP-LINK', 'net'), '00-27-19': ('TP-LINK', 'net'), '14-cc-20': ('TP-LINK', 'net'),
    'a4-2b-b0': ('TP-LINK', 'net'),
    '00-05-5d': ('D-Link', 'net'), '14-d6-4d': ('D-Link', 'net'),
    '00-d0-d0': ('中兴', 'net'), 'f8-4e-06': ('中兴', 'net'), '74-d5-0e': ('深信服', 'net'),
    '00-1f-29': ('惠普', 'printer'), '3c-52-82': ('惠普', 'printer'), '00-1a-a0': ('惠普', 'printer'),
    '10-1f-74': ('惠普', 'printer'), 'b0-5a-da': ('惠普', 'printer'),
    '00-1e-a2': ('佳能', 'printer'), '18-8b-45': ('佳能', 'printer'),
    '00-80-92': ('兄弟', 'printer'), '30-05-5c': ('兄弟', 'printer'),
    '00-1b-25': ('爱普生', 'printer'), 'ac-18-26': ('爱普生', 'printer'),
    '00-00-aa': ('富士施乐', 'printer'), '00-80-77': ('富士施乐', 'printer'),
    '00-1e-8f': ('理光', 'printer'), '00-25-15': ('理光', 'printer'),
    '64-87-88': ('京瓷', 'printer'), '00-04-00': ('利盟', 'printer'),
    '00-e0-4c': ('Realtek', 'nic'), '3c-97-0e': ('Intel', 'nic'), '8c-ec-4b': ('Intel', 'nic'),
    'f0-18-98': ('Apple', 'nic'), 'ac-de-48': ('Apple', 'nic'),
    '28-6c-07': ('小米', 'nic'), '64-09-80': ('小米', 'nic'),
    '88-ae-1d': ('戴尔', 'nic'), 'f8-b1-56': ('戴尔', 'nic'), '00-59-19': ('联想', 'nic'),
}

PRINTER_PORTS = {9100, 631, 515}   # JetDirect / IPP / LPD
NETMGMT_PORTS = {23, 22, 161}      # Telnet / SSH / SNMP
PC_PORTS = {445, 135}              # SMB / RPC
SCAN_PORTS = (22, 23, 80, 135, 161, 443, 445, 515, 631, 9100)


def run_cmd(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.stdout.decode('gbk', 'replace')
    except Exception:
        return ''


def oui_lookup(mac):
    if not mac or len(mac) < 8:
        return '', ''
    return OUI_DB.get(mac[:8].lower(), ('', ''))


def wifi_link_info():
    """netsh 实测 Wi-Fi 关联信息（SSID / BSSID / 信号），AP 定位的实测依据。"""
    info = {}
    for ln in run_cmd(['netsh', 'wlan', 'show', 'interfaces'], 4).splitlines():
        s = ln.strip()
        for key, name in (('SSID', 'ssid'), ('BSSID', 'bssid')):
            if s.startswith(key) and ':' in s:
                info[name] = s.split(':', 1)[1].strip()
        for sig_key in ('信号', 'Signal'):
            if s.startswith(sig_key) and ':' in s:
                m = re.search(r'(\d+)', s.split(':', 1)[1])
                if m:
                    info['signal'] = int(m.group(1))
    return info


def norm_mac(s):
    """MAC 归一化（去分隔符小写），统一 netsh 'aa:bb:cc' 与 ARP 'aa-bb-cc' 两种格式。"""
    return re.sub(r'[^0-9a-f]', '', (s or '').lower())


def ping_sweep(base, workers=64):
    """并发 ICMP 扫描 /24 网段，返回 {ip: ttl}。"""
    result = {}

    def one(i):
        ip = '%s.%d' % (base, i)
        text = run_cmd(['ping', '-n', '1', '-w', '500', '-l', '1', ip], 2)
        m = re.search(r'TTL[=:：]\s*(\d+)', text, re.I)
        return (ip, int(m.group(1))) if m else None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(one, range(1, 255)):
            if r:
                result[r[0]] = r[1]
    return result


def arp_table():
    """解析系统 ARP 缓存 {ip: mac}（ping 扫描后缓存最全）。"""
    table = {}
    for ln in run_cmd(['arp', '-a'], 5).splitlines():
        m = re.match(r'\s*(\d+\.\d+\.\d+\.\d+)\s+((?:[0-9a-f]{2}-){5}[0-9a-f]{2})\s', ln, re.I)
        if m:
            table[m.group(1)] = m.group(2).lower()
    return table


def probe_ports(ip, timeout=0.4):
    """并发 TCP 探测特征端口，返回开放端口列表。"""
    def one(p):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((ip, p))
            return p
        except OSError:
            return None
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=len(SCAN_PORTS)) as ex:
        return [r for r in ex.map(one, SCAN_PORTS) if r]


def http_title(ip, port):
    """读取管理页 / 打印机 Web 标题（设备身份线索）。"""
    try:
        s = socket.create_connection((ip, port), timeout=1.0)
        s.settimeout(1.2)
        s.sendall(('GET / HTTP/1.0\r\nHost: %s\r\nUser-Agent: CyberNWT-NetSense/1.0\r\n\r\n' % ip).encode())
        buf = b''
        while len(buf) < 4096:
            chunk = s.recv(1024)
            if not chunk:
                break
            buf += chunk
        s.close()
        m = re.search(r'<title[^>]*>([^<]{1,80})</title>', buf.decode('utf-8', 'replace'), re.I)
        return m.group(1).strip() if m else ''
    except OSError:
        return ''


def reverse_names(ips, budget=4.0):
    """并发反查主机名（Windows 走 NBNS/DNS，主机与打印机常可解析）。
    有严格时间预算：卡住的解析线程不阻塞主流程。"""
    names = {}

    def one(ip):
        try:
            return ip, socket.gethostbyaddr(ip)[0]
        except Exception:
            return None

    ex = ThreadPoolExecutor(max_workers=48)
    try:
        futs = [ex.submit(one, ip) for ip in ips]
        deadline = time.time() + budget
        for f in futs:
            if time.time() > deadline:
                break
            try:
                r = f.result(timeout=max(0.05, deadline - time.time()))
                if r:
                    names[r[0]] = r[1]
            except Exception:
                pass
    finally:
        ex.shutdown(wait=False)
    return names


def ssdp_discover(budget=2.5):
    """SSDP M-SEARCH：UPnP 设备发现（路由器/打印机/NAS 常响应，含自报身份）。"""
    found = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        msg = (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
               b'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n')
        sock.sendto(msg, ('239.255.255.250', 1900))
        sock.settimeout(0.3)
        t0 = time.time()
        while time.time() - t0 < budget:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            text = data.decode('utf-8', 'replace')
            m = re.search(r'LOCATION:\s*http://(\d+\.\d+\.\d+\.\d+)', text, re.I)
            srv = re.search(r'SERVER:\s*(.+)', text, re.I)
            if m:
                ip = m.group(1)
                cur = found.get(ip, '')
                if srv and len(srv.group(1).strip()) > len(cur):
                    found[ip] = srv.group(1).strip()
        sock.close()
    except OSError:
        pass
    return found


def classify_device(dev, wifi_bssid):
    """多指纹分类（优先级从高到低）：BSSID 实测 > 打印端口 > OUI 厂商 > 管理端口 > TTL。"""
    ports = set(dev['ports'])
    vendor, kind = oui_lookup(dev.get('mac', ''))
    ttl = dev.get('ttl', 0)
    if wifi_bssid and norm_mac(dev.get('mac')) == wifi_bssid:
        return 'ap', '实测·Wi-Fi BSSID', vendor or '—'
    if ports & PRINTER_PORTS:
        hit = sorted(ports & PRINTER_PORTS)[0]
        return 'printer', '实测·打印端口 %d' % hit, vendor or '—'
    if kind == 'printer':
        return 'printer', '实测·OUI 厂商指纹', vendor
    if kind == 'net' and (ports & NETMGMT_PORTS):
        return 'switch', '实测·OUI+管理端口', vendor
    if kind == 'net':
        return ('ap' if 80 in ports else 'switch'), '实测·OUI+端口', vendor
    if ports & PC_PORTS:
        return 'client', '实测·SMB/RPC 端口', vendor or '—'
    if ttl >= 120:
        return 'client', '实测·ICMP(TTL=%d)' % ttl, vendor or '—'
    if 80 in ports or 443 in ports:
        return 'server', '实测·Web 服务', vendor or '—'
    return 'client', '实测·ICMP 存活', vendor or '—'


def _dev_label(dev):
    """设备显示名：主机名 / Web 标题 / 厂商+角色，取最有识别度的一个。"""
    if dev['role'] == 'printer' and dev.get('title'):
        return dev['title'][:24]
    if dev.get('hostname'):
        return dev['hostname'].split('.')[0][:24]
    role_names = {'gateway': '网关/路由', 'switch': '交换机', 'ap': '无线 AP',
                  'printer': '打印机', 'server': '服务器', 'client': '网络终端'}
    v = dev.get('vendor')
    label = '%s %s' % (v if v and v != '—' else '', role_names.get(dev['role'], '设备'))
    return label.strip()


def build_real_network(real):
    """真实感知主流程：ICMP 扫描 → ARP → 端口/HTTP/主机名指纹 → 分类 → 实测拓扑。"""
    base = real['ip'].rsplit('.', 1)[0]
    wifi = wifi_link_info()
    wifi_bssid = norm_mac(wifi.get('bssid'))
    gw_ip = real['gateway']

    # 1) 并行：ICMP 全网段扫描 + SSDP 发现
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_ping = ex.submit(ping_sweep, base)
        f_ssdp = ex.submit(ssdp_discover)
        live = f_ping.result()
        ssdp = f_ssdp.result()
    # 2) ARP 表（扫描后缓存最全）
    macs = arp_table()
    # 3) 存活设备逐台指纹（端口 + Web 标题）
    devs = [{'ip': ip, 'ttl': ttl, 'mac': macs.get(ip, ''), 'ports': [], 'title': '',
             'hostname': '', 'ssdp': ssdp.get(ip, '')} for ip, ttl in live.items()]

    def fingerprint(d):
        d['ports'] = probe_ports(d['ip'])
        web_port = 80 if 80 in d['ports'] else (443 if 443 in d['ports'] else 0)
        if web_port:
            d['title'] = http_title(d['ip'], web_port)
        return d

    with ThreadPoolExecutor(max_workers=24) as ex:
        devs = list(ex.map(fingerprint, devs))
    # 4) 主机名反查
    names = reverse_names([d['ip'] for d in devs])
    for d in devs:
        d['hostname'] = names.get(d['ip'], '')

    # 5) 分类（排除本机；网关单独标注）
    classified = []
    for d in devs:
        if d['ip'] == real['ip']:
            continue
        if d['ip'] == gw_ip:
            d['role'], d['conf'] = 'gateway', '实测·ARP 网关+ICMP'
            d['vendor'] = oui_lookup(d['mac'])[0] or '—'
        else:
            d['role'], d['conf'], d['vendor'] = classify_device(d, wifi_bssid)
        classified.append(d)

    switches = [d for d in classified if d['role'] == 'switch']
    aps = [d for d in classified if d['role'] == 'ap']
    printers = [d for d in classified if d['role'] == 'printer']
    servers = [d for d in classified if d['role'] == 'server']
    clients = [d for d in classified if d['role'] == 'client']

    # 6) 组装拓扑：互联网 → 网关 → (核心/接入交换机) → AP/打印机/服务器/终端
    nodes = [{'id': 'net', 'tier': 0, 'icon': '☁️', 'name': '互联网', 'role': 'isp', 'ip': '', 'conf': '—'}]
    links = []
    nodes.append({'id': 'gw', 'tier': 1, 'icon': '🔗', 'name': '出口网关（实测）', 'role': 'gateway',
                  'ip': gw_ip, 'vendor': next(d['vendor'] for d in classified if d['role'] == 'gateway'),
                  'conf': '实测·ARP 网关+ICMP'})
    uplink_id = 'gw'

    if switches:
        core = switches[0]
        nodes.append({'id': 'core', 'tier': 2, 'icon': '🔀', 'name': _dev_label(core) or '交换机',
                      'role': 'core', 'ip': core['ip'], 'vendor': core['vendor'], 'conf': core['conf']})
        links.append({'from': 'gw', 'to': 'core', 'label': 'Trunk', 'kind': 'trunk'})
        uplink_id = 'core'
        for i, d in enumerate(switches[1:]):
            nid = 'acc%d' % (i + 1)
            nodes.append({'id': nid, 'tier': 3, 'icon': '🔀', 'name': _dev_label(d) or ('交换机 %d' % (i + 1)),
                          'role': 'access', 'ip': d['ip'], 'vendor': d['vendor'], 'conf': d['conf']})
            links.append({'from': 'core', 'to': nid, 'label': '级联', 'kind': 'trunk'})
            uplink_id = nid

    for i, d in enumerate(aps):
        nid = 'ap%d' % (i + 1)
        nm = wifi.get('ssid') if wifi_bssid and norm_mac(d['mac']) == wifi_bssid else None
        nodes.append({'id': nid, 'tier': 3, 'icon': '📶',
                      'name': ('AP · %s' % nm) if nm else (_dev_label(d) or ('AP-%02d' % (i + 1))),
                      'role': 'ap', 'ip': d['ip'], 'vendor': d['vendor'], 'conf': d['conf']})
        links.append({'from': uplink_id, 'to': nid, 'label': 'PoE/有线', 'kind': 'access'})
    for i, d in enumerate(printers):
        nid = 'prt%d' % (i + 1)
        nodes.append({'id': nid, 'tier': 4, 'icon': '🖨️', 'name': _dev_label(d) or ('打印机 %d' % (i + 1)),
                      'role': 'printer', 'ip': d['ip'], 'vendor': d['vendor'], 'conf': d['conf']})
        links.append({'from': uplink_id, 'to': nid, 'label': 'Access', 'kind': 'access'})
    for i, d in enumerate(servers):
        nid = 'srv%d' % (i + 1)
        nodes.append({'id': nid, 'tier': 4, 'icon': '🗄️', 'name': _dev_label(d) or ('服务器 %d' % (i + 1)),
                      'role': 'server', 'ip': d['ip'], 'vendor': d['vendor'], 'conf': d['conf']})
        links.append({'from': uplink_id, 'to': nid, 'label': 'Access', 'kind': 'access'})

    if clients:
        nodes.append({'id': 'pcs', 'tier': 4, 'icon': '💻', 'name': '在线终端 ×%d' % len(clients),
                      'role': 'clients', 'ip': base + '.0/24', 'conf': '实测·ICMP 存活 %d 台' % len(clients)})
        links.append({'from': uplink_id, 'to': 'pcs',
                      'label': real['conn_type'] == 'wifi' and 'Wi-Fi' or 'Access',
                      'kind': 'wireless' if real['conn_type'] == 'wifi' else 'access'})

    nodes.append({'id': 'me', 'tier': 4, 'icon': '🧑‍🔧', 'name': '工程师本机（实测）', 'role': 'self',
                  'ip': real['ip'], 'conf': '实测·本机网卡'})
    parent = next(('ap%d' % (aps.index(d) + 1) for d in aps if wifi_bssid and norm_mac(d['mac']) == wifi_bssid), uplink_id)
    links.append({'from': parent, 'to': 'me',
                  'label': wifi.get('ssid') if real['conn_type'] == 'wifi' and wifi.get('ssid') else ('Wi-Fi' if real['conn_type'] == 'wifi' else '有线'),
                  'kind': 'wireless' if real['conn_type'] == 'wifi' else 'access'})

    subnets = [{'cidr': base + '.0/24', 'vlan': '—', 'name': '现场实测网段', 'gateway': gw_ip,
                'hosts': len(live), 'dhcp': bool(real.get('dhcp'))}]
    if wifi.get('ssid') and real['conn_type'] == 'wifi':
        subnets[0]['wifi'] = {'ssid': wifi['ssid'], 'signal': wifi.get('signal', 0)}

    hosts = []
    for d in clients:
        hosts.append({'ip': d['ip'], 'type': d['hostname'].split('.')[0][:20] if d['hostname'] else '网络终端',
                      'vendor': d['vendor'], 'conf': d['conf']})

    scn = {'has_ac': len(aps) >= 2, 'has_core': bool(switches), 'multi_subnet': False,
           'flat': True, 'me_wifi': real['conn_type'] == 'wifi'}
    return {'nodes': nodes, 'links': links, 'subnets': subnets, 'hosts': hosts, 'scenario': scn,
            'scan_stats': {'alive': len(live), 'with_mac': len(macs), 'ssdp_hits': len(ssdp)}}


def build_deployment_advice(real, net):
    """根据感知到的环境生成深信服设备部署模式建议（规则引擎）。"""
    scn = net['scenario']
    aps = [n for n in net['nodes'] if n['role'] == 'ap']
    if aps:
        ap_vendors = '/'.join(sorted({n.get('vendor') or '未知' for n in aps}))
        ac_note = ('现场实测发现 %d 台 AP（%s）。若为瘦 AP 架构需先确认 AC 位置与 CAPWAP 链路；'
                   '新增无线设备时保持管理 VLAN 与业务 VLAN 分离规划。' % (len(aps), ap_vendors))
    else:
        ac_note = '现场未实测发现无线 AP，如需新增 AC 建议与 AF 同步规划管理地址。'
    if scn['flat']:
        mode, alt = '网桥（透明串接）模式', '路由模式'
        reasons = [
            '现场为单网段平面网络（网关 %s），终端无需变更网关即可生效' % real['gateway'],
            '透明串接不改变现有 IP/路由规划，割接窗口最短、回退只需拔线',
            '如后续需要 NAT/多线路等能力，可原地切换为路由模式',
        ]
        planning = ['AF 接口：LAN 口接核心/接入交换，WAN 口接出口网关',
                    '管理地址：在办公网段预留一个固定 IP（建议 .253 之前确认未占用）',
                    'Interface 走线：先桥接旁路观察 24h 流量，再正式串接']
    else:
        mode, alt = '旁路部署（旁挂核心交换）', '路由模式串接'
        reasons = [
            '现场为多网段环境（检测到 %d 个网段），核心交换机具备旁挂条件' % len(net['subnets']),
            '旁挂核心不改变现有流量路径，通过策略路由/静态路由引流，业务零中断',
            '割接风险低：引流异常时删除引流策略即可秒级回退',
        ]
        planning = ['AF 旁路口接核心交换机（建议万兆口），划分独立互联 VLAN',
                    '核心上配置策略路由：办公/访客网段流量转发至 AF 互联地址',
                    'AF 回程路由指向核心，服务器网段按需 NAT 或策略放行',
                    '管理网（VLAN 99）单独放行 AF 管理地址']
    risks = [
        '实施前必须备份：出口设备与核心交换机配置各导出一份',
        '确认网关 %s 的会话/ARP 表在割接后正常收敛（观察 30 分钟）' % real['gateway'],
        '客户内网存在未登记设备，策略放行遵循"先观察后收紧"原则',
    ]
    checklist = ['确认本次上架设备的型号、授权与版本基线', '与客户确认变更窗口和回退责任人',
                 '梳理接口/VLAN 互联表并双方签字确认', '准备 Console 线与带外管理通道',
                 '割接后按清单逐项验证业务（办公/服务器/访客/无线）']
    return {'mode': mode, 'alternative': alt, 'reasons': reasons, 'planning': planning,
            'risks': risks, 'checklist': checklist, 'wireless_note': ac_note,
            'me_access': '当前通过 Wi-Fi 接入现场网络，拓扑感知与配置验证均可无线完成；正式串接割接建议临时接有线到待配设备管理口。'
            if scn['me_wifi'] else '当前为有线接入，可直接连通待配设备管理口。'}


def init_db():
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash  TEXT NOT NULL,
            salt     TEXT NOT NULL,
            created_at REAL NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sessions(
            token    TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expires  REAL NOT NULL)''')
        if conn.execute('SELECT id FROM users WHERE username=?', ('admin',)).fetchone() is None:
            add_user('admin', 'admin')
            print('[init] seeded default account: admin / admin')


# ---------------- 请求处理 ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = 'CyberNWT/1.0'

    # ---- 输出辅助 ----

    def send_json(self, obj, code=200, set_cookie=None):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filename, code=200):
        path = os.path.realpath(os.path.join(ROOT, filename))
        if not path.startswith(ROOT) or not os.path.isfile(path):
            return self.send_error(404)
        ext = os.path.splitext(path)[1].lower()
        with open(path, 'rb') as f:
            body = f.read()
        self.send_response(code)
        self.send_header('Content-Type', CONTENT_TYPES.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.end_headers()

    # ---- 输入辅助 ----

    def read_json(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(length) if length > 0 else b''
        try:
            data = json.loads(raw.decode('utf-8'))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_cookie(self, name):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        return cookie[name].value if name in cookie else None

    def current_user(self):
        return session_user(self.get_cookie('sid'))

    @staticmethod
    def session_cookie(token):
        return f'sid={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={int(SESSION_TTL)}'

    # ---- 路由 ----

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/me':
            user = self.current_user()
            if user:
                self.send_json({'ok': True, 'username': user})
            else:
                self.send_json({'ok': False, 'message': '未登录'}, 401)
        elif path == '/':
            if self.current_user():
                self.redirect('/home.html')
            else:
                self.send_file('login.html')
        elif path == '/login.html':
            self.send_file('login.html')
        elif path == '/home.html':
            if not self.current_user():
                self.redirect('/')
            else:
                self.send_file('home.html')
        elif path == '/api/topology/scan':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            real = read_local_nic()
            if not real or not real.get('gateway'):
                return self.send_json(
                    {'ok': False, 'message': '未能读取本机网卡信息（未联网或非 Windows 环境）'}, 503)
            net = build_real_network(real)
            advice = build_deployment_advice(real, net)
            real['prefix'] = mask_to_prefix(real['mask'])
            self.send_json({'ok': True, 'real': real, 'topology': net,
                            'advice': advice, 'modeled': False,
                            'engine': 'ICMP+ARP+OUI+Port+BSSID'})
        elif path in ('/speedtest.html', '/diagnose.html', '/review.html', '/topology.html'):
            if not self.current_user():
                self.redirect('/')
            else:
                self.send_file(path.lstrip('/'))
        elif path == '/api/speedtest/echo':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.send_json({'t': time.time(), 'ip': self.client_address[0]})
        elif path == '/api/speedtest/geo':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_geo()
        elif path == '/api/speedtest/upnodes':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_upnodes()
        elif path == '/peer/info':
            self.handle_peer_info()
        elif path == '/peer/down':
            self.handle_peer_down(urllib.parse.urlparse(self.path).query)
        elif path == '/api/speedtest/down':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                n = min(max(int(q.get('bytes', ['4194304'])[0]), 1024), 64 * 1024 * 1024)
            except ValueError:
                n = 4 * 1024 * 1024
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(n))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            sent = 0
            while sent < n:
                part = min(len(_SPEED_CHUNK), n - sent)
                self.wfile.write(_SPEED_CHUNK[:part])
                sent += part
        else:
            self.serve_static(path)

    def serve_static(self, path):
        name = path.lstrip('/')
        if not name:
            return self.send_error(404)
        ext = os.path.splitext(name)[1].lower()
        if ext not in CONTENT_TYPES:
            return self.send_error(404)
        real = os.path.realpath(os.path.join(ROOT, name))
        if not real.startswith(ROOT) or not os.path.isfile(real):
            return self.send_error(404)
        with open(real, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', CONTENT_TYPES[ext])
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_speed_up(self):
        """测速上传接口：请求体为二进制数据，只统计字节数不落盘。"""
        if not self.current_user():
            return self.send_json({'ok': False, 'message': '未登录'}, 401)
        length = int(self.headers.get('Content-Length', 0) or 0)
        received = 0
        while received < length:
            block = self.rfile.read(min(65536, length - received))
            if not block:
                break
            received += len(block)
        self.send_json({'ok': True, 'bytes': received})

    # ---------------- 灵犀测速：定位 / 内网对端协议 ----------------

    def handle_speed_geo(self):
        """服务端多源定位：返回出口 IP / 省市 / 运营商（全部国内源）。"""
        ip = pro = city = isp = ''
        for url in SPEED_GEO_APIS:
            try:
                req = urllib.request.Request(url, headers=GEO_HEADERS)
                with urllib.request.urlopen(req, timeout=4) as r:
                    raw = r.read().decode('utf-8', errors='replace')
                if 'ip2city' in url:
                    data = json.loads(raw)
                    if data.get('ret') == 0:
                        ip = str(data.get('ip', ''))
                        pro = str(data.get('province', ''))
                        city = str(data.get('city', ''))
                else:
                    m = re.search(r'IP[:：]\s*([0-9.]+)', raw)
                    if m:
                        ip = m.group(1)
                        seg = raw.split('来自于：')[-1].split()
                        if len(seg) >= 4:
                            pro, city, isp = seg[1], seg[2], seg[-1]
                        elif len(seg) == 3:
                            pro, isp = seg[1], seg[-1]
                if ip:
                    if not isp:
                        try:
                            isp = _geo_baidu_isp(ip)
                        except Exception:
                            isp = ''
                    return self.send_json({'ok': True, 'ip': ip,
                                           'region': (pro + ' · ' + city).strip(' ·'), 'isp': isp})
            except Exception:
                continue
        return self.send_json({'ok': False, 'message': '定位服务不可用'}, 502)

    def handle_speed_upnodes(self):
        """返回大陆全部公开 Ookla 上行测速节点（前端按可达性实测后分片并发）。"""
        try:
            nodes = ookla_cn_nodes()
        except Exception:
            nodes = []
        if nodes:
            return self.send_json({'ok': True, 'count': len(nodes), 'nodes': nodes})
        return self.send_json({'ok': False, 'message': '大陆 Ookla 节点清单获取失败'}, 502)

    def _peer_cors(self):
        """内网对端协议 CORS：允许局域网内任意浏览器直连本机测速。"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def handle_peer_info(self):
        body = json.dumps({'ok': True, 'host': socket.gethostname(),
                           'system': sys.platform, 'time': time.time()}).encode()
        self.send_response(200)
        self._peer_cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_peer_ping(self):
        self.send_response(204)
        self._peer_cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def handle_peer_down(self, query):
        """对端下行：流式吐出 N 字节随机数据（与 speedpeer.py 同协议）。"""
        q = urllib.parse.parse_qs(query)
        try:
            n = max(1024, min(int(q.get('bytes', ['8388608'])[0]), 2 * 1024 * 1024 * 1024))
        except ValueError:
            n = 8388608
        self.send_response(200)
        self._peer_cors()
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(n))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        sent = 0
        try:
            while sent < n:
                part = min(len(_SPEED_CHUNK), n - sent)
                self.wfile.write(_SPEED_CHUNK[:part])
                sent += part
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # 浏览器测完提前断开，正常节奏

    def handle_peer_up(self):
        """对端上行：读取并丢弃请求体，返回收到的字节数。"""
        length = int(self.headers.get('Content-Length', 0) or 0)
        received = 0
        try:
            while received < length:
                block = self.rfile.read(min(262144, length - received))
                if not block:
                    break
                received += len(block)
        except (ConnectionResetError, ConnectionAbortedError):
            pass
        body = json.dumps({'ok': True, 'bytes': received}).encode()
        self.send_response(200)
        self._peer_cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/peer/ping':
            return self.handle_peer_ping()
        self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self._peer_cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/speedtest/up':
            return self.handle_speed_up()   # 二进制请求体，不能走 JSON 解析
        if path == '/peer/up':
            return self.handle_peer_up()     # 内网对端协议：二进制请求体
        data = self.read_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))

        if path == '/api/register':
            if not re.fullmatch(r'\w{2,20}', username, re.UNICODE):
                return self.send_json(
                    {'ok': False, 'message': '账号需为 2-20 位字母、数字、下划线或中文'}, 400)
            if not (6 <= len(password) <= 64):
                return self.send_json({'ok': False, 'message': '密码长度需为 6-64 位'}, 400)
            try:
                add_user(username, password)
            except sqlite3.IntegrityError:
                return self.send_json({'ok': False, 'message': '该账号已被注册'}, 409)
            return self.send_json({'ok': True, 'message': '注册成功'})

        if path == '/api/login':
            if not username or not password:
                return self.send_json({'ok': False, 'message': '请输入账号和密码'}, 400)
            if verify_user(username, password):
                token = create_session(username)
                return self.send_json({'ok': True, 'username': username},
                                      set_cookie=self.session_cookie(token))
            return self.send_json({'ok': False, 'message': '账号或密码错误'}, 401)

        if path == '/api/logout':
            drop_session(self.get_cookie('sid'))
            return self.send_json({'ok': True},
                                  set_cookie='sid=; Path=/; HttpOnly; Max-Age=0')

        if path in ('/api/ai/chat', '/api/ai/report'):
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            scene = 'review' if path.endswith('report') else 'diagnose'
            messages = []
            for m in (data.get('messages') or []):
                if not (isinstance(m, dict) and m.get('content')):
                    continue
                role = str(m.get('role', 'user'))[:10]
                c = m.get('content')
                if isinstance(c, list):
                    # 多模态消息：文本 + 图片（dataURL），过滤异常部分
                    parts, n_img = [], 0
                    for p in c:
                        if not isinstance(p, dict):
                            continue
                        if p.get('type') == 'text' and str(p.get('text', '')).strip():
                            parts.append({'type': 'text', 'text': str(p['text'])[:8000]})
                        elif p.get('type') == 'image_url' and n_img < 3:
                            url = str((p.get('image_url') or {}).get('url', ''))
                            if url.startswith('data:image/') and len(url) <= 6000000:
                                parts.append({'type': 'image_url', 'image_url': {'url': url}})
                                n_img += 1
                    if not parts:
                        continue
                    c = parts[0]['text'] if len(parts) == 1 and parts[0]['type'] == 'text' else parts
                else:
                    c = str(c)[:8000]
                messages.append({'role': role, 'content': c})
            if not messages:
                return self.send_json({'ok': False, 'message': '缺少对话内容'}, 400)
            reply, source = ai_chat(messages, scene)
            if reply is None:
                source = 'demo'
                last_txt = _msg_text(messages[-1]['content'])
                reply = demo_review(last_txt) if scene == 'review' else demo_diagnose(last_txt)
            return self.send_json({'ok': True, 'reply': reply, 'source': source})

        self.send_json({'ok': False, 'message': '未知接口'}, 404)

    def log_message(self, fmt, *args):
        print('[%s] %s' % (time.strftime('%H:%M:%S'), fmt % args))


def port_in_use(port):
    """Windows 下 SO_REUSEADDR 允许新旧进程同时监听同一端口，旧实例会抢走连接
    导致浏览器 ERR_EMPTY_RESPONSE，必须在启动前显式探测。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def lan_ip():
    """取本机局域网 IP，用于提示内网测速入口地址。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('223.5.5.5', 80))
            return s.getsockname()[0]
    except OSError:
        return ''


def main():
    if port_in_use(PORT):
        print(f'[error] 端口 {PORT} 已被占用：可能有一个旧的 server.py 还在运行。')
        print('[提示] 解决方法（任选其一）：')
        print('       1. 任务管理器 -> 结束旧的 python 进程后重试')
        print(f'       2. 换端口启动：py server.py 8643')
        try:
            input('\n按回车键关闭本窗口…')
        except EOFError:
            pass
        sys.exit(1)
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    server.daemon_threads = True
    print(f'[ok] CyberNWT 已启动: http://127.0.0.1:{PORT}   (演示账号 admin / admin, Ctrl+C 停止)')
    threading.Thread(target=ookla_cn_nodes, daemon=True,
                    name='ookla-warmup').start()
    ip = lan_ip()
    if ip:
        print(f'[ok] 内网测速入口: http://{ip}:{PORT}/speedtest.html  '
              f'（同一内网的其他终端打开此地址，登录后选择「内网测速」）')
        print(f'[ok] 深度内网测速: 在目标机器上运行  py speedpeer.py --host 0.0.0.0  '
              f'（默认端口 {PEER_DEFAULT_PORT}），测速页填入其 IP:端口 即可')
    threading.Timer(0.8, lambda: webbrowser.open(f'http://127.0.0.1:{PORT}/login.html')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[bye] server stopped')


if __name__ == '__main__':
    main()
