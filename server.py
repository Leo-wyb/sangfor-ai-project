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
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zlib
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

# FastGPT 外接配置（可选）：设置环境变量后，AI 功能自动从演示回复切换为真实大模型
#   FASTGPT_BASE  例如 https://your-fastgpt.example.com/api/v1 （OpenAI 兼容 /chat/completions）
#   FASTGPT_KEY   FastGPT 的 API Key
FASTGPT_BASE = os.environ.get('FASTGPT_BASE', '').rstrip('/')
FASTGPT_KEY = os.environ.get('FASTGPT_KEY', '')
FASTGPT_TIMEOUT = float(os.environ.get('FASTGPT_TIMEOUT', '60'))

# 测速下行缓冲：预生成 4MB 随机数据，避免测试时临时生成拖慢吞吐
_SPEED_CHUNK = os.urandom(4 * 1024 * 1024)

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

def fastgpt_chat(messages):
    """转发到 FastGPT（OpenAI 兼容协议）。未配置或失败时返回 None，由调用方回退演示回复。"""
    if not FASTGPT_BASE:
        return None
    req = urllib.request.Request(
        FASTGPT_BASE + '/chat/completions',
        data=json.dumps({'messages': messages, 'stream': False}).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + FASTGPT_KEY})
    try:
        with urllib.request.urlopen(req, timeout=FASTGPT_TIMEOUT) as r:
            data = json.loads(r.read().decode('utf-8'))
        return data['choices'][0]['message']['content']
    except Exception as e:
        print('[ai] FastGPT 调用失败: %r' % e)
        return None


_DEMO_STEPS = {
    '上架': ['核对设备型号、S/N 与到货清单，确认电源/风扇/光模块齐备',
            '机柜固定并规范接地，检查供电电压后加电，观察 STAT/ALARM 指示灯',
            'Console 或管理口登录，核对系统版本、授权与硬盘 RAID 状态',
            '按拓扑预配置管理地址与路由，先跑基线再接入业务'],
    '割接': ['割接前：导出并备份新旧设备配置，梳理接口/VLAN/路由/策略映射表',
            '明确回退点与回退负责人，准备串接旁路/回退命令清单',
            '割接中：按“先旁路、后串接”顺序切换，逐段验证业务连通与会话保持',
            '割接后：持续观察 30 分钟流量曲线与安全日志，确认无异常再收尾'],
    'vpn': ['确认两端协商阶段：IKE 提议（加密/认证算法、DH 组）是否一致',
            '检查第二阶段感兴趣流（Proxy ID/保护网段）是否完全镜像',
            '排查 NAT 环境下的 NAT-T 与 UDP 4500 端口放行情况',
            '抓包查看 ISAKMP/IPSec 报文定位卡在哪个阶段'],
    '丢包': ['先分段定位：终端—网关—出口—对端逐跳 ping 结合大包测试',
            '查看接口错包/CRC 计数与光衰，排除物理层问题',
            '确认是否命中限速/流控策略或会话数达到上限',
            '在路径关键节点抓包对比，确定丢包发生段'],
}


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
    """真实读取本机网卡信息（Windows: ipconfig /all）。
    这是浏览器环境之外、本地服务器唯一可靠获得的'实测'网络事实。"""
    try:
        raw = subprocess.run(['ipconfig', '/all'], capture_output=True, timeout=5).stdout
        text = raw.decode('gbk', 'replace')
    except Exception:
        try:
            text = subprocess.run(['ipconfig', '/all'], capture_output=True,
                                  timeout=5, text=True).stdout or ''
        except Exception:
            return None

    def pick(block, key):
        for ln in block:
            if key in ln and ':' in ln:
                return ln.split(':', 1)[1].strip().rstrip(',').strip()
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
        if b and '主机名' in b[0]:
            hostname = pick(b, '主机名') or hostname

    best = None
    for b in blocks:
        head = b[0] if b else ''
        if '适配器' not in head:
            continue
        ip = pick(b, 'IPv4 地址')
        gw = pick(b, '默认网关')
        if not ip or not gw:
            continue
        name = head.split('适配器', 1)[1].strip().rstrip(':')
        desc = pick(b, '描述') or ''
        is_wifi = any(k in (name + desc).upper() for k in ('WLAN', '无线', 'WI-FI', 'WIFI', '802.11', 'WIRELESS'))

        def ipv4(s):
            m = re.search(r'\d+\.\d+\.\d+\.\d+', s or '')
            return m.group(0) if m else ''
        best = {
            'adapter': name, 'desc': desc, 'conn_type': 'wifi' if is_wifi else 'ethernet',
            'ip': ipv4(pick(b, 'IPv4 地址')), 'mask': ipv4(pick(b, '子网掩码')) or '255.255.255.0',
            'gateway': ipv4(pick(b, '默认网关')), 'mac': pick(b, '物理地址') or '',
            'dhcp': (pick(b, 'DHCP 已启用') or '').lower().startswith('是'),
            'dns': ipv4(pick(b, 'DNS 服务器')), 'hostname': hostname,
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


def build_modeled_network(real):
    """基于真实网关/网段，建模生成客户内网拓扑与设备清单。
    【如实标注】浏览器演示环境无法对客户内网做 ARP/SNMP 主动探测，
    除本机网卡事实外的设备均为建模数据；真实部署时由此处接入探针引擎。"""
    # 以网关地址为确定性种子：同一线现场重复感知结果保持一致
    seed = zlib.crc32(real['gateway'].encode('utf-8'))
    rng = random.Random(seed)
    ip3 = real['ip'].split('.')[:3]
    base = '.'.join(ip3)
    big = rng.random() < 0.5          # 中大型网络：多网段
    wireless = rng.random() < 0.65    # 存在无线 AC/AP
    srv_v = '192.168.%d' % rng.randint(2, 60)
    mgmt_v = '10.0.99'

    nodes = [
        {'id': 'net', 'tier': 0, 'icon': '☁️', 'name': '互联网', 'role': 'isp', 'ip': '', 'conf': '—'},
        {'id': 'gw', 'tier': 1, 'icon': '🔗', 'name': '出口网关/路由', 'role': 'gateway',
         'ip': real['gateway'], 'vendor': rng.choice(['华为', 'H3C', '思科', '锐捷']), 'conf': '高（实测网关）'},
        {'id': 'core', 'tier': 2, 'icon': '🔀', 'name': '核心交换机', 'role': 'core',
         'ip': base + '.253', 'vendor': rng.choice(['华为', 'H3C', '锐捷']), 'conf': '建模'},
    ]
    links = [
        {'from': 'net', 'to': 'gw', 'label': '出口链路', 'kind': 'uplink'},
        {'from': 'gw', 'to': 'core', 'label': 'Trunk', 'kind': 'trunk'},
    ]

    acc = []
    for i in range(rng.randint(1, 2)):
        nid = 'acc%d' % (i + 1)
        acc.append(nid)
        nodes.append({'id': nid, 'tier': 3, 'icon': '🔀', 'name': '接入交换机 %02d' % (i + 1), 'role': 'access',
                      'ip': base + '.25%d' % (2 - i), 'vendor': rng.choice(['华为', 'H3C', 'TP-LINK']), 'conf': '建模'})
        links.append({'from': 'core', 'to': nid, 'label': 'Trunk', 'kind': 'trunk'})

    if wireless:
        ac_vendor = rng.choice(['深信服', '华为', '锐捷'])
        nodes.append({'id': 'ac', 'tier': 3, 'icon': '📡', 'name': '无线控制器 AC', 'role': 'ac',
                      'ip': srv_v + '.10', 'vendor': ac_vendor, 'conf': '建模'})
        links.append({'from': 'core', 'to': 'ac', 'label': '旁挂', 'kind': 'access'})
        for i in range(rng.randint(2, 3)):
            nodes.append({'id': 'ap%d' % (i + 1), 'tier': 4, 'icon': '📶', 'name': 'AP-%02d' % (i + 1),
                          'role': 'ap', 'ip': base + '.1%d0' % i, 'vendor': ac_vendor, 'conf': '建模'})
            links.append({'from': 'ac', 'to': 'ap%d' % (i + 1), 'label': 'CAPWAP', 'kind': 'wireless'})

    n_srv = rng.randint(1, 3)
    nodes.append({'id': 'srvsw', 'tier': 3, 'icon': '🔀', 'name': '服务器区交换', 'role': 'server-sw',
                  'ip': srv_v + '.254', 'vendor': rng.choice(['华为', 'H3C']), 'conf': '建模'})
    links.append({'from': 'core', 'to': 'srvsw', 'label': 'Trunk', 'kind': 'trunk'})
    srv_names = ['业务服务器', '文件/存储服务器', 'OA 应用服务器']
    for i in range(n_srv):
        nodes.append({'id': 'srv%d' % (i + 1), 'tier': 4, 'icon': '🗄️', 'name': srv_names[i % len(srv_names)],
                      'role': 'server', 'ip': srv_v + '.%d' % (11 + i), 'conf': '建模'})
        links.append({'from': 'srvsw', 'to': 'srv%d' % (i + 1), 'label': 'Access', 'kind': 'access'})

    nodes.append({'id': 'pc', 'tier': 4, 'icon': '💻', 'name': '办公终端区 ×%d' % rng.randint(12, 60),
                  'role': 'clients', 'ip': base + '.0/24', 'conf': '建模'})
    links.append({'from': acc[0], 'to': 'pc', 'label': 'Access', 'kind': 'access'})
    if rng.random() < 0.6:
        nodes.append({'id': 'prt', 'tier': 4, 'icon': '🖨️', 'name': '打印机/共享设备', 'role': 'printer',
                      'ip': base + '.%d' % rng.randint(100, 200), 'conf': '建模'})
        links.append({'from': acc[-1], 'to': 'prt', 'label': 'Access', 'kind': 'access'})
    nodes.append({'id': 'me', 'tier': 4, 'icon': '🧑‍🔧', 'name': '工程师本机（实测）', 'role': 'self',
                  'ip': real['ip'], 'conf': '高（实测）'})
    links.append({'from': acc[0], 'to': 'me', 'label': real['conn_type'] == 'wifi' and 'Wi-Fi' or '有线', 'kind': 'wireless' if real['conn_type'] == 'wifi' else 'access'})

    subnets = [{'cidr': base + '.0/24', 'vlan': '1（默认）', 'name': '办公终端网', 'gateway': real['gateway'],
                'hosts': rng.randint(12, 60), 'dhcp': True},
               {'cidr': srv_v + '.0/24', 'vlan': '20', 'name': '服务器网', 'gateway': srv_v + '.254',
                'hosts': n_srv + 1, 'dhcp': False}]
    if big:
        subnets.insert(1, {'cidr': '192.168.%d.0/24' % rng.randint(61, 200), 'vlan': '30',
                           'name': '访客网', 'gateway': '192.168.%d.254' % rng.randint(61, 200),
                           'hosts': rng.randint(3, 20), 'dhcp': True})
    subnets.append({'cidr': mgmt_v + '.0/24', 'vlan': '99', 'name': '设备管理网', 'gateway': mgmt_v + '.254',
                    'hosts': len(acc) + 3, 'dhcp': False})

    hosts = []
    used = set()
    for n in nodes:
        if n['role'] in ('gateway', 'core', 'access', 'ac', 'ap', 'server', 'printer') and n.get('ip'):
            used.add(n['ip'])
    for i in range(6):
        ip = base + '.%d' % rng.randint(2, 250)
        while ip in used or ip.endswith('.254') or ip.endswith('.253'):
            ip = base + '.%d' % rng.randint(2, 250)
        used.add(ip)
        role = rng.choice(['办公 PC', '办公 PC', '办公 PC', '笔记本', 'IP 电话', '网络摄像头'])
        hosts.append({'ip': ip, 'type': role, 'vendor': rng.choice(['联想', 'Dell', '华为', '苹果', 'H3C']),
                      'conf': '建模'})

    scn = {'has_ac': wireless, 'has_core': True, 'multi_subnet': big, 'flat': not big, 'me_wifi': real['conn_type'] == 'wifi'}
    return {'nodes': nodes, 'links': links, 'subnets': subnets, 'hosts': hosts, 'scenario': scn}


def build_deployment_advice(real, net):
    """根据感知到的环境生成深信服设备部署模式建议（规则引擎）。"""
    scn = net['scenario']
    ac_note = ('现场存在「%s AC + AP」，新增无线相关设备时建议 AC 旁挂核心、AP 保持二层注册，'
               '管理 VLAN 与业务 VLAN 分离规划。' % (next(n['vendor'] for n in net['nodes'] if n['role'] == 'ac'),)) \
        if scn['has_ac'] else '现场未发现无线控制器，如需新增 AC 建议与 AF 同步规划管理地址。'
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
            net = build_modeled_network(real)
            advice = build_deployment_advice(real, net)
            real['prefix'] = mask_to_prefix(real['mask'])
            self.send_json({'ok': True, 'real': real, 'topology': net,
                            'advice': advice, 'modeled': True})
        elif path in ('/speedtest.html', '/diagnose.html', '/review.html', '/topology.html'):
            if not self.current_user():
                self.redirect('/')
            else:
                self.send_file(path.lstrip('/'))
        elif path == '/api/speedtest/echo':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.send_json({'t': time.time()})
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

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/speedtest/up':
            return self.handle_speed_up()   # 二进制请求体，不能走 JSON 解析
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
            messages = [{'role': str(m.get('role', 'user'))[:10],
                         'content': str(m.get('content', ''))[:8000]}
                        for m in (data.get('messages') or [])
                        if isinstance(m, dict) and m.get('content')]
            if not messages:
                return self.send_json({'ok': False, 'message': '缺少对话内容'}, 400)
            reply = fastgpt_chat(messages)
            source = 'fastgpt'
            if reply is None:
                source = 'demo'
                reply = demo_review(messages[-1]['content']) if scene == 'review' \
                    else demo_diagnose(messages[-1]['content'])
            return self.send_json({'ok': True, 'reply': reply, 'source': source})

        self.send_json({'ok': False, 'message': '未知接口'}, 404)

    def log_message(self, fmt, *args):
        print('[%s] %s' % (time.strftime('%H:%M:%S'), fmt % args))


def main():
    init_db()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    url = f'http://127.0.0.1:{PORT}'
    print(f'[ok] CyberNWT 已启动: {url}   (演示账号 admin / admin, Ctrl+C 停止)')
    threading.Timer(0.8, lambda: webbrowser.open(url + '/login.html')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[bye] server stopped')


if __name__ == '__main__':
    main()
