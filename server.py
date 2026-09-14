# -*- coding: utf-8 -*-
"""CyberNWT —— 本地演示服务器

零依赖：仅使用 Python 标准库（HTTP 服务 + SQLite 数据库）。
启动：  python server.py [端口]      （默认端口 8642，启动后自动打开浏览器）
演示账号：admin / admin
"""
import base64
import hashlib
import html
import io
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
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))  # 规范盘符大小写，避免 send_file 前缀校验误判 404
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
    def _parse_kv(raw, cfg):
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith('#') and '=' in ln:
                k, v = ln.split('=', 1)
                cfg[k.strip()] = v.strip()
        return cfg

    cfg = {}
    # 优先读取加密配置 fastgpt.config.enc：磁盘不留明文密钥，启动时在内存中解密（可移植，不绑定机器）
    enc_path = os.path.join(ROOT, 'fastgpt.config.enc')
    if os.path.isfile(enc_path):
        try:
            if ROOT not in sys.path:   # 自带 runtime 嵌入式发行版不含脚本目录，需显式补充
                sys.path.insert(0, ROOT)
            import secrets_util
            return _parse_kv(secrets_util.decrypt_file(enc_path), cfg)
        except Exception as e:
            print('[config] fastgpt.config.enc 解密失败: %r' % e)
    # 兼容回退：明文 fastgpt.config（开发期可直接编辑，交付前用 encrypt_config.py 加密）
    path = os.path.join(ROOT, 'fastgpt.config')
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                _parse_kv(f.read(), cfg)
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
# 视觉模型（图片识别）：拓扑图 AI 建模用；需平台/模型支持 vision 能力
LLM_MODEL_VISION = os.environ.get('LLM_MODEL_VISION', _FG_CFG.get('LLM_MODEL_VISION', 'qwen3.8-flash'))
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', _FG_CFG.get('LLM_TIMEOUT', '120')))
# 思考开关：默认 off = 跳过模型思考直达输出（约快一倍以上，与视觉识别路径同款提速）；
# 如需保留思考过程换取更复杂问题的深度，在 fastgpt.config 加 LLM_THINKING=on
LLM_THINKING_ON = os.environ.get('LLM_THINKING', _FG_CFG.get('LLM_THINKING', 'off')
                                 ).strip().lower() in ('on', 'true', '1', 'yes')
if LLM_BASE and LLM_KEY:
    print('[config] FastGPT 已接入: 对接知识库（诊断 / 复盘 / 拓扑识别）')

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
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
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
        # 推理类模型（deepseek-v4 等）会先产出 reasoning_content，与 content 共享 max_tokens；
        # 900 会被思考过程吃光导致 content 恒为空，故放宽并做 reasoning 兜底。
        # 默认关掉思考直达输出（LLM_THINKING=on 可恢复），与视觉识别路径同款提速
        body = {'model': LLM_MODEL.get(scene, 'glm-5.3-flash'), 'messages': call_msgs,
                'stream': False, 'temperature': 0.5,
                'max_tokens': 6000 if scene == 'review' else 4000}
        if not LLM_THINKING_ON:
            body['thinking'] = {'type': 'disabled'}
        # 网关偶发返回空 content：最多尝试 2 次；thinking 参数不被网关接受时自动去掉重试
        for attempt in (1, 2):
            for b in (body, {k: v for k, v in body.items() if k != 'thinking'}):
                req = urllib.request.Request(
                    LLM_BASE + '/chat/completions',
                    data=json.dumps(b).encode('utf-8'),
                    headers={'Content-Type': 'application/json',
                             'Authorization': 'Bearer ' + LLM_KEY})
                try:
                    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                        data = json.loads(r.read().decode('utf-8'))
                    msg = (data.get('choices') or [{}])[0].get('message', {})
                    content = msg.get('content')
                    if not content and msg.get('reasoning_content'):
                        # 极端情况（content 仍被截断）：用思考文本兜底，好过掉到演示模式
                        print('[ai] content 为空，使用 reasoning_content 兜底')
                        content = msg['reasoning_content']
                    if content:
                        return content
                    print('[ai] FastGPT 第 %d 次返回空内容' % attempt)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 400 and 'thinking' in b:
                        continue   # 参数不被该模型接受：去掉重试
                    print('[ai] FastGPT 调用失败: HTTP %s' % e.code)
                    if 'thinking' not in b:
                        return None   # 400 与请求内容相关，重试无意义
                    break
                except Exception as e:
                    print('[ai] FastGPT 调用失败: %r' % e)
                    break
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


def _llm_stream(messages, scene, on_delta):
    """流式直连大模型：正文每增量一段就回调 on_delta(t)，边生成边推送前端，大幅降低首字等待。
    返回完整正文（成功，含中途断流的部分内容）或 None（失败，调用方回退非流式 / 演示模式）。
    系统提示词、知识库注入、历史截短与 _llm_chat 完全一致，回答内容不受影响。"""
    if not LLM_BASE or not LLM_KEY:
        return None
    sys_txt = _SCENE_SYSTEM.get(scene, '')
    if scene == 'diagnose':
        kb = kb_lookup(_msg_text(messages[-1].get('content')) if messages else '')
        if kb:
            sys_txt += '\n\n以下是本站知识库中与该问题相关的参考资料（迁移自原知识库，可直接引用）：\n' + kb
    msgs = [{'role': 'system', 'content': sys_txt}]
    msgs += _strip_images(messages)[-4:]
    body = {'model': LLM_MODEL.get(scene, 'glm-5.3-flash'), 'messages': msgs,
            'stream': True, 'temperature': 0.5,
            'max_tokens': 6000 if scene == 'review' else 4000}
    if not LLM_THINKING_ON:
        body['thinking'] = {'type': 'disabled'}
    parts, reasoning = [], []
    while True:
        req = urllib.request.Request(
            LLM_BASE + '/chat/completions', data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + LLM_KEY})
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                for raw_line in r:
                    line = raw_line.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    payload = line[5:].strip()
                    if payload == '[DONE]':
                        break
                    try:
                        chunk = json.loads(payload)
                    except Exception:
                        continue
                    delta = (chunk.get('choices') or [{}])[0].get('delta', {})
                    if delta.get('content'):
                        parts.append(delta['content'])
                        on_delta(delta['content'])
                    elif delta.get('reasoning_content'):
                        reasoning.append(delta['reasoning_content'])
            break
        except urllib.error.HTTPError as e:
            if e.code == 400 and 'thinking' in body:
                body.pop('thinking')
                continue   # 参数不被该模型接受：去掉重试
            print('[ai] 流式调用失败: HTTP %s' % e.code)
            return ''.join(parts) or None
        except Exception as e:
            # 中途断流但已有部分正文：返回已有内容，好过整段重来
            print('[ai] 流式调用失败: %r' % e)
            return ''.join(parts) or None
    text = ''.join(parts)
    if text:
        return text
    if reasoning:
        # 与 _llm_chat 相同的兜底：content 为空时用思考文本，好过掉到演示模式
        t = ''.join(reasoning)
        on_delta(t)
        return t
    return None


def ai_chat(messages, scene='diagnose'):
    """直连大模型（含本地知识库检索注入）；失败时回退演示回复。"""
    r = _llm_chat(messages, scene)
    if r:
        return r, 'llm'
    return None, 'demo'


def _vision_call_once(model, b64, prompt):
    """单次视觉识别（流式接收）：返回 (内容文本, None) 或 (None, 失败原因)。
    先带 thinking:disabled（模型跳过思考直达输出，速度约快一倍以上）；
    网关对不认该参数的模型回 400，则去掉参数原样重试。"""
    body = {'model': model, 'stream': True, 'temperature': 0.2, 'max_tokens': 8000,
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64}}]}]}
    for no_think in (True, False):
        if no_think:
            body['thinking'] = {'type': 'disabled'}
        else:
            body.pop('thinking', None)
        req = urllib.request.Request(
            LLM_BASE + '/chat/completions', data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + LLM_KEY})
        parts = []
        try:
            with urllib.request.urlopen(req, timeout=max(LLM_TIMEOUT, 240)) as r:
                for raw_line in r:
                    line = raw_line.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    payload = line[5:].strip()
                    if payload == '[DONE]':
                        break
                    try:
                        chunk = json.loads(payload)
                    except Exception:
                        continue
                    delta = (chunk.get('choices') or [{}])[0].get('delta', {})
                    if delta.get('content'):
                        parts.append(delta['content'])
            return ''.join(parts), None
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = e.read().decode('utf-8', 'replace')
            except Exception:
                pass
            if e.code == 400 and no_think:
                continue   # 参数不被该模型接受：去掉重试
            if 'vision' in detail.lower():
                return None, '当前 FastGPT 模型不支持图片输入（vision），可在 fastgpt.config 配置视觉模型'
            return None, 'FastGPT 调用失败（HTTP %s）' % e.code
        except Exception as e:
            return None, 'FastGPT 调用失败: %r' % e


def _parse_topology_json(content):
    """从模型输出中解析并清洗拓扑 JSON → ({nodes,links}, None) 或 (None, 原因)。"""
    m = re.search(r'\{.*\}', content, re.S)
    if not m:
        return None, '识别结果无法解析'
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None, '识别结果 JSON 解析失败'
    if not isinstance(obj, dict):
        return None, '识别结果格式异常'
    if obj.get('error') == 'not-topology':
        return None, '图片不是网络拓扑图'
    seen = str(obj.get('seen', ''))
    if not seen or '无法' in seen or '不能' in seen or '看不到' in seen:
        return None, '当前 FastGPT 模型不支持图片输入（vision）'
    clean_nodes = []
    for n in (obj.get('nodes') or []):
        if not isinstance(n, dict):
            continue
        name = str(n.get('name', '')).strip()
        if not name:
            continue
        clean_nodes.append({'name': name[:40], 'type': str(n.get('type', '其他')).strip(), 'x': n.get('x'), 'y': n.get('y')})
    if len(clean_nodes) < 2:
        return None, '识别出的设备过少'
    names = {n['name'] for n in clean_nodes}
    clean_links, pair_seen = [], set()

    def _lname(v):
        # f/t 优先按 nodes 下标解析（提示词要求的新格式），兼容直接给名称的旧格式
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(clean_nodes):
            return clean_nodes[v]['name']
        s = str(v or '').strip()
        return s if s in names else None

    for l in (obj.get('links') or []):
        if not isinstance(l, dict):
            continue
        f = _lname(l.get('f', l.get('from')))
        t = _lname(l.get('t', l.get('to')))
        if f and t and f != t and (f, t) not in pair_seen and (t, f) not in pair_seen:
            clean_links.append({'from': f, 'to': t})
            pair_seen.add((f, t))
            pair_seen.add((t, f))
    return {'nodes': clean_nodes, 'links': clean_links}, None


def _norm_dev_name(s):
    """设备名归一化（多路结果合并用）：去空白、转小写、全角括号统一。"""
    return (re.sub(r'\s+', '', str(s or '')).lower()
            .replace('（', '(').replace('）', ')'))


def _merge_topo_passes(passes):
    """多路识别结果共识合并：以连线最全的一路为底；其它路的连线只有在
    「≥2 路都画出（含底路自身）且两端设备在底子里都已存在」时才补入——
    专补单路漏掉的终端线，又不给单路的幻觉线放行、不并出重名重复节点。"""
    def score(d):
        return (len(d['links']), len(d['nodes']))
    ordered = sorted(passes, key=score, reverse=True)
    base = ordered[0]
    pool = {_norm_dev_name(n['name']): n['name'] for n in base['nodes']}

    def norm_link(l):
        fk, tk = _norm_dev_name(l.get('from')), _norm_dev_name(l.get('to'))
        return tuple(sorted((fk, tk))) if fk in pool and tk in pool and fk != tk else None

    votes = {}
    for d in passes:
        for l in d['links']:
            pair = norm_link(l)
            if pair:
                votes[pair] = votes.get(pair, 0) + 1
    base_pairs = {norm_link(l) for l in base['links']}
    base_pairs.discard(None)
    extra = [pair for pair, n in votes.items() if n >= 2 and pair not in base_pairs]
    if extra:
        pretty = ', '.join('%s-%s' % (pool[a], pool[b]) for a, b in extra)
        print('[ai] 共识补线 %d 条：%s' % (len(extra), pretty))
    return {'nodes': base['nodes'],
            'links': base['links'] + [{'from': pool[a], 'to': pool[b]} for a, b in extra]}


def recognize_topology_image(b64):
    """视觉大模型识别网络拓扑图 → ({nodes,links}, None) 或 (None, 失败原因)。
    节点名取图中标注文字（几何识别读不了文字，这里由大模型读）；
    连线只按图中实际画出的线还原；坐标归一化 0-1000。
    同款模型双路并发（两路提示词各有侧重：一路均衡、一路专盯终端连线），
    结果做并集合并互相补漏——flash 档单次连线数有波动，并集不增加等待时间；
    合并后仍无有效结果时换备用模型兜底。
    通过 seen 字段防呆：文字模型看不到图却硬编时会被拦截。"""
    prompt_tail = (
        '要求：\n'
        '1. nodes：图中画出的每台设备节点（如云、光猫、防火墙、路由器、交换机、无线控制器、上网行为管理、服务器、AP、'
        '摄像头、终端电脑、打印机、电话等）。name 用图中标注的文字（设备图形下方或旁边的文字标注），'
        '不要用图形框内的缩写字母（如 ISP/SW/FW/RTR 只是图标装饰）；图中没标注的用类型命名。type 只能取：互联网、光猫、防火墙、'
        '路由器、交换机、无线控制器、上网行为管理、AP、服务器、终端、打印机、摄像头、电话、其他。'
        'x/y 为设备在图中的位置，归一化到 0-1000（左上角为原点）。\n'
        '2. links：图中实际画出的连线，f/t 为两端设备在 nodes 数组中的下标（从 0 开始）；'
        '只连图中真实画出的线，不要按常识自行补线。图中画了多台同名设备（如多台"接入交换机"、"AP"、"终端电脑"）时，'
        '每台都要单独输出为一个节点（按图中实际台数），不要合并成一台。\n'
        '3. 图中的虚线区域框（分组框）不是设备，不要作为节点。\n'
        '4. 不要编造图中不存在的设备或连线。如果图片不是网络拓扑图，输出 {"error":"not-topology"}。\n'
        '输出格式：{"seen":"一句话描述图片整体内容","nodes":[{"name":"...","type":"...","x":123,"y":456}],'
        '"links":[{"f":0,"t":2}]}'
    )
    prompt_main = (
        '你是网络拓扑图识别引擎。识别这张图中的网络拓扑，直接输出一个 JSON 对象（第一个字符是 {，最后一个字符是 }），'
        '不要输出任何分析过程。\n'
        '先数一遍图中设备图形（方框/图标）的总台数，nodes 的数量必须与图中实际台数一致。\n'
        + prompt_tail
    )
    prompt_link = (
        '你是网络拓扑图识别引擎。识别这张图中的网络拓扑，直接输出一个 JSON 对象（第一个字符是 {，最后一个字符是 }），'
        '不要输出任何分析过程。\n'
        '重点任务是把连线一条不漏地找全：对图中每台设备，逐台检查它的图形四周有没有连线伸出；'
        '边缘和底部一排的终端设备（终端电脑、打印机、摄像头、电话、AP）各自通常都有一根线连到交换机，这类线最容易被漏掉；'
        '发现某台设备在 links 里没有任何连线时，回到图中再确认一次，只有确认确实没有线才可以让它保持孤立。\n'
        + prompt_tail
    )
    vision = globals().get('_vision_model_ok') or LLM_MODEL_VISION
    last_err = '识别失败'
    good = []
    t0 = time.time()
    # 三路并发（均衡 / 均衡 / 专盯终端连线）：并行不增加等待时间，
    # 三路做共识合并——两路及以上都画出的连线才补入，单路幻觉线不放行
    prompts = (prompt_main, prompt_main, prompt_link)
    with ThreadPoolExecutor(max_workers=3) as ex:
        for content, err in ex.map(lambda i: _vision_call_once(vision, b64, prompts[i]), range(3)):
            if not content:
                last_err = err or last_err
                continue
            data, perr = _parse_topology_json(content)
            if perr:
                last_err = perr
                continue
            good.append(data)
    if good:
        merged = good[0] if len(good) == 1 else _merge_topo_passes(good)
        globals()['_vision_model_ok'] = vision   # 记住上次成功的视觉模型，下次优先用
        print('[ai] 拓扑识别 %s：%.1fs，%d 节点 %d 连线（%s）' % (
            vision, time.time() - t0, len(merged['nodes']), len(merged['links']),
            '+'.join(str(len(g['links'])) for g in good)))
        return merged, None
    # 兜底：备用模型单次识别
    for model in [m for m in ('glm-5.3-flash',) if m != vision]:
        content, err = _vision_call_once(model, b64, prompt_main)
        if not content:
            last_err = err or last_err
            continue
        data, perr = _parse_topology_json(content)
        if data:
            globals()['_vision_model_ok'] = model
            print('[ai] 拓扑识别兜底 %s：%.1fs，%d 节点 %d 连线' % (
                model, time.time() - t0, len(data['nodes']), len(data['links'])))
            return data, None
        if perr:
            last_err = perr
    return None, last_err


def extract_doc_text(name, raw):
    """从 docx / pdf 提取纯文字（诊断助手附件解析）。
    失败抛 ValueError（消息可直接展示给工程师），成功返回纯文本。"""
    low = (name or '').lower()
    try:
        if low.endswith('.topo'):
            # 华为 eNSP 拓扑文件（无公开规范）：zip 包形态解出内嵌 xml/text，
            # 纯文本/二进制形态原样返回，由前端做设备识别
            if raw[:2] == b'PK':
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    cands = [n for n in z.namelist()
                             if n.lower().endswith(('.xml', '.txt', '.topo', '.topodata', '.ini'))]
                    pick = max(cands or z.namelist(), key=lambda n: z.getinfo(n).file_size)
                    return z.read(pick).decode('utf-8', 'ignore')[:200000]
            return raw.decode('utf-8', 'ignore')[:200000]
        if low.endswith('.docx'):
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read('word/document.xml').decode('utf-8', 'ignore')
            xml = xml.replace('</w:p>', '\n').replace('<w:br/>', '\n').replace('<w:tab/>', '\t')
            text = html.unescape(re.sub(r'<[^>]+>', '', xml))
            return re.sub(r'\n{3,}', '\n\n', text).strip()
        if low.endswith('.pdf'):
            try:
                import pymupdf as fitz
            except ImportError:
                try:
                    import fitz
                except ImportError:
                    raise ValueError('服务端缺少 PDF 解析组件（pymupdf），请 pip install pymupdf')
            doc = fitz.open(stream=raw, filetype='pdf')
            try:
                pages = [doc.load_page(i).get_text() for i in range(min(doc.page_count, 30))]
            finally:
                doc.close()
            return re.sub(r'\n{3,}', '\n\n', '\n'.join(pages)).strip()
    except ValueError:
        raise
    except Exception as e:
        raise ValueError('文档可能已损坏或加密（%s）' % e.__class__.__name__)
    raise ValueError('仅支持 docx / pdf 文档解析，其他格式请直接粘贴文字')


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
    """真实读取本机网卡信息（Windows: ipconfig /all，中英文输出均兼容）。
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

    # 字段标签兼容中文系统与输出英文标签的系统（Host Name / IPv4 Address / ...）
    labels = {
        'host': ('主机名', 'Host Name'),
        'ip': ('IPv4 地址', 'IPv4 Address'),
        'mask': ('子网掩码', 'Subnet Mask'),
        'gateway': ('默认网关', 'Default Gateway'),
        'desc': ('描述', 'Description'),
        'mac': ('物理地址', 'Physical Address'),
        'dhcp': ('DHCP 已启用', 'DHCP Enabled'),
        'dns': ('DNS 服务器', 'DNS Servers'),
    }

    def pick(block, field):
        for ln in block:
            for key in labels[field]:
                if key in ln and ':' in ln:
                    return ln.split(':', 1)[1].strip().rstrip(',').strip()
        return None

    blocks, cur = [], []
    for ln in text.splitlines():
        if ln and not ln.startswith(' ') and ln.rstrip().endswith(':'):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)

    hostname = ''
    for b in blocks:
        head = b[0] if b else ''
        if ('适配器' in head) or ('adapter' in head.lower()):
            break  # 主机名只出现在首个（系统信息）块中
        h = pick(b, 'host')
        if h:
            hostname = h
            break

    best = None
    fallback = None
    for b in blocks:
        head = b[0] if b else ''
        if ('适配器' not in head) and ('adapter' not in head.lower()):
            continue
        ip = pick(b, 'ip')
        gw = pick(b, 'gateway')
        if not ip:
            continue
        if '适配器' in head:
            name = head.split('适配器', 1)[1].strip().rstrip(':')
        else:
            name = head.split('adapter', 1)[1].strip().rstrip(':')
        desc = pick(b, 'desc') or ''
        is_wifi = any(k in (name + desc).upper() for k in ('WLAN', '无线', 'WI-FI', 'WIFI', '802.11', 'WIRELESS'))

        def ipv4(s):
            m = re.search(r'\d+\.\d+\.\d+\.\d+', s or '')
            return m.group(0) if m else ''
        dhcp_raw = (pick(b, 'dhcp') or '').strip().lower()
        e = {
            'adapter': name, 'desc': desc, 'conn_type': 'wifi' if is_wifi else 'ethernet',
            'ip': ipv4(ip), 'mask': ipv4(pick(b, 'mask')) or '255.255.255.0',
            'gateway': ipv4(gw) if gw else '', 'mac': pick(b, 'mac') or '',
            'dhcp': dhcp_raw.startswith('是') or dhcp_raw.startswith('yes'),
            'dns': ipv4(pick(b, 'dns')), 'hostname': hostname,
        }
        if e['gateway']:
            best = e
            if is_wifi:
                break  # 优先呈现无线网卡（对应工程师连 WiFi 的场景）
        else:
            # ipconfig 未显示网关的网卡（部分 DHCP 不下发网关字段），留作路由表兜底候选
            if fallback is None or (is_wifi and fallback['conn_type'] != 'wifi'):
                fallback = e
    if best is None and fallback is not None:
        rt_gw = default_route_gateway()
        if rt_gw:
            fallback['gateway'] = rt_gw
            best = fallback
    return best


def default_route_gateway():
    """从系统路由表读默认网关（ipconfig 不显示网关时的兜底）。"""
    try:
        raw = subprocess.run(['route', 'print', '-4'], capture_output=True, timeout=5).stdout
        text = raw.decode('gbk', 'replace')
    except Exception:
        return ''
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) >= 5 and parts[0] == '0.0.0.0' and parts[1] == '0.0.0.0':
            return parts[2]
    return ''


def ipv4_in(ip, prefix, bits):
    """判断 ip 是否在 prefix/bits 网段内（用于按网卡网段匹配目标）。"""
    try:
        a = socket.inet_aton(ip)
        b = socket.inet_aton(prefix + '.0')
        mask = (0xffffffff << (32 - bits)) & 0xffffffff
        return (int.from_bytes(a, 'big') ^ int.from_bytes(b, 'big')) & mask == 0
    except Exception:
        return False


def list_all_nics():
    """枚举本机全部 IPv4 网卡（多网卡选线路用）。

    每块网卡一条：名称/描述/IP/掩码/网关/协商速率/有线无线/虚拟标记。
    网关取自 ipconfig 对应适配器块，缺省时用 route print 按接口 IP 兜底；
    协商速率复用 Get-NetAdapter 口径（失败留空，不影响选择）。
    """
    # 协商速率表：{适配器名(小写): '1 Gbps'}（获取失败则为空表）
    speeds = {}
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-CimInstance Win32_NetworkAdapter -Filter "NetEnabled=true" | '
             'ForEach-Object { $_.Name + "|" + ($_.Speed / 1e6) + " Mbps" }'],
            capture_output=True, timeout=12)
        for ln in r.stdout.decode('utf-8', 'replace').splitlines():
            parts = ln.strip().split('|')
            if len(parts) == 2 and parts[1]:
                speeds[parts[0].strip().lower()] = parts[1].strip()
    except Exception:
        pass

    # route print 兜底网关：取「0.0.0.0 默认路由 + 本机接口 IP」匹配
    gw_by_if = {}
    try:
        raw = subprocess.run(['route', 'print', '-4'], capture_output=True, timeout=5).stdout
        for ln in raw.decode('gbk', 'replace').splitlines():
            parts = ln.split()
            # 默认路由行：0.0.0.0 0.0.0.0 网关 接口IP 度量
            if len(parts) >= 5 and parts[0] == '0.0.0.0' and parts[1] == '0.0.0.0':
                gw_by_if.setdefault(parts[3], parts[2])
    except Exception:
        pass

    try:
        raw = subprocess.run(['ipconfig', '/all'], capture_output=True, timeout=5).stdout
        text = raw.decode('gbk', 'replace')
    except Exception:
        try:
            text = subprocess.run(['ipconfig', '/all'], capture_output=True,
                                  timeout=5, text=True).stdout or ''
        except Exception:
            return []

    def ipv4(s):
        m = re.search(r'\d+\.\d+\.\d+\.\d+', s or '')
        return m.group(0) if m else ''

    blocks, cur = [], []
    for ln in text.splitlines():
        if ln and not ln.startswith(' ') and ln.rstrip().endswith(':'):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)

    nics = []
    for b in blocks:
        head = b[0] if b else ''
        if ('适配器' not in head) and ('adapter' not in head.lower()):
            continue
        if '适配器' in head:
            name = head.split('适配器', 1)[1].strip().rstrip(':')
        else:
            name = head.split('adapter', 1)[1].strip().rstrip(':')
        ip = ipv4(next((l for l in b if 'IPv4' in l and ':' in l), ''))
        if not ip or ip.startswith('169.254.'):
            continue    # 无 IP 或 APIPA 自动私网地址：链路不通，不作为可选线路
        mask = ipv4(next((l for l in b if ('子网掩码' in l or 'Subnet Mask' in l)), '')) or '255.255.255.0'
        gw = ipv4(next((l for l in b if ('默认网关' in l or 'Default Gateway' in l)), ''))
        desc = next((l.split(':', 1)[1].strip() for l in b
                     if ('描述' in l or 'Description' in l) and ':' in l), '')
        is_wifi = any(k in (name + ' ' + desc).upper()
                      for k in ('WLAN', '无线', 'WI-FI', 'WIFI', '802.11', 'WIRELESS'))
        virtual = is_virtual_adapter_name(name + ' ' + desc)
        if not gw:
            gw = gw_by_if.get(ip, '')
        nics.append({
            'name': name,
            'desc': (desc or '')[:48],
            'ip': ip, 'mask': mask, 'gateway': gw,
            'speed': speeds.get(name.strip().lower(), ''),
            'conn_type': 'wifi' if is_wifi else 'ethernet',
            'virtual': virtual,
        })
    # 排序：真实网卡在前（有网关的优先），虚拟网卡垫底
    nics.sort(key=lambda n: (n['virtual'], not n['gateway'], n['conn_type'] != 'ethernet'))
    # 协商速率回填：CIM 的连接名（Intel(R) Wi-Fi...）与 ipconfig 适配器名（WLAN）口径不同，
    # 按描述名匹配；先查精确名再查描述
    if speeds:
        for n in nics:
            for key in (n['name'], n['desc']):
                k = key.strip().lower()
                if k in speeds:
                    n['speed'] = speeds[k]
                    break
                for sk, sv in speeds.items():
                    if k and (k in sk or sk in k):
                        n['speed'] = sv
                        break
                if n['speed']:
                    break
    return nics


def mask_to_prefix(mask):
    try:
        return bin(int(mask.split('.')[0]) << 24 | int(mask.split('.')[1]) << 16 |
                   int(mask.split('.')[2]) << 8 | int(mask.split('.')[3])).count('1')
    except Exception:
        return 24


# ---------------- 真实内网感知（ping 扫描 / ARP / 端口指纹） ----------------

PING_TIMEOUT_MS = 300
PRINTER_PORT_NAME = {9100: 'JetDirect 9100', 631: 'IPP 631', 515: 'LPD 515'}

# 常见服务端口 → 设备/系统特征（补充指纹：22/3389/8443 等）
PORT_HINTS = {
    22: 'SSH（Linux / 网络设备）',
    3389: 'Windows 远程桌面',
    8443: '管理口（深信服设备常用 8443）',
}

# 常见厂商 OUI 前缀（MAC 前 3 字节）
OUI_VENDORS = {
    '00-0f-e2': 'H3C', '00-e0-fc': 'H3C', '00-23-89': 'H3C', '28-6e-d4': '华为/H3C',
    '04-f9-38': '华为', '18-c5-8a': '华为', '48-46-fb': '华为', '5c-c9-99': '华为',
    '88-28-b3': '华为', '8c-ec-4b': '华为', 'd4-61-2e': '华为', 'e8-08-1f': '华为',
    '00-25-86': '锐捷', '04-25-c5': '锐捷',
    '00-00-0c': '思科', 'f8-72-ea': '思科', '00-1b-0d': '思科', '00-26-99': '思科',
    '50-c7-bf': 'TP-LINK', 'd8-5d-84': 'TP-LINK', '14-cc-20': 'TP-LINK', 'f4-f2-6d': 'TP-LINK',
    '3c-d9-2b': 'HP 打印机', '10-1f-74': 'HP 打印机', '2c-41-38': 'HP 打印机', '6c-3b-e5': 'HP 打印机',
    '00-1e-8f': 'Canon 打印机', '18-e7-f4': 'Canon 打印机', 'f4-ce-8c': 'Canon 打印机',
    '00-1b-a9': 'Brother 打印机', 'e0-5f-b9': 'Brother 打印机', '84-38-35': 'Brother 打印机',
    '00-1b-25': 'Epson 打印机', '64-eb-8c': 'Epson 打印机',
    '00-20-6d': 'Ricoh 打印机', '00-c0-ee': 'Kyocera 打印机',
    'f8-db-88': 'Dell', '14-fe-b5': 'Dell', '18-03-73': 'Dell', 'a4-ba-db': 'Dell', '5c-f9-38': 'Dell',
    '54-ee-75': '联想', '8c-16-45': '联想', '60-d9-c7': '联想', '5c-c3-07': '联想',
    '14-da-e9': '联想', 'd0-7e-35': '联想', '00-25-64': '联想',
    'f0-18-98': '苹果', '3c-07-54': '苹果', '14-99-e2': '苹果', 'a4-83-e7': '苹果', '50-ed-3c': '苹果',
    '64-09-80': '小米', '8c-be-be': '小米', 'e4-46-da': '小米',
}


def ping_alive(ip, timeout_ms=PING_TIMEOUT_MS):
    try:
        r = subprocess.run(['ping', '-n', '1', '-w', str(timeout_ms), ip],
                           capture_output=True, timeout=timeout_ms / 1000.0 + 2)
        out = r.stdout.decode('gbk', 'replace')
        return r.returncode == 0 and 'TTL=' in out
    except Exception:
        return False


def ping_sweep(prefix):
    """并发 ping 扫描本机所在 /24 网段，返回在线 IP 列表。"""
    ips = ['%s.%d' % (prefix, i) for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=96) as ex:
        results = list(ex.map(ping_alive, ips))
    return [ip for ip, ok in zip(ips, results) if ok]


def read_arp_table():
    """读取系统 ARP 表（ping 扫描后 MAC 已缓存），返回 {ip: mac}。"""
    arp = {}
    try:
        raw = subprocess.run(['arp', '-a'], capture_output=True, timeout=5).stdout
        text = raw.decode('gbk', 'replace')
    except Exception:
        return arp
    for ln in text.splitlines():
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+(([0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})', ln)
        if m:
            arp[m.group(1)] = m.group(2).lower()
    return arp


def mac_vendor(mac):
    if not mac:
        return ''
    return OUI_VENDORS.get(mac[:8].lower(), '')


def parse_subnet(text):
    """把用户录入的网段解析成 (prefix, bits)；支持 192.168.20.0/24、192.168.20、192.168.20.0 255.255.255.0。
    非法返回 None。"""
    t = (text or '').strip()
    m = re.fullmatch(r'(\d{1,3}(?:\.\d{1,3}){0,3})(?:/(\d{1,2}))?(?:\s+(?:mask[:：]?)?(\d{1,3}(?:\.\d{1,3}){3}))?', t)
    if not m:
        return None
    parts = m.group(1).split('.')
    while len(parts) < 4:
        parts.append('0')
    try:
        if any(int(p) > 255 for p in parts):
            return None
        if m.group(3):                       # 点分掩码
            bits = mask_to_prefix(m.group(3))
        elif m.group(2) is not None:         # /bits
            bits = int(m.group(2))
        else:                                # 无掩码默认 /24
            bits = 24
        if not (8 <= bits <= 30):
            return None
    except Exception:
        return None
    # 统一成三段 prefix（与 build_real_network 的 base 同构）：'192.168.20.0/24' → '192.168.20'
    prefix = '.'.join(parts[:3])
    return (prefix, bits)


VIRTUAL_NIC_KEYWORDS = ('VirtualBox', 'VMware', 'Hyper-V', 'WSL', 'Loopback', 'TAP', 'TUN',
                        'virtual', 'vEthernet', '蓝牙', 'Bluetooth')


def is_virtual_adapter_name(name):
    """按适配器名称判断是否虚拟/本地回环类网卡。"""
    n = name or ''
    return any(k.lower() in n.lower() for k in VIRTUAL_NIC_KEYWORDS)


def local_nic_subnets():
    """读 ipconfig，按【适配器块】枚举本机全部 IPv4 网卡。
    返回 [{'prefix','bits','virtual'}]；virtual=True 为虚拟网卡（VirtualBox/VMware 等宿主私有网段，
    不属于客户内网，自动批量扫描时应排除）。失败返回 []。"""
    out = []
    try:
        raw = subprocess.run(['ipconfig'], capture_output=True, timeout=6).stdout
        text = raw.decode('gbk', 'replace')
    except Exception:
        return out
    # 按"适配器"行切分块，逐块内配对 IPv4 与掩码
    blocks = re.split(r'\n(?=\s*\S*适配器|\n(?=\s*adapter ))', '\n' + text, flags=re.I)
    for blk in blocks:
        mname = re.search(r'适配器\s*([^\n:：]+)|adapter\s+([^\n:：]+)', blk, re.I)
        name = (mname.group(1) or mname.group(2)).strip() if mname else ''
        virtual = is_virtual_adapter_name(name)
        ips = re.findall(r'IPv4[^：:\n]*[：:]\s*(\d+\.\d+\.\d+\.\d+)', blk)
        masks = re.findall(r'(?:子网掩码|Subnet Mask)[^：:\n]*[：:]\s*(\d+\.\d+\.\d+\.\d+)', blk)
        for ip, mask in zip(ips, masks[:len(ips)]):
            if ip.startswith('127.') or ip.startswith('169.254.'):
                continue
            bits = mask_to_prefix(mask)
            prefix = '.'.join(ip.split('.')[:3])
            cand = {'prefix': prefix, 'bits': bits, 'virtual': virtual}
            if cand not in out:
                out.append(cand)
    # 兜底：知名虚拟宿主网段即使名称没带上关键字也标为虚拟
    KNOWN_VIRTUAL_PREFIXES = ('192.168.56.',)   # VirtualBox Host-Only 默认段
    for item in out:
        if item['prefix'].startswith(KNOWN_VIRTUAL_PREFIXES):
            item['virtual'] = True
    return out


# ---------------- SNMP v2c（纯标准库 BER，读交换机 MAC 地址表） ----------------
SNMP_OID_SYSDESCR = '1.3.6.1.2.1.1.1.0'          # sysDescr.0：探活+识别交换机型号
SNMP_OID_MAC_TABLE = '1.3.6.1.2.1.17.4.3.1.2'    # dot1dTpFdbTable：MAC → 端口


def _ber_len(n):
    if n < 128:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(b)]) + b


def _ber_oid(oid):
    parts = [int(x) for x in oid.split('.')]
    body = bytes([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        chunk = []
        chunk.append(p & 0x7F)
        p >>= 7
        while p:
            chunk.append((p & 0x7F) | 0x80)
            p >>= 7
        body += bytes(reversed(chunk))
    return b'\x06' + _ber_len(len(body)) + body


def _ber_int(n):
    b = n.to_bytes(max(1, (n.bit_length() + 8) // 8), 'big', signed=True)
    return b'\x02' + _ber_len(len(b)) + b


def _ber_octets(b):
    return b'\x04' + _ber_len(len(b)) + b


def _ber_seq(payload, tag=0x30):
    return bytes([tag]) + _ber_len(len(payload)) + payload


def _asn1_walk(objs, tag):
    """从 BER 缓冲里取出指定 tag 的所有 TLV（用于解 SNMP 响应）。"""
    out = []
    i = 0
    while i < len(objs):
        t = objs[i]
        if i + 1 >= len(objs):
            break
        ln = objs[i + 1]
        hd = 2
        if ln & 0x80:
            k = ln & 0x7F
            ln = int.from_bytes(objs[i + 2:i + 2 + k], 'big')
            hd = 2 + k
        if t == tag:
            out.append(objs[i + hd:i + hd + ln])
        i += hd + ln
    return out


def snmp_getnext_walk(ip, community, version, base_oid, max_rows=200, timeout=1.0):
    """纯标准库实现 SNMP v2c GETNEXT 遍历，返回 {oid字符串: 值字节}。
    仅支持 v2c（v3 需要 USM 加密，超出标准库范围，前端给出提示）。失败返回 {}。"""
    if version not in ('v2c', '2c', '2'):
        return {}
    res = {}
    oid = base_oid
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        for _ in range(max_rows):
            # SNMP GETNEXT PDU tag = 0xA1；请求 id=1, err=0, erridx=0
            varbind = _ber_seq(_ber_oid(oid))
            pdu_body = _ber_int(1) + _ber_int(0) + _ber_int(0) + _ber_seq(varbind)
            pdu = b'\xa1' + _ber_len(len(pdu_body)) + pdu_body
            packet = _ber_seq(_ber_int(version_map(version)) + _ber_octets(community.encode()) + pdu)
            sock.sendto(packet, (ip, 161))
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                break
            # 粗解：直接在整包里找 OCTET STRING（第一个为 OID，最后一个为值）
            octets = _asn1_walk(data, 0x06)
            if len(octets) < 2:
                break
            next_oid_raw, val_raw = octets[0], octets[-1]
            next_oid = '.'.join(str(b) for b in _decode_oid(next_oid_raw))
            if not next_oid.startswith(base_oid):
                break
            res[next_oid] = val_raw
            oid = next_oid
    except Exception:
        pass
    finally:
        sock.close()
    return res


def version_map(v):
    return {0: 0, 1: 0, 'v1': 0, 'v2c': 1, '2c': 1, '2': 1}.get(v, 1)


def _decode_oid(raw):
    if not raw:
        return []
    first = raw[0]
    out = [first // 40, first % 40]
    val = 0
    for b in raw[1:]:
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            out.append(val)
            val = 0
    return out


def snmp_probe_switch(ip, community, version):
    """SNMP 探测交换机：取 sysDescr 验证可达；成功返回 {'ok':True,'sysdescr':...}。"""
    rows = snmp_getnext_walk(ip, community, version, SNMP_OID_SYSDESCR, max_rows=1)
    if not rows:
        return {'ok': False}
    val = next(iter(rows.values()), b'')
    return {'ok': True, 'sysdescr': val.decode('utf-8', 'replace').strip()[:120]}


def snmp_read_mac_table(ip, community, version):
    """读交换机 dot1dTpFdbTable，返回 {'mac列表': [...], 'ok': True}；不可达返回 {'ok':False}。"""
    rows = snmp_getnext_walk(ip, community, version, SNMP_OID_MAC_TABLE, max_rows=256)
    if not rows:
        return {'ok': False}
    macs = []
    for oid, val in rows.items():
        # FdbTable 索引尾部 6 字节即 MAC
        tail = oid.split('.')[-6:]
        if len(tail) == 6 and all(t.isdigit() for t in tail):
            macs.append('-'.join('%02x' % int(t) for t in tail))
    return {'ok': True, 'macs': macs}


def fingerprint_host(ip):
    """对在线主机做端口指纹：打印机(9100/631/515) + SMB(445) + SSH/RDP/管理口(22/3389/8443)。
    返回 fp：printer_port / smb / hints(服务特征列表) / label(综合推断)。
    7 个端口并发探测（超时与端口集与旧串行版一致，结果不变，仅把每台 3.5s 的最坏等待压到 0.5s）。"""
    fp = {'ip': ip, 'printer_port': None, 'smb': False, 'hints': []}
    def probe(port):
        try:
            s = socket.create_connection((ip, port), timeout=0.5)
            s.close()
            return port
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=7) as pex:
        open_ports = [p for p in pex.map(probe, (9100, 631, 515, 445, 22, 3389, 8443)) if p]
    for port in open_ports:
        if port in PRINTER_PORT_NAME and fp['printer_port'] is None:
            fp['printer_port'] = port
        elif port == 445:
            fp['smb'] = True
        elif port in PORT_HINTS:
            fp['hints'].append(PORT_HINTS[port])
    # 综合标签：多特征叠加推断设备身份
    labels = []
    if fp['smb']:
        labels.append('Windows 终端（SMB）')
    if 22 in open_ports:
        labels.append('Linux / 网络设备（SSH）')
    if 3389 in open_ports:
        labels.append('Windows（远程桌面开放）')
    if 8443 in open_ports:
        labels.append('疑似深信服设备（8443 管理口）')
    fp['label'] = ' + '.join(labels) if labels else ''
    fp['open_ports'] = open_ports
    return fp


# ---------------- 深信服设备知识库（工程师声明上架设备 → 建模 + 部署建议） ----------------
# mode: inline=串接在出口链路上 / onearm=旁挂核心或核心交换 / serverzone=旁挂服务器区
# 旁挂类设备（部署不改变主链路，拓扑上画在核心/汇聚侧位）
SANGFOR_BYPASS = {'AC', 'SSL', 'VDC', 'XAC'}

SANGFOR_DEVICES = {
    'AF': {'name': '深信服 AF', 'full': 'AF 下一代防火墙', 'icon': '🛡️', 'mode': 'inline', 'tier': 1,
           'summary': '边界安全：防火墙 / IPS / 防病毒 / 上网策略',
           'deploy': '串接在出口网关与内网之间（透明桥或路由模式），做出口边界防护与策略控制'},
    'AC': {'name': '深信服 AC', 'full': 'AC 上网行为管理', 'icon': '🎛️', 'mode': 'onearm', 'tier': 3,
           'summary': '上网行为管理：流量管控 / 行为审计 / 上网认证',
           'deploy': '默认旁挂（经核心交换机镜像/引流审计，不改变路由）；注明「串联/串接/网桥」时透明串接在路由器下方，内网终端接于其下'},
    'AD': {'name': '深信服 AD', 'full': 'AD 应用交付', 'icon': '⚖️', 'mode': 'inline', 'tier': 1,
           'summary': '应用交付：链路负载均衡 / 服务器负载均衡',
           'deploy': '部署在互联网多线接入与服务器区之间，做链路选路与应用发布加速'},
    # EDR 已下架：端点安全统一由升级版 aES（AES）承载
    'VDC': {'name': '深信服 VDC', 'full': 'VDC 虚拟桌面管理', 'icon': '🖥️', 'mode': 'serverzone', 'tier': 3,
            'summary': '云桌面：虚拟桌面交付 / 集中管控',
            'deploy': '旁挂部署在服务器区，配套 aDesk 云终端使用，承载桌面虚拟化业务'},
    'SSL': {'name': '深信服 SSL VPN', 'full': 'SSL VPN / 零信任接入', 'icon': '🔐', 'mode': 'onearm', 'tier': 3,
            'summary': '远程接入：SSL VPN / 多因素认证 / 零信任',
            'deploy': '旁挂或串接在出口区，对外发布远程接入入口，供移动办公与运维接入'},
    'WOC': {'name': '深信服 WOC', 'full': 'WOC 广域网优化', 'icon': '🚀', 'mode': 'inline', 'tier': 1,
            'summary': '广域网优化：链路加速 / 数据缓存 / QoS',
            'deploy': '串接在出口链路上（两端各一台成对部署），加速跨广域业务流量'},
    'XAC': {'name': '深信服 XAC', 'full': 'XAC 云原生安全平台', 'icon': '☁️', 'mode': 'serverzone', 'tier': 3,
            'summary': '云安全资源池：按需交付安全能力',
            'deploy': '旁挂部署在服务器区/云管理网，按业务按需编排安全资源'},
    'SDWR': {'name': '深信服 SDW-R', 'full': 'SDW-R 安誓路由器', 'icon': '🔗', 'mode': 'inline', 'tier': 1,
             'summary': '安全路由：软件定义路由 / SD-WAN 组网 / 边界安全',
             'deploy': '部署在出口做安全路由与 SD-WAN 组网，替代传统出口路由器'},
    'XDR': {'name': '深信服 XDR', 'full': 'XDR 可扩展检测与响应平台', 'icon': '🛰️', 'mode': 'serverzone', 'tier': 3,
            'summary': '扩展检测与响应：跨终端 / 网络联动检测，AI 自动处置（分布式 XDR+GPT）',
            'deploy': '旁挂部署在服务器区/核心区，接入 EDR 与流量探针数据做联动检测响应'},
    'AES': {'name': '深信服 aES', 'full': 'aES 统一端点安全管理系统', 'icon': '🧰', 'mode': 'serverzone', 'tier': 3,
            'summary': '统一端点安全：防病毒 / 补丁分发 / 外设与准入管控',
            'deploy': '旁挂部署在办公网可达位置，各终端安装客户端统一管控'},
    'NGES': {'name': '深信服 NGES', 'full': 'NGES 下一代端点安全', 'icon': '🧿', 'mode': 'serverzone', 'tier': 3,
             'summary': '下一代端点安全：AI 引擎 EPP+EDR 一体化防护',
             'deploy': '旁挂部署在服务器区/办公网可达位置，终端轻量接入统一防护'},
    'ATRUST': {'name': '深信服 aTrust', 'full': 'aTrust 零信任访问控制系统', 'icon': '🛂', 'mode': 'onearm', 'tier': 3,
               'summary': '零信任访问：身份认证 / 最小权限 / 动态访问控制',
               'deploy': '旁挂部署在出口/核心区，对外发布零信任业务访问入口，先认证后连接'},
    'HCI': {'name': '深信服 HCI', 'full': 'HCI 超融合', 'icon': '🗃️', 'mode': 'serverzone', 'tier': 3,
            'summary': '超融合：计算 / 存储 / 网络一体化资源池',
            'deploy': '部署在服务器区承载业务虚机与云桌面，按集群扩容'},
    'EDS': {'name': '深信服 EDS', 'full': 'EDS 企业级分布式存储', 'icon': '💾', 'mode': 'serverzone', 'tier': 3,
            'summary': '分布式存储：海量非结构化数据弹性存储',
            'deploy': '部署在服务器区/存储网，为业务与备份提供统一存储资源池'},
    'ADESK': {'name': '深信服 aDesk', 'full': 'aDesk 桌面云', 'icon': '💻', 'mode': 'serverzone', 'tier': 3,
              'summary': '桌面云：云桌面交付 / 集中运维 / 数据不落地',
              'deploy': '部署在服务器区（配套 VDC/云终端），为办公与涉密场景交付云桌面'},
}


def _cluster_size(note):
    """从工程师备注里解析集群成员数量：'3台'/'三台' → 3；双机/未注明 → 2。"""
    nl = note or ''
    m = re.search(r'(\d+)\s*台', nl)
    if m:
        return min(8, max(2, int(m.group(1))))
    for w, n in (('两台', 2), ('三台', 3), ('四台', 4)):
        if w in nl:
            return n
    return 2


def _resolve_deploy(key, note):
    """解析单台设备的部署方式（附件二最佳实践 + 工程师期望词优先）。
    返回 {form, pos, label, long}：
      form: single=单机 | cluster=双机/集群（两台及以上并排、互联双心跳，一般部署在出口）
      pos:  up=出口位 | down=透明串接位（网关与内网之间，充当交换机）
            bypass=旁挂位（镜像/引流，不改变主链路） | serverfront=服务器区前串接（数据中心边界）
    关键词判定顺序：数据中心/服务器区 → 集群/双机/热备 → 出口 → 透明/串接 → 旁挂；
    未注明时按产品知识表默认形态（inline→出口，onearm/serverzone→旁挂）。"""
    nl = (note or '').lower()
    if any(w in nl for w in ('数据中心', '服务器区', 'dmz', '服务器前')):
        cluster = any(w in nl for w in ('集群', '双机', '热备', 'ha', '主备', '双主', '主主'))
        return {'form': 'cluster' if cluster else 'single', 'pos': 'serverfront',
                'label': '边界串接', 'long': '数据中心边界串接（核心与服务器区之间）'}
    if any(w in nl for w in ('集群', '双机', '热备', 'ha', '主备', '双主', '主主')):
        pos = 'bypass' if any(w in nl for w in ('旁挂', '旁路', '镜像')) else 'up'
        size = _cluster_size(nl)
        return {'form': 'cluster', 'pos': pos, 'label': '双机热备' if size == 2 else '集群(%d台)' % size,
                'long': ('集群并排部署在出口：成员互联双心跳（心跳线×2 聚合，如 eth5/eth6），'
                         '上联运营商线路（交叉布线）、下联内网，主备/主主协同') if pos == 'up'
                        else '集群旁挂部署在主链路侧位，成员互联双心跳，不改变现有流量路径'}
    if any(w in nl for w in ('出口', '路由器上', '网关上', '互联网', '外网')):
        return {'form': 'single', 'pos': 'up', 'label': '出口路由',
                'long': '出口部署（路由模式，做出口网关）'}
    if any(w in nl for w in ('透明', '串接', '串联', '网桥', '虚拟网线', 'bridge')):
        return {'form': 'single', 'pos': 'down', 'label': '透明网桥',
                'long': '透明串接（网桥模式，接在网关与内网之间充当二层交换机）'}
    if any(w in nl for w in ('旁挂', '旁路', '镜像', 'onearm', 'bypass', '引流', '监听')):
        return {'form': 'single', 'pos': 'bypass', 'label': '旁挂接入',
                'long': '旁挂接入（镜像/引流，不改变主链路）'}
    mode = SANGFOR_DEVICES[key]['mode']
    if mode == 'inline':
        return {'form': 'single', 'pos': 'up', 'label': '出口路由', 'long': '出口部署（路由模式，设备默认）'}
    if mode == 'serverzone':
        return {'form': 'single', 'pos': 'bypass', 'label': '服务器区旁挂', 'long': '旁挂部署在服务器区/办公网可达位置'}
    return {'form': 'single', 'pos': 'bypass', 'label': '旁挂接入', 'long': '旁挂接入（设备默认，镜像/引流）'}


def build_planned_devices(planned):
    """把工程师声明的上架设备清单规范化：[{key,type,note}]，key 为类型缩写。
    未识别的类型按自定义设备处理。返回 (规范化列表, 无法识别提示)。"""
    norm, unknown = [], []
    for item in (planned or [])[:12]:
        key = str(item.get('type') or item.get('key') or '').strip().upper()
        note = str(item.get('note', '')).strip()
        if not key:
            continue
        if key in SANGFOR_DEVICES:
            norm.append({'key': key, 'note': note})
        else:
            unknown.append(key)
    return norm, unknown


def _resolve_mode(key, note):
    """设备实际部署方式：知识表默认 + 工程师期望词覆盖。
    含「出口」→ 强制出口位由上层判断；此处只区分链路形态：
    串接/网桥/透明 → inline；旁挂/旁路/镜像 → bypass；否则用知识表默认。"""
    nl = (note or '').lower()
    if any(w in nl for w in ('串接', '串联', '网桥', '透明', 'inline', 'bridge')):
        return 'inline'
    if any(w in nl for w in ('旁挂', '旁路', '镜像', 'onearm', 'bypass')):
        return 'bypass'
    return SANGFOR_DEVICES[key]['mode']


def build_real_network(real, extra_subnets=None, snmp=None, planned=None):
    """真实感知：ping 扫描本机网段（可加工程师手填的其他网段/多网卡网段批量）
    + ARP 厂商指纹 + 端口探测（9100/631/515/445/22/3389/8443）。
    snmp={'community','version','ip'}：提供则尝试 SNMP 读交换机（sysDescr 探活 + MAC 地址表），
    拿到即生成 kind='snmp-real' 的实测物理链路；拿不到保持逻辑推演（kind='access'）并附说明。
    planned：工程师声明的上架设备清单（见 SANGFOR_DEVICES），逐台在拓扑上建模；
    未声明时默认建模一台深信服 AF（与原行为一致）。
    【如实标注】除「规划部署」节点（为施工建议而建模）外，
    所有节点与主机均为实测数据；关闭 ICMP 的设备可能未被感知。"""
    base = '.'.join(real['ip'].split('.')[:3])
    prefix = mask_to_prefix(real['mask'])

    live = ping_sweep(base)
    arp = read_arp_table()
    if real['ip'] not in live:
        live.append(real['ip'])

    # ARP 有记录但首轮 ping 未响应的同网段主机：多半只是响应慢，用长超时重试一次
    candidates = [ip for ip in arp
                  if ip.startswith(base + '.') and not ip.endswith('.255')
                  and ip not in live and ip != real['gateway']]
    if candidates:
        with ThreadPoolExecutor(max_workers=16) as ex:
            retried = list(ex.map(lambda ip: ping_alive(ip, 800), candidates))
        live.extend(ip for ip, ok in zip(candidates, retried) if ok)

    gw_ok = real['gateway'] in live or real['gateway'] in arp
    others = sorted((ip for ip in live if ip not in (real['ip'], real['gateway'])),
                    key=lambda x: [int(p) for p in x.split('.')])

    with ThreadPoolExecutor(max_workers=32) as ex:
        fps = list(ex.map(fingerprint_host, others))

    printers = [fp for fp in fps if fp['printer_port']]
    terminals = [fp for fp in fps if not fp['printer_port']]

    def vendor_of(ip):
        return mac_vendor(arp.get(ip, ''))

    # ---- 规划部署建模（按工程师声明的部署方式逐台建模）----
    # 位置语义（_resolve_deploy：设备默认 + 工程师期望词共同决定）：
    #   up          = 出口位：互联网与出口网关之间（「出口」及双机/集群默认）
    #   down        = 透明串接位：出口网关与内网之间（「透明/串接/网桥」，充当二层交换机）
    #   serverfront = 服务器区前串接位（「数据中心/服务器区」，归入 down 链，标签为边界串接）
    #   bypass      = 旁挂位：主链路侧位（「旁挂/旁路/镜像/引流」，不改变主链路）
    # 链路顺序：互联网 → up 链 → 出口网关 → down 链 → 内网终端（终端接在 down 链末端之下）
    # 双机/集群（form=cluster）：成员同层并排建模，互联两条心跳线（心跳线×2 聚合），
    #   上联/下联各成员独立出线（交叉布线），对应附件二双机方案的口字型/全交叉形态。
    planned_norm, planned_unknown = build_planned_devices(planned)
    if not planned_norm:
        planned_norm = [{'key': 'AF', 'note': ''}]
    planned_ids = []           # 供部署建议使用：[{id,key,note,info,mode,pos,dep,members}]
    nodes = [
        {'id': 'net', 'layer': 0, 'tier': 0, 'icon': '☁️', 'name': '互联网', 'role': 'isp', 'ip': '', 'conf': '—'},
        {'id': 'gw', 'layer': 99, 'tier': 1, 'icon': '🔗', 'name': '出口网关/路由', 'role': 'gateway',
         'ip': real['gateway'], 'vendor': vendor_of(real['gateway']) or '—',
         'mac': arp.get(real['gateway'], ''),
         'conf': '实测（网关，ping %s）' % ('通' if gw_ok else '未响应')},
    ]
    links = []

    def _plan_node(dev_id, d, member_no, layer):
        dep = d['dep']
        name = ('%s（%s）' % (d['info']['name'], member_no)) if member_no \
            else ('%s（规划部署）' % d['info']['name'])
        nodes.append({'id': dev_id, 'layer': layer, 'tier': layer, 'icon': d['info']['icon'],
                      'name': name, 'role': 'sangfor',
                      'ip': '管理 IP 待规划', 'vendor': '深信服', 'conf': '规划部署',
                      'plan_key': d['key'], 'plan_note': d['note'], 'pos': dep['pos'],
                      'deploy': dep['label'], 'deploy_long': dep['long'], 'form': dep['form']})

    def _register(d, dev_id, member_no, layer, mode, members=2):
        planned_ids.append({'id': dev_id, 'key': d['key'], 'note': d['note'], 'info': d['info'],
                            'mode': mode, 'pos': d['dep']['pos'], 'dep': d['dep'],
                            'member': member_no, 'members': members})

    # ---- 集群归组：部署规划里连续声明的同类「集群」台 = 一个集群的各成员 ----
    # 具体几台以工程师声明的台数为准：相邻两台备注「集群」→ 一个双机集群（成员=2）；
    # 单台声明且备注写明台数（如「集群 3台」）→ 展开 3 台；单台未写台数 → 默认双机。
    resolved = []
    for pd in planned_norm:
        resolved.append({'key': pd['key'], 'note': pd['note'],
                         'info': SANGFOR_DEVICES[pd['key']],
                         'dep': _resolve_deploy(pd['key'], pd['note'])})

    groups = []          # [{'items':[声明...], 'size':成员数, 'cluster':bool, 'pos':位置}]
    for it in resolved:
        dep = it['dep']
        if dep['form'] != 'cluster':
            groups.append({'items': [it], 'size': 1, 'cluster': False, 'pos': dep['pos']})
            continue
        prev = groups[-1] if groups else None
        if prev and prev['cluster'] and prev['items'][0]['key'] == it['key'] \
                and prev['pos'] == dep['pos']:
            prev['items'].append(it)           # 连续同类声明 = 同一集群的下一个成员
            prev['size'] = len(prev['items'])
        else:
            groups.append({'items': [it], 'size': _cluster_size(it['note']),
                           'cluster': True, 'pos': dep['pos']})

    up_groups, down_groups, bypass_groups = [], [], []
    for g in groups:
        if g['pos'] == 'bypass':
            bypass_groups.append(g)
        elif g['pos'] in ('down', 'serverfront'):
            down_groups.append(g)
        else:
            up_groups.append(g)
    n_cgroups = sum(1 for g in groups if g['cluster'])
    for g in groups:   # 归组后按组内实际台数修正部署方式标签
        if g['cluster'] and len(g['items']) > 1:
            for it in g['items']:
                it['dep']['label'] = '双机热备' if g['size'] == 2 else '集群(%d台)' % g['size']

    # ---- 单台声明高可用且未注明台数：降级为单台建模，并返回提示让工程师补足 ----
    # 「双机/双机热备/热备/HA」单台 → 提示：双机高可用需要两台设备！
    # 「集群」单台未写台数 → 提示：集群至少需要两台设备！（写明台数如「集群 3台」则按台数展开）
    cluster_hints = []
    for g in groups:
        if not g['cluster'] or len(g['items']) > 1:
            continue
        lead = g['items'][0]
        nl = (lead['note'] or '').lower()
        if re.search(r'\d+\s*台', nl) or any(w in nl for w in ('两台', '三台', '四台')):
            continue   # 注明了台数，按台数展开
        g['cluster'] = False
        g['size'] = 1
        lead['dep']['form'] = 'single'
        dev = lead['info']['name']
        if any(w in nl for w in ('双机', '热备', 'ha')):
            cluster_hints.append('%s：双机高可用需要两台设备！请在部署规划中再添加一台（备注「双机」或「集群」）。' % dev)
        else:
            cluster_hints.append('%s：集群至少需要两台设备！请再添加一台，或注明台数（如「集群 3台」）。' % dev)

    def _build_chain(chain_groups, start_members, start_layer, first_label, step_label, kind):
        """逐组串接一条链：普通设备单节点占一层；集群组内各成员同层并排、互联双心跳、
        上/下联各成员独立出线。返回 (末端成员列表, 末层号)。"""
        members = list(start_members)
        layer = start_layer
        gseq = 0
        for g in chain_groups:
            layer += 1
            gseq += 1
            if g['cluster']:
                size = g['size']
                lead = g['items'][0]
                tag = lambda k: (('集群%d-' % gseq if n_cgroups > 1 else '集群-') + str(k)) if size > 1 else ''
                ids = []
                for k in range(size):
                    dev_id = 'plan%d' % len(planned_ids)
                    ids.append(dev_id)
                    d = g['items'][k] if k < len(g['items']) else lead
                    _plan_node(dev_id, d, tag(k + 1), layer)
                    _register(d, dev_id, (k + 1) if size > 1 else 0, layer, 'inline', size)
                for pid in members:            # 上联（多成员×多成员即交叉布线）
                    for j, dev_id in enumerate(ids):
                        links.append({'from': pid, 'to': dev_id,
                                      'label': (first_label if j == 0 else ''), 'kind': kind})
                for k in range(size - 1):      # 成员互联双心跳（心跳线×2 聚合）
                    links.append({'from': ids[k], 'to': ids[k + 1], 'label': '心跳线', 'kind': 'ha'})
                    links.append({'from': ids[k + 1], 'to': ids[k], 'label': '', 'kind': 'ha'})
                members = ids
            else:
                d = g['items'][0]
                dev_id = 'plan%d' % len(planned_ids)
                _plan_node(dev_id, d, '', layer)
                _register(d, dev_id, 0, layer, 'inline', 1)
                for pid in members:
                    links.append({'from': pid, 'to': dev_id,
                                  'label': first_label if pid == members[0] else '', 'kind': kind})
                members = [dev_id]
        return members, layer

    # up 出口链：互联网→up设备们→出口网关（集群两台并排+双心跳）
    up_members, seq = _build_chain(up_groups, ['net'], 0, '出口链路', '出口链路', 'uplink')
    for pid in up_members:
        links.append({'from': pid, 'to': 'gw', 'label': '出口链路' if pid == up_members[0] else '',
                      'kind': 'uplink'})
    gw_layer = seq + 1
    next(n for n in nodes if n['id'] == 'gw')['layer'] = gw_layer

    # down 串接链：出口网关→down设备们（透明网桥/数据中心边界）→内网
    down_members, gw_layer = _build_chain(
        down_groups, ['gw'], gw_layer, '规划串接', '规划串接', 'plan')

    # 旁挂设备：挂在 down 链末端（无 down 设备则出口网关）侧位
    bypass_anchor = down_members[0]
    for g in bypass_groups:
        if g['cluster']:
            size = g['size']
            lead = g['items'][0]
            ids = []
            for k in range(size):
                dev_id = 'plan%d' % len(planned_ids)
                ids.append(dev_id)
                d = g['items'][k] if k < len(g['items']) else lead
                _plan_node(dev_id, d, (str(k + 1) if size > 1 else ''), gw_layer)
                _register(d, dev_id, (k + 1) if size > 1 else 0, gw_layer, 'bypass', size)
            for k, dev_id in enumerate(ids):
                links.append({'from': bypass_anchor, 'to': dev_id,
                              'label': '旁挂接入' if k == 0 else '', 'kind': 'bypass'})
            for k in range(size - 1):
                links.append({'from': ids[k], 'to': ids[k + 1], 'label': '心跳线', 'kind': 'ha'})
                links.append({'from': ids[k + 1], 'to': ids[k], 'label': '', 'kind': 'ha'})
        else:
            d = g['items'][0]
            dev_id = 'plan%d' % len(planned_ids)
            _plan_node(dev_id, d, '', gw_layer)
            _register(d, dev_id, 0, gw_layer, 'bypass', 1)
            links.append({'from': bypass_anchor, 'to': dev_id, 'label': '旁挂接入', 'kind': 'bypass'})

    # 内网设备逻辑接入点：down 链末端（无 down 设备则出口网关）
    inner_from = down_members[0]

    # 出口链路自上而下：互联网→出口网关；串接链在出口网关下方（互联网→出口网关→串接设备…）


    n_term = len(terminals)
    nodes.append({'id': 'pc', 'layer': gw_layer + 2, 'tier': 5, 'icon': '💻',
                  'name': '在线终端 ×%d' % n_term if n_term else '未发现其他终端',
                  'role': 'clients', 'ip': '%s.0/%d' % (base, prefix), 'conf': '实测（ping 扫描）'})
    links.append({'from': inner_from, 'to': 'pc', 'label': '内网接入', 'kind': 'access'})

    for i, fp in enumerate(printers):
        nodes.append({'id': 'prt%d' % (i + 1), 'layer': gw_layer + 2, 'tier': 5, 'icon': '🖨️',
                      'name': '打印机 %s' % fp['ip'].rsplit('.', 1)[1], 'role': 'printer',
                      'ip': fp['ip'], 'vendor': vendor_of(fp['ip']) or '—',
                      'mac': arp.get(fp['ip'], ''),
                      'conf': '实测（%s 开放）' % PRINTER_PORT_NAME[fp['printer_port']]})
        links.append({'from': inner_from, 'to': 'prt%d' % (i + 1), 'label': 'Access', 'kind': 'access'})

    nodes.append({'id': 'me', 'layer': gw_layer + 2, 'tier': 5, 'icon': '🧑‍🔧', 'name': '工程师本机', 'role': 'self',
                  'ip': real['ip'], 'mac': real['mac'], 'conf': '实测'})
    links.append({'from': inner_from, 'to': 'me',
                  'label': 'Wi-Fi' if real['conn_type'] == 'wifi' else '有线',
                  'kind': 'wireless' if real['conn_type'] == 'wifi' else 'access'})

    subnets = [{'cidr': '%s.0/%d' % (base, prefix), 'vlan': '1（默认）',
                'name': '本机所在办公网段', 'gateway': real['gateway'],
                'hosts': len(live), 'dhcp': real['dhcp']}]

    # ---- 多网段扩展：工程师手填的其他网段 + 本机多网卡网段，批量并入扫描 ----
    # 主机清单：普通终端（网关/打印机/本机已在拓扑节点中，避免重复）；扩展网段主机也会并入
    hosts = []
    extra_notes = []
    scanned_extra = []                     # [(prefix,bits)]
    for text in (extra_subnets or []):
        parsed = parse_subnet(text)
        if parsed and parsed not in scanned_extra and parsed != (base, prefix):
            scanned_extra.append(parsed)
        elif not parsed:
            extra_notes.append('网段「%s」格式无法识别，已跳过（示例：192.168.20.0/24）' % text)
    # 多网卡：自动并入本机其余【物理】网卡的网段；虚拟网卡（VirtualBox/VMware 等宿主私有网段）
    # 不是客户内网，自动扫描时排除，保证结果真实客观（工程师手动填了才扫，且会标注）
    for cand in local_nic_subnets():
        key = (cand['prefix'], cand['bits'])
        if key == (base, prefix) or key in scanned_extra:
            continue
        if cand['virtual']:
            extra_notes.append('已跳过本机虚拟网卡网段 %s.0/%d（VirtualBox 等宿主私有网段，不属于客户内网）'
                               % (cand['prefix'], cand['bits']))
            continue
        scanned_extra.append(key)
        extra_notes.append('检测到本机多网卡网段 %s.0/%d，已自动并入扫描' % (cand['prefix'], cand['bits']))

    remote_hosts_total = 0
    for gi, (pfx, bits) in enumerate(scanned_extra, start=1):
        seg_live = [ip for ip in ping_sweep(pfx) if ip != real['ip']]
        with ThreadPoolExecutor(max_workers=24) as ex:
            seg_fps = list(ex.map(fingerprint_host, seg_live))
        seg_prn = [fp for fp in seg_fps if fp['printer_port']]
        seg_term = [fp for fp in seg_fps if not fp['printer_port']]
        remote_hosts_total += len(seg_live)
        subnets.append({'cidr': '%s.0/%d' % (pfx, bits), 'vlan': '—（手填/多网卡网段）',
                        'name': '扩展扫描网段 %d' % gi, 'gateway': '—',
                        'hosts': len(seg_live), 'dhcp': '未探测'})
        # 每个扩展网段生成一个聚合节点挂到核心层下；若该段是本机虚拟网卡段则如实标注
        nid = 'xnet%d' % gi
        is_virt_seg = pfx.startswith(('192.168.56.',))   # VirtualBox Host-Only 等知名虚拟段
        conf_txt = ('工程师指定网段 批量 ping' + ('；注意：此段为本机虚拟网卡网段（宿主私有），非客户内网设备' if is_virt_seg else ''))
        nodes.append({'id': nid, 'layer': gw_layer + 2, 'tier': 5, 'icon': '🕸️',
                      'name': ('跨网段终端 ×%d' % len(seg_live)) if seg_live else '跨网段 %s（无响应）' % pfx.rsplit('.', 1)[0],
                      'role': 'clients', 'ip': '%s.0/%d' % (pfx, bits),
                      'conf': ('实测（%s）' % conf_txt) if seg_live else '实测（无在线响应）'})
        links.append({'from': inner_from, 'to': nid, 'label': '跨网段 Access', 'kind': 'access'})
        for fp in seg_prn:
            nodes.append({'id': 'xprt%d_%d' % (gi, len(nodes)), 'layer': gw_layer + 2, 'tier': 5, 'icon': '🖨️',
                          'name': '打印机 %s' % fp['ip'].rsplit('.', 1)[1], 'role': 'printer',
                          'ip': fp['ip'], 'vendor': vendor_of(fp['ip']) or '—', 'mac': arp.get(fp['ip'], ''),
                          'conf': '实测（%s 开放）' % PRINTER_PORT_NAME[fp['printer_port']]})
        for fp in seg_term[:8]:
            hosts.append({'ip': fp['ip'],
                          'type': fp['label'] or ('Windows 终端（SMB）' if fp['smb'] else '在线终端'),
                          'vendor': vendor_of(fp['ip']) or '—', 'mac': arp.get(fp['ip'], ''),
                          'conf': '实测（扩展网段）'})

    # ---- SNMP：读交换机生成实测物理链路（失败降级为逻辑推演并如实标注） ----
    snmp_info = {'used': False, 'note': '未提供 SNMP 参数：连线为「逻辑推演」，非实测物理链路。'}
    if snmp and snmp.get('community'):
        target_ip = snmp.get('ip') or real['gateway']
        ver = snmp.get('version') or 'v2c'
        if ver == 'v3':
            snmp_info = {'used': False,
                         'note': 'SNMP v3 需要 USM 加密（超出本工具纯标准库范围），请改用 v2c 或在交换机上临时开 v2c 只读账号。'}
        else:
            probe = snmp_probe_switch(target_ip, snmp['community'], ver)
            if probe.get('ok'):
                macs = snmp_read_mac_table(target_ip, snmp['community'], ver)
                if macs.get('ok'):
                    snmp_info = {'used': True, 'ip': target_ip, 'mac_count': len(macs['macs']),
                                 'sysdescr': probe.get('sysdescr', ''),
                                 'note': 'SNMP 实测：%s 读到 %d 条 MAC 地址表记录，交换机下行连线为实测物理链路。'
                                         % (target_ip, len(macs['macs']))}
                    # gw→交换机(snmp交换节点)→终端 的物理链路：交换机节点以 SNMP 实测标注
                    nodes.append({'id': 'sw', 'tier': 2, 'icon': '🔀', 'name': '交换机（SNMP 实测）',
                                  'role': 'switch', 'ip': target_ip,
                                  'vendor': vendor_of(arp.get(target_ip, '')) or '—',
                                  'conf': 'SNMP 实测（%s）' % (probe.get('sysdescr') or 'sysDescr 可达')})
                    links.append({'from': 'gw', 'to': 'sw', 'label': '物理链路（SNMP）', 'kind': 'snmp-real'})
                    # 把原「sf→pc 接入」改为经交换机的实测物理链路
                    for lk in links:
                        if lk.get('from') == inner_from and lk.get('to') == 'pc':
                            lk['from'] = 'sw'
                            lk['label'] = '物理链路（SNMP）'
                            lk['kind'] = 'snmp-real'
                else:
                    snmp_info = {'used': False, 'ip': target_ip,
                                 'note': 'SNMP 探活成功但 MAC 地址表读取失败（权限/版本/表为空），连线仍为「逻辑推演」。'}
            else:
                snmp_info = {'used': False, 'ip': target_ip,
                             'note': 'SNMP 连接失败（团体字/版本/IP 不对或交换机未开 SNMP），连线仍为「逻辑推演」。'}

    # 主机清单：仅普通终端（网关/打印机/本机已在拓扑节点中，避免重复）
    for fp in terminals:
        hosts.append({'ip': fp['ip'],
                      'type': fp['label'] or ('Windows 终端（SMB）' if fp['smb'] else '在线终端'),
                      'vendor': vendor_of(fp['ip']) or '—',
                      'mac': arp.get(fp['ip'], ''), 'conf': '实测'})

    # 拓扑呈现真实探测结果 + 工程师声明的规划部署设备（逐台建模），不做其他经验推测

    scn = {'flat': not scanned_extra, 'multi_subnet': bool(scanned_extra), 'n_hosts': n_term,
           'n_printers': len(printers), 'gw_ok': gw_ok,
           'extra_notes': extra_notes, 'snmp': snmp_info,
           'remote_hosts': remote_hosts_total,
           'planned': planned_norm, 'planned_unknown': planned_unknown,
           'cluster_hints': cluster_hints,
           'scope': ('本机所在网段 %s.0/%d' % (base, prefix)) if not scanned_extra
                    else ('本机网段 + %d 个扩展网段' % len(scanned_extra)),
           'has_wireless': real['conn_type'] == 'wifi', 'me_wifi': real['conn_type'] == 'wifi'}
    return {'nodes': nodes, 'links': links, 'subnets': subnets, 'hosts': hosts,
            'scenario': scn, 'planned_ids': planned_ids}


def build_deployment_advice(real, net, planned_ids=None):
    """根据实测环境生成深信服设备部署模式建议（规则引擎）。
    planned_ids：工程师声明的上架设备（已建模），逐台生成针对性建议。"""
    scn = net['scenario']
    n_hosts, n_prt = scn['n_hosts'], scn['n_printers']

    mode, alt = '网桥（透明串接）模式', '路由模式'
    planned_ids = planned_ids or []
    has_dev = bool(planned_ids)
    reasons = [
        '实测为单网段平面网络（网段 %s，网关 %s），终端无需变更网关即可生效' % (
            net['subnets'][0]['cidr'], real['gateway']),
        '实测在线终端 %d 台%s，业务以出口上网为主，串接无需改动内网路由' % (
            n_hosts, ('，其中打印机 %d 台' % n_prt) if n_prt else ''),
        '透明串接不改变现有 IP/路由规划，割接窗口最短，回退只需跳过设备直接对接',
    ]
    planning = []
    if not has_dev:
        planning.append('AF 部署位置（拓扑中已用橙色虚线标出）：接在出口路由器 %s 下方（网桥/透明串接模式），内网侧下联交换与终端；路由器位置与 IP 规划均不变' % real['gateway'])
    else:
        forms = []
        for p in planned_ids:
            dep = p.get('dep') or {}
            tag = dep.get('long') or dep.get('label') or p.get('pos') or '旁挂'
            if p.get('members', 0) > 1 and p.get('member') and p.get('member') > 1:
                continue   # 集群只在 1 号成员上报一次
            forms.append('%s：%s' % (p['info']['name'], tag))
        if forms:
            planning.append('本轮规划 %d 台设备的部署方式（拓扑中橙色虚线已按各自方式建模）：%s' % (
                len(planned_ids), '；'.join(forms)))
    planning.append('管理地址：在本网段预留一个固定 IP（建议避开实测已发现的在线设备地址）')
    planning.append('上线路径：先物理旁挂观察流量，割接窗口内再串接生效')
    if any((p.get('dep') or {}).get('form') == 'cluster' for p in planned_ids):
        planning.append('双机/集群要点：两台并排上架，互联两条心跳线（建议心跳线×2 聚合，如 eth5/eth6 或聚合口），'
                        '上联运营商线路交叉布线、下联内网；业务口避开硬件 bypass 对（eth0+eth1、eth2+eth3），防止关机成环')
    if n_prt:
        planning.append('打印机放行：放行 %d 台实测打印机的打印端口（9100/631/515），与办公终端同策略' % n_prt)
    if scn['has_wireless']:
        planning.append('现场存在无线网络（本机经 Wi-Fi 接入）；如后续上无线安全组件，可与 AF 统一规划')

    # ---- 逐台设备建议：按类型给出部署位置/模式/功能配置要点，并结合工程师填写的期望 ----
    device_advices = []
    for p in planned_ids:
        info = p['info']
        dep = p.get('dep') or {}
        pos, form = dep.get('pos'), dep.get('form')
        # 优先按工程师声明的部署方式生成位置说明（与拓扑建模一致）
        if form == 'cluster':
            loc = dep.get('long', '集群并排部署在出口，成员互联双心跳（心跳线×2 聚合），上联运营商线路交叉布线、下联内网')
        elif pos == 'up':
            loc = '互联网与出口网关 %s 之间，路由模式做出口网关（NAT/安全策略/VPN）' % real['gateway']
        elif pos == 'down':
            loc = '串接在出口网关 %s 与内网之间（透明网桥，充当二层交换机），内网终端接于其下，不改 IP/路由' % real['gateway']
        elif pos == 'serverfront':
            loc = '串接在核心交换与服务器区之间，做数据中心边界防护'
        elif p['key'] == 'AC':
            loc = '旁挂在核心/接入交换机侧（经镜像或引流审计全部上网流量），不改变现有路由'
        elif p['key'] == 'AD':
            loc = '互联网多线接入与服务器区之间（链路/服务器负载均衡）'
        elif p['key'] == 'VDC':
            loc = '服务器区旁挂，配套 aDesk 云终端交付桌面'
        elif p['key'] == 'SSL':
            loc = '出口区旁挂/串接，对外发布远程接入入口'
        elif p['key'] == 'WOC':
            loc = '出口链路串接（对端出口需成对部署）'
        elif p['key'] == 'XAC':
            loc = '服务器区/云管理网旁挂，按业务编排安全资源'
        else:
            loc = '结合组网实际选择接入位置（建议先旁挂观察）'
        steps = [
            '部署位置：%s' % loc,
            '设备定位：%s（%s）' % (info['full'], info['summary']),
            '上架顺序：先旁挂/观察 → 确认业务正常 → 再按需串接生效',
            '管理配置：预留固定管理 IP（避开实测在线地址 %s 等已占用地址）' % real['gateway'],
        ]
        if form == 'cluster':
            steps.append('集群布线：两台并排上架，互联两条心跳线（心跳线×2 聚合，如 eth5/eth6）；'
                         '上联线路交叉接到两台，下联内网各出一条；AF 业务口避开 bypass 对（eth0+eth1、eth2+eth3）')
        if p['note']:
            steps.append('工程师期望（已在拓扑规划中参考）：%s' % p['note'])
        dev_name = info['name'] + ('（集群-%d）' % p['member'] if p.get('member') else '')
        device_advices.append({'id': p['id'], 'key': p['key'], 'name': dev_name,
                               'full': info['full'], 'icon': info['icon'],
                               'deploy': info['deploy'], 'steps': steps})

    risks = [
        '实施前必须备份：出口网关与内网交换机配置各导出一份',
        '确认网关 %s 的 ARP/会话表在割接后正常收敛（观察 30 分钟）' % real['gateway'],
        '实测内网在线主机 %d 台，策略放行遵循"先观察后收紧"原则' % (n_hosts + n_prt + 1),
    ]
    checklist = ['确认本次上架设备的型号、授权与版本基线', '与客户确认变更窗口和回退责任人',
                 '梳理接口/VLAN 互联表并双方签字确认', '准备 Console 线与带外管理通道',
                 '实施前完成安全基线加固（改默认口令、开启日志上送、关闭无用服务）',
                 '割接后按清单逐项验证业务（上网 / 打印 / 内网访问）']
    return {'mode': mode, 'alternative': alt, 'reasons': reasons, 'planning': planning,
            'risks': risks, 'checklist': checklist,
            'device_advices': device_advices, 'deploy_note': net.get('deploy_note', ''),
            'wireless_note': ('现场实测存在无线网络（本机即经 Wi-Fi 接入）；AC/AP 细节感知需 SNMP/管理权限，'
                              '本次以出口与终端实测数据为准。' if scn['has_wireless'] else
                              '当前为有线接入，未感知无线控制器；如现场有无线网络，AC 旁挂方案可与 AF 同步规划。'),
            'me_access': '当前通过 Wi-Fi 接入现场网络，感知基于无线链路完成；正式串接割接建议临时接有线到待配设备管理口。'
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
        for enc in ('utf-8', 'gbk'):       # GBK 回退：兼容非 UTF-8 客户端
            try:
                data = json.loads(raw.decode(enc))
                return data if isinstance(data, dict) else {}
            except Exception:
                continue
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
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
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
        elif path == '/api/sangfor/devices':
            # 深信服设备知识表（供部署规划下拉与说明）
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            devs = [{'key': k, 'name': v['name'], 'full': v['full'],
                     'summary': v['summary'], 'deploy': v['deploy']}
                    for k, v in SANGFOR_DEVICES.items()]
            return self.send_json({'ok': True, 'devices': devs})
        elif path == '/api/topology/nics':
            # 枚举本机全部网卡网段（多网卡批量扫描用）；虚拟网卡(Host-Only等)单独标注不参与
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            nics = local_nic_subnets()
            real = ['%s.0/%d' % (n['prefix'], n['bits']) for n in nics if not n['virtual']]
            virt = ['%s.0/%d' % (n['prefix'], n['bits']) for n in nics if n['virtual']]
            return self.send_json({'ok': True, 'subnets': real, 'virtual_subnets': virt})
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
                            'engine': 'ICMP+ARP+OUI+Port'})
        elif path in ('/speedtest.html', '/diagnose.html', '/review.html', '/topology.html'):
            if not self.current_user():
                self.redirect('/')
            else:
                self.send_file(path.lstrip('/'))
        elif path == '/api/speedtest/echo':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            lip = read_local_nic() or {}
            self.send_json({'t': time.time(), 'ip': self.client_address[0],
                            'local_ip': lip.get('ip', ''), 'host': socket.gethostname()})
        elif path == '/api/speedtest/nics':
            # 全网卡清单：内网测速「选线路」下拉（多网卡=多线路，按网卡针对性测试）
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            nics = list_all_nics()
            return self.send_json({'ok': True, 'nics': nics,
                                   'active': read_local_nic()})
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
        elif path == '/api/speedtest/hops':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_hops(urllib.parse.urlparse(self.path).query)
        elif path == '/api/speedtest/link':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_link()
        elif path == '/api/speedtest/cpu':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_cpu()
        elif path == '/api/speedtest/icmp':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_icmp(urllib.parse.urlparse(self.path).query)
        elif path == '/api/speedtest/browse':
            # 持续测速导出位置选择：列出本机磁盘/子文件夹/常用位置，供前端文件夹选择器使用。
            # 返回真实磁盘路径，报告由服务程序直写——零提示、与页面刷新/切换完全无关。
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            self.handle_speed_browse(urllib.parse.urlparse(self.path).query)
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
        size = os.path.getsize(real)
        rng = self.headers.get('Range')
        # 视频拖动进度条需要 Range 分段响应
        if rng and rng.startswith('bytes='):
            try:
                start_s, end_s = rng[6:].split('-', 1)
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    raise ValueError
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % size)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header('Content-Type', CONTENT_TYPES[ext])
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(end - start + 1))
            self.end_headers()
            with open(real, 'rb') as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    block = f.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
            return
        with open(real, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', CONTENT_TYPES[ext])
        if ext in ('.html', '.js', '.css'):
            # 页面与脚本经常更新：要求浏览器每次回源验证，避免改版后命中旧缓存
            self.send_header('Cache-Control', 'no-cache')
        self.send_header('Accept-Ranges', 'bytes')
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

    def handle_speed_hops(self, query):
        """逐跳时延（Windows 版 mtr）：tracert 拿路径，再对每跳并发 ping 采样统计。"""
        q = urllib.parse.parse_qs(query)
        host = str(q.get('host', [''])[0])[:64]
        if not re.match(r'^[A-Za-z0-9.\-]+$', host):
            self.send_json({'ok': False, 'message': '无效地址'}, 400)
            return
        # 1) tracert 拿路径（不解析主机名，加快）；探测超时/异常均优雅返回而非崩溃
        try:
            raw = subprocess.run(['tracert', '-d', '-h', '16', '-w', '800', host],
                                 capture_output=True, timeout=60).stdout.decode('gbk', 'replace')
        except Exception:
            self.send_json({'ok': False, 'message': '路径探测超时'})
            return
        hops = []
        seen_hops = set()
        for ln in raw.splitlines():
            # 简洁解析：行首跳号 + 行内任意位置的 IPv4（避免嵌套量词的回溯灾难）
            m = re.match(r'\s*(\d{1,2})\s', ln)
            if not m:
                continue
            n = int(m.group(1))
            if n in seen_hops:
                continue
            ips = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3})', ln)
            seen_hops.add(n)
            # 无 IP 的超时跳（* * * 行）也保留，保证跳号连续完整
            hops.append({'hop': n, 'ip': ips[-1] if ips else None})
        if not hops:
            self.send_json({'ok': False, 'message': '路径探测失败（tracert 无输出）'})
            return
        # 2) 逐跳并发 ping 采样（每跳 3 次）；单次 ping 异常按丢包计，不影响整体
        def sample(h):
            if not h['ip']:
                h['ms'] = None
                h['loss'] = 100
                return h
            lat, loss = [], 0
            for _ in range(3):
                try:
                    r = subprocess.run(['ping', '-n', '1', '-w', '800', h['ip']],
                                       capture_output=True, timeout=6)
                    t = r.stdout.decode('gbk', 'replace')
                    mm = re.search(r'[=<>]\s*(\d+)ms|时间[=<>]\s*(\d+)ms', t)
                    if mm:
                        lat.append(int(mm.group(1) or mm.group(2)))
                    else:
                        loss += 1
                except Exception:
                    loss += 1
            h['ms'] = round(sum(lat) / len(lat), 1) if lat else None
            h['loss'] = round(loss / 3 * 100)
            return h
        with ThreadPoolExecutor(max_workers=min(12, len(hops))) as ex:
            hops = list(ex.map(sample, hops))
        self.send_json({'ok': True, 'hops': hops})

    def handle_speed_link(self):
        """链路协商信息：网卡速率/双工（PowerShell Get-NetAdapter，失败静默）。"""
        info = {}
        try:
            adapters = []
            # 首选 CIM（兼容老系统与受限策略）；FullDuplex 属性部分网卡不提供
            r = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Get-CimInstance Win32_NetworkAdapter | Where-Object NetEnabled -eq $true | '
                 'ForEach-Object { $_.Name + "|" + ($_.Speed / 1e6) + " Mbps|" }'],
                capture_output=True, timeout=12)
            for ln in [x.strip() for x in r.stdout.decode('utf-8', 'replace').splitlines() if x.strip()]:
                parts = ln.split('|')
                if len(parts) >= 2:
                    try:
                        mb = float(parts[1].replace('Mbps', '').strip())
                        adapters.append({'name': parts[0][:30],
                                         'speed': ('%g Gbps' % (mb / 1000)) if mb >= 1000 else ('%g Mbps' % mb),
                                         'duplex': '—'})
                    except ValueError:
                        pass
            if not adapters:
                r2 = subprocess.run(
                    ['powershell', '-NoProfile', '-Command',
                     'Get-NetAdapter | Where-Object Status -eq "Up" | '
                     'ForEach-Object { $_.Name + "|" + $_.LinkSpeed + "|" + $_.FullDuplex }'],
                    capture_output=True, timeout=10)
                for ln in [x.strip() for x in r2.stdout.decode('utf-8', 'replace').splitlines() if x.strip()]:
                    parts = ln.split('|')
                    if len(parts) >= 3:
                        adapters.append({'name': parts[0][:30], 'speed': parts[1][:16],
                                         'duplex': '全双工' if parts[2].lower() in ('true', 'full') else '半双工'})
            if adapters:
                info = {'ok': True, 'adapters': adapters}
        except Exception:
            pass
        if not info:
            info = {'ok': False, 'adapters': []}
        info['host'] = socket.gethostname()
        self.send_json(info)

    def handle_speed_cpu(self):
        """本机 CPU/内存占用（typeperf 单次采样 + wmic 内存，零依赖）。"""
        cpu = mem = None
        try:
            r = subprocess.run(['typeperf', '\\Processor(_Total)\\% Processor Time',
                                '-sc', '1'], capture_output=True, timeout=8)
            m = re.findall(r'"([\d.]+)"', r.stdout.decode('gbk', 'replace'))
            if m:
                cpu = round(float(m[-1]))
        except Exception:
            pass
        try:
            r = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 '$os = Get-CimInstance Win32_OperatingSystem; '
                 '[math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100)'],
                capture_output=True, timeout=15)
            v = r.stdout.decode('utf-8', 'replace').strip()
            if v.isdigit():
                mem = int(v)
        except Exception:
            pass
        self.send_json({'ok': True, 'cpu': cpu, 'mem': mem})

    def handle_speed_icmp(self, query):
        """ICMP 延迟代理：对不支持 HTTP 测速的对端（网关/网络设备）测真实延迟。
        返回 ms 列表（最多 10 样本），复用系统 ping。
        src：选定网卡的 IP（ping -S 源地址），多网卡时按指定线路测。"""
        q = urllib.parse.parse_qs(query)
        host = str(q.get('host', [''])[0])[:64]
        src = str(q.get('src', [''])[0])[:15]
        try:
            n = min(max(int(q.get('n', ['4'])[0]), 1), 10)
        except ValueError:
            n = 4
        if not re.match(r'^[A-Za-z0-9.\-]+$', host):
            self.send_json({'ok': False, 'message': '无效地址'}, 400)
            return
        cmd = ['ping', '-n', '1', '-w', '1000']
        if re.match(r'^\d{1,3}(?:\.\d{1,3}){3}$', src):
            cmd += ['-S', src]      # Windows ping 指定源地址：多网卡选线路
        cmd.append(host)
        ms = []
        try:
            for _ in range(n):
                r = subprocess.run(cmd, capture_output=True, timeout=3)
                text = r.stdout.decode('gbk', 'replace')
                m = re.search(r'[=<>]\s*(\d+)ms|时间[=<>]\s*(\d+)ms', text)
                if m:
                    ms.append(int(m.group(1) or m.group(2)))
        except Exception:
            pass
        self.send_json({'ok': True, 'host': host, 'src': src, 'ms': ms})

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

    @staticmethod
    def _quick_dirs():
        """常用导出位置：桌面 / 下载 / 文档（兼容 OneDrive 重定向）。"""
        home = os.path.expanduser('~')
        candidates = {
            '桌面': ['Desktop', os.path.join('OneDrive', 'Desktop'), os.path.join('OneDrive', '桌面'), '桌面'],
            '下载': ['Downloads', os.path.join('OneDrive', 'Downloads')],
            '文档': ['Documents', os.path.join('OneDrive', 'Documents'), os.path.join('OneDrive', '文档')],
        }
        quick = []
        for name, subs in candidates.items():
            for sub in subs:
                p = os.path.join(home, sub)
                if os.path.isdir(p):
                    quick.append({'name': name, 'path': p})
                    break
        return quick

    def handle_speed_browse(self, query):
        """列出本机目录供前端选择报告导出位置：path 为空返回盘符列表，否则返回该目录下的子文件夹。
        每次响应都附带常用位置（桌面/下载/文档），前端一键直达。"""
        qs = urllib.parse.parse_qs(query)
        raw = (qs.get('path', [''])[0] or '').strip()
        quick = self._quick_dirs()
        if not raw:
            drives = []
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                p = letter + ':\\'
                try:
                    if os.path.exists(p):
                        drives.append(p)
                except OSError:
                    pass
            return self.send_json({'ok': True, 'path': '', 'parent': None, 'dirs': drives, 'quick': quick})
        p = os.path.abspath(os.path.expanduser(raw))
        if not os.path.exists(p):
            return self.send_json({'ok': False, 'message': '路径不存在：' + p}, 404)
        if not os.path.isdir(p):
            p = os.path.dirname(p)   # 传入了文件路径：取其所在文件夹
        try:
            names = sorted(os.listdir(p), key=str.lower)
        except (PermissionError, OSError) as e:
            return self.send_json({'ok': False, 'message': '无法读取该目录：' + str(e)}, 403)
        dirs = [n for n in names if not n.startswith(('.', '$')) and os.path.isdir(os.path.join(p, n))]
        parent = os.path.dirname(p)
        if parent == p:
            parent = ''   # 盘符根目录：上级 = 盘符选择层（''），仍可返回重选磁盘
        return self.send_json({'ok': True, 'path': p, 'parent': parent, 'dirs': dirs, 'quick': quick})

    def handle_speed_report(self):
        """持续测速报告导出：前端传结构化 blocks，服务端生成 Word 报告写入指定路径。
        有 python-docx 时生成真正的 .docx；否则降级为 Word 兼容 HTML（.doc）。
        路径填目录则自动命名，相对路径基于服务器工作目录（app/）。"""
        data = self.read_json()
        raw = str(data.get('path', '')).strip()
        filename = str(data.get('filename', '')).strip() or '灵犀测速-持续测速报告.docx'
        blocks = data.get('blocks')
        if not raw or not blocks:
            return self.send_json({'ok': False, 'message': '缺少导出路径或报告内容'}, 400)
        filename = re.sub(r'[\\/:*?"<>|]', '-', filename)   # Windows 文件名非法字符兜底
        try:
            p = os.path.abspath(os.path.expanduser(raw))
            if os.path.isdir(p) or p.endswith(('\\', '/')):
                p = os.path.join(p, filename)
            try:
                if not p.lower().endswith('.docx'):
                    p += '.docx'
                os.makedirs(os.path.dirname(p) or '.', exist_ok=True)   # 目录不存在时自动创建，避免写入失败
                self._write_report_docx(blocks, p)
            except ImportError:
                # 未安装 python-docx：降级为 Word 兼容 HTML（.doc，Word 可直接打开）
                p = re.sub(r'\.docx$', '', p, flags=re.I) + '.doc'
                self._write_report_html_doc(blocks, p)
        except Exception as e:
            return self.send_json({'ok': False, 'message': '写入失败：' + str(e)}, 500)
        self.send_json({'ok': True, 'path': p})

    def _write_report_docx(self, blocks, path):
        """用 python-docx 生成 Word 报告，统一排版：
        居中微软雅黑大标题 / 加粗章节标题 / 正文 1.3 倍行距 / 全宽细边框表格（表头底纹加粗居中）。
        中英文字体（ascii/hAnsi/eastAsia）全部显式声明，Word/WPS 打开不发生字体回退。"""
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_ALIGN_VERTICAL
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        doc = Document()

        def set_font(run, size, bold=False):
            run.font.name = 'Microsoft YaHei'
            run.font.size = Pt(size)
            run.font.bold = bold
            rPr = run._element.get_or_add_rPr()
            rfonts = rPr.find(qn('w:rFonts'))
            if rfonts is None:
                rfonts = OxmlElement('w:rFonts')
                rPr.append(rfonts)
            rfonts.set(qn('w:ascii'), 'Microsoft YaHei')
            rfonts.set(qn('w:hAnsi'), 'Microsoft YaHei')
            rfonts.set(qn('w:eastAsia'), '微软雅黑')

        def space_after(p, pt):
            p.paragraph_format.space_after = Pt(pt)

        # 文档默认字体（覆盖未显式设置字体的内容）
        normal = doc.styles['Normal']
        normal.font.name = 'Microsoft YaHei'
        normal.font.size = Pt(10.5)
        rpr = normal.element.get_or_add_rPr()
        rfonts = rpr.find(qn('w:rFonts'))
        if rfonts is None:
            rfonts = OxmlElement('w:rFonts')
            rpr.append(rfonts)
        rfonts.set(qn('w:ascii'), 'Microsoft YaHei')
        rfonts.set(qn('w:hAnsi'), 'Microsoft YaHei')
        rfonts.set(qn('w:eastAsia'), '微软雅黑')

        def dress_table(table):
            """全宽 + 细边框 + 单元格边距 + 表头底纹/居中/垂直居中。"""
            table.autofit = True
            tblPr = table._tbl.tblPr
            tblW = OxmlElement('w:tblW')
            tblW.set(qn('w:w'), '5000')
            tblW.set(qn('w:type'), 'pct')
            tblPr.append(tblW)
            mar = OxmlElement('w:tblCellMar')
            for side, val in (('top', '71'), ('left', '141'), ('bottom', '71'), ('right', '141')):
                el = OxmlElement('w:' + side)
                el.set(qn('w:w'), val)
                el.set(qn('w:type'), 'dxa')
                mar.append(el)
            tblPr.append(mar)
            for cell in table.rows[0].cells:
                tcPr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:fill'), 'E8EEF7')
                tcPr.append(shd)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for p in cell.paragraphs:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for b in blocks:
            t = b.get('t')
            if t == 'h1':
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(str(b.get('text', '')))
                set_font(run, 20, bold=True)
                space_after(p, 10)
            elif t == 'h2':
                p = doc.add_paragraph()
                run = p.add_run(str(b.get('text', '')))
                set_font(run, 14, bold=True)
                p.paragraph_format.space_before = Pt(14)
                space_after(p, 6)
            elif t == 'b':
                p = doc.add_paragraph(str(b.get('text', '')), style='List Bullet')
                if b.get('ind'):
                    p.paragraph_format.left_indent = Pt(10.5 * (1 + int(b['ind'])))
                p.paragraph_format.line_spacing = 1.3
                space_after(p, 4)
                for run in p.runs:
                    set_font(run, 10.5)
            elif t == 'p':
                p = doc.add_paragraph()
                run = p.add_run(str(b.get('text', '')))
                set_font(run, 10.5, bold=bool(b.get('bold')))
                p.paragraph_format.line_spacing = 1.3
                space_after(p, 6)
            elif t == 'table':
                rows = [list(map(str, r)) for r in (b.get('rows') or [])]
                if not rows or not rows[0]:
                    continue
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = 'Table Grid'
                for i, row in enumerate(rows):
                    for j, cellv in enumerate(row):
                        c = table.cell(i, j)
                        c.text = cellv
                        if i == 0:   # 表头：加粗 + 居中
                            for run in c.paragraphs[0].runs:
                                set_font(run, 10, bold=True)
                            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                        else:
                            for run in c.paragraphs[0].runs:
                                set_font(run, 10)
                dress_table(table)
        doc.save(path)

    def _write_report_html_doc(self, blocks, path):
        """降级：Word 兼容 HTML 结构，保存为 .doc（Word/WPS 可直接打开）。"""
        def esc(s):
            return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts = ['<html xmlns:w="urn:schemas-microsoft-com:office:word"><head>',
                 '<meta charset="utf-8"><title>灵犀测速报告</title><style>',
                 'body{font-family:"Microsoft YaHei","微软雅黑",sans-serif;font-size:10.5pt}',
                 'h1{text-align:center;font-size:20pt}h2{font-size:14pt;margin:14pt 0 6pt}',
                 'table{width:100%;border-collapse:collapse}th{background:#E8EEF7}td,th{border:1px solid #9AA4AE;padding:4px 6px}',
                 '</style></head><body>']
        for b in blocks:
            t = b.get('t')
            text = esc(b.get('text', ''))
            if t == 'h1':
                parts.append('<h1>' + text + '</h1>')
            elif t == 'h2':
                parts.append('<h2>' + text + '</h2>')
            elif t == 'b':
                parts.append('<p style="margin:3px 0 3px 18px">• ' + text + '</p>')
            elif t == 'p':
                parts.append('<p style="margin:6px 0;line-height:1.6">' + text + '</p>')
            elif t == 'table':
                parts.append('<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;font-size:11pt">')
                for i, row in enumerate(b.get('rows') or []):
                    tag = 'th' if i == 0 else 'td'
                    parts.append('<tr>' + ''.join('<' + tag + '>' + esc(c) + '</' + tag + '>' for c in row) + '</tr>')
                parts.append('</table>')
        parts.append('</body></html>')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(''.join(parts))

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/peer/ping':
            return self.handle_peer_ping()
        if path == '/' or path == '/login.html':
            return self.send_response(200)
        if path == '/home.html':
            return self.send_response(200 if self.current_user() else 302)
        if path in ('/speedtest.html', '/diagnose.html', '/review.html', '/topology.html'):
            return self.send_response(200 if self.current_user() else 302)
        # 静态资源存在性探测（下载前的可用性检查）
        name = path.lstrip('/')
        ext = os.path.splitext(name)[1].lower()
        if ext in CONTENT_TYPES:
            real = os.path.realpath(os.path.join(ROOT, name))
            if real.startswith(ROOT) and os.path.isfile(real):
                self.send_response(200)
                self.send_header('Content-Type', CONTENT_TYPES[ext])
                self.send_header('Content-Length', str(os.path.getsize(real)))
                self.end_headers()
                return
        self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self._peer_cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _ai_stream_reply(self, messages, scene):
        """SSE 流式回复：正文增量以 delta 事件推送，结束时发 done 事件（含全文与来源）。
        流式未产出任何内容时回退非流式生成（含演示模式），回退文本只随 done 下发，
        前端对回退文本沿用打字机动画，交互观感与原来一致。"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        def emit(ev, obj):
            try:
                self.wfile.write(('event: %s\ndata: %s\n\n'
                                  % (ev, json.dumps(obj, ensure_ascii=False))).encode('utf-8'))
                self.wfile.flush()
            except OSError:
                pass   # 客户端提前断开：停止推送即可

        def demo_reply():
            last_txt = _msg_text(messages[-1]['content'])
            return demo_review(last_txt) if scene == 'review' else demo_diagnose(last_txt)

        text = ''
        try:
            text = _llm_stream(messages, scene, lambda t: emit('delta', {'t': t})) or ''
        except Exception as e:
            # 防崩溃护栏：流式环节任何异常都降级，绝不让连接被重置
            print('[ai] 流式生成异常(已回退): %r' % e)
            text = ''
        source = 'llm'
        if not text:
            try:
                reply, source = ai_chat(messages, scene)
                if reply is None:
                    source = 'demo'
                    reply = demo_reply()
            except Exception as e:
                print('[ai] 生成回复异常(已降级): %r' % e)
                source = 'demo'
                reply = ('**抱歉，生成回复时服务内部出现异常（已自动降级，连接未中断）。**\n\n'
                         '- 请重试一次，或换一种表述再发送\n'
                         '- 若持续出现：重启 Start-CyberNWT.bat 后重试')
            text = reply
        emit('done', {'ok': True, 'source': source, 'reply': text})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/speedtest/up':
            return self.handle_speed_up()   # 二进制请求体，不能走 JSON 解析
        if path == '/peer/up':
            return self.handle_peer_up()     # 内网对端协议：二进制请求体
        if path == '/api/speedtest/report':
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            return self.handle_speed_report()
        data = self.read_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))

        if path == '/api/topology/scan':
            # 感知扫描（POST 版）：其他网段 + SNMP 参数 + 工程师声明的上架设备与部署期望
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            real = read_local_nic()
            if not real or not real.get('gateway'):
                return self.send_json(
                    {'ok': False, 'message': '未能读取本机网卡信息（未联网或非 Windows 环境）'}, 503)
            extra = data.get('extra_subnets') or []
            if not isinstance(extra, list):
                extra = []
            snmp = data.get('snmp') if isinstance(data.get('snmp'), dict) else None
            planned = data.get('planned_devices') if isinstance(data.get('planned_devices'), list) else []
            deploy_note = str(data.get('deploy_note', '')).strip()
            net = build_real_network(real, extra_subnets=[str(x) for x in extra[:8]], snmp=snmp,
                                     planned=planned)
            net['deploy_note'] = deploy_note
            advice = build_deployment_advice(real, net, planned_ids=net.get('planned_ids'))
            real['prefix'] = mask_to_prefix(real['mask'])
            self.send_json({'ok': True, 'real': real, 'topology': net,
                            'advice': advice, 'modeled': False,
                            'engine': 'ICMP+ARP+OUI+Port+SNMP(optional)+Planned'})

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

        if path == '/api/topology/ai-model':
            # 图片 → 大模型视觉识别拓扑（读图中设备名与真实连线），供「已有拓扑·建模拓扑」使用
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            if not LLM_BASE or not LLM_KEY:
                return self.send_json({'ok': False, 'message': '未接入 FastGPT，无法识别'}, 200)
            try:
                raw = base64.b64decode(str(data.get('b64', '')))
            except Exception:
                return self.send_json({'ok': False, 'message': '图片数据异常'}, 400)
            if not raw:
                return self.send_json({'ok': False, 'message': '图片内容为空'}, 400)
            if len(raw) > 8 * 1024 * 1024:
                return self.send_json({'ok': False, 'message': '图片超过 8MB，无法识别'}, 400)
            data_ai, err = recognize_topology_image(base64.b64encode(raw).decode('ascii'))
            if err or not data_ai:
                return self.send_json({'ok': False, 'message': err or '识别失败'}, 200)
            return self.send_json({'ok': True, 'data': data_ai})

        if path == '/api/doc/extract':
            # 附件解析：docx / pdf → 纯文字，供诊断助手随消息发给大模型
            if not self.current_user():
                return self.send_json({'ok': False, 'message': '未登录'}, 401)
            name = str(data.get('name', ''))
            try:
                raw = base64.b64decode(str(data.get('b64', '')))
            except Exception:
                return self.send_json({'ok': False, 'message': '文件数据异常'}, 400)
            if not raw:
                return self.send_json({'ok': False, 'message': '文件内容为空'}, 400)
            if len(raw) > 8 * 1024 * 1024:
                return self.send_json({'ok': False, 'message': '文档超过 8MB，无法解析'}, 400)
            try:
                text = extract_doc_text(name, raw)
            except ValueError as e:
                return self.send_json({'ok': False, 'message': str(e)}, 400)
            limit = 200000 if name.lower().endswith('.topo') else 6000
            return self.send_json({'ok': True, 'text': text[:limit]})

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
            if data.get('stream'):
                # 流式模式（SSE）：正文边生成边推，回退逻辑与非流式一致
                return self._ai_stream_reply(messages, scene)
            try:
                reply, source = ai_chat(messages, scene)
                if reply is None:
                    source = 'demo'
                    last_txt = _msg_text(messages[-1]['content'])
                    reply = demo_review(last_txt) if scene == 'review' else demo_diagnose(last_txt)
            except Exception as e:
                # 防崩溃护栏：演示/LLM 生成环节的任何异常都降级为 JSON 错误，
                # 绝不让连接被重置（否则前端只会看到 "Failed to fetch"）
                print('[ai] 生成回复异常(已降级): %r' % e)
                source = 'demo'
                reply = ('**抱歉，生成回复时服务内部出现异常（已自动降级，连接未中断）。**\n\n'
                         '- 请重试一次，或换一种表述再发送\n'
                         '- 若持续出现：重启 Start-CyberNWT.bat 后重试')
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
