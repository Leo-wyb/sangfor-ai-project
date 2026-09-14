# -*- coding: utf-8 -*-
"""CyberNWT 竞赛 PPT 生成器 — 深色科技风 / 含切换动画与入场动画"""
import copy
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from PIL import Image
import os

# ---------------- 主题 ----------------
BG      = RGBColor(0x05, 0x07, 0x0E)   # 深空黑蓝
BG2     = RGBColor(0x0A, 0x10, 0x20)   # 面板底
CYAN    = RGBColor(0x22, 0xD3, 0xEE)   # 主色·霓虹青
TEAL    = RGBColor(0x34, 0xD3, 0x99)   # 辅色·薄荷绿
VIOLET  = RGBColor(0xA7, 0x8B, 0xFA)   # 点缀·星云紫
PINK    = RGBColor(0xF4, 0x72, 0xB6)   # 建模·粉
AMBER   = RGBColor(0xF5, 0x9E, 0x0B)   # 警示·琥珀
TXT     = RGBColor(0xE9, 0xF1, 0xFF)   # 主文本
TXT2    = RGBColor(0x9F, 0xB2, 0xCF)   # 次文本
TXT3    = RGBColor(0x6B, 0x7C, 0x98)   # 弱文本
GRID    = RGBColor(0x16, 0x24, 0x3C)   # 网格线

FONT   = '微软雅黑'
MONO   = 'Consolas'

SW, SH = Inches(13.333), Inches(7.5)   # 16:9

PROC = r'D:\桌面\计算机网络方向\深信服sangfor\AI区域争霸赛\过程'
IMPR = r'D:\桌面\计算机网络方向\深信服sangfor\AI区域争霸赛\改进1'

prs = Presentation()
prs.slide_width  = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]

# ---------------- 底层工具 ----------------
def add_slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s

def _noline(shape):
    shape.line.fill.background()

def rect(s, x, y, w, h, fill=None, line=None, lw=1.0, shape=MSO_SHAPE.RECTANGLE, shadow=False):
    sp = s.shapes.add_shape(shape, x, y, w, h)
    sp.fill.solid(); sp.fill.fore_color.rgb = fill if fill else BG2
    if line: sp.line.color.rgb = line; sp.line.width = Pt(lw)
    else: _noline(sp)
    if not shadow: sp.shadow.inherit = False
    sp.text_frame.word_wrap = True
    return sp

def text(s, x, y, w, h, runs, size=14, color=TXT2, bold=False, align=PP_ALIGN.LEFT,
         font=FONT, line_spacing=1.15, anchor=MSO_ANCHOR.TOP, space_after=4):
    """runs: str 或 [(txt,{size,color,bold,font})...] 列表（每元素一段）"""
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if isinstance(runs, str):
        runs = [(runs, {})]
    for i, item in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(space_after)
        if isinstance(item, tuple):
            t, st = item
        else:
            t, st = item, {}
        r = p.add_run(); r.text = t
        r.font.size = Pt(st.get('size', size))
        r.font.color.rgb = st.get('color', color)
        r.font.bold = st.get('bold', bold)
        r.font.name = st.get('font', font)
        r.font._rPr.set('lang', 'zh-CN')
    return tb

def chip(s, x, y, txt_, color=CYAN, w=None):
    """小标签"""
    est = Inches(0.16 * len(txt_) + 0.24)
    w = w or est
    sp = rect(s, x, y, w, Inches(0.30), fill=BG2, line=color, lw=0.75,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    try:
        sp.adjustments[0] = 0.5
    except Exception:
        pass
    tf = sp.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = txt_
    r.font.size = Pt(10.5); r.font.color.rgb = color; r.font.bold = True; r.font.name = MONO
    return sp, w

def decor(s, section='', idx=None):
    """页面统一装饰：网格 + 顶栏 + 页码"""
    # 网格（细线矩形）
    g = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    g.fill.background(); _noline(g)
    ln = g.line; ln.color.rgb = GRID; ln.width = Pt(0.25)
    g.shadow.inherit = False
    # 用多条细线模拟网格
    g._element.getparent().remove(g._element)
    for i in range(1, 9):
        ln_ = s.shapes.add_connector(1, 0, Inches(i*0.55), SW, Inches(i*0.55))
        ln_.line.color.rgb = RGBColor(0x11, 0x1A, 0x2E); ln_.line.width = Pt(0.3)
        ln_.shadow.inherit = False
    # 顶部品牌条
    b = rect(s, 0, 0, SW, Inches(0.06), fill=CYAN)
    # 右上角章节标签
    if section:
        text(s, SW - Inches(3.2), Inches(0.18), Inches(3.0), Inches(0.3),
             section, size=10, color=TXT3, font=MONO, align=PP_ALIGN.RIGHT)
    # 页码
    if idx:
        text(s, SW - Inches(1.0), SH - Inches(0.42), Inches(0.8), Inches(0.3),
             '%02d' % idx, size=10, color=TXT3, font=MONO, align=PP_ALIGN.RIGHT)
    # 底部细线
    fl = s.shapes.add_connector(1, 0, SH - Inches(0.28), SW, SH - Inches(0.28))
    fl.line.color.rgb = RGBColor(0x14, 0x1E, 0x33); fl.line.width = Pt(0.5)
    fl.shadow.inherit = False

def sec_head(s, eyebrow, title, sub=None):
    """章节页眉：眉题 + 大标题 + 副题"""
    text(s, Inches(0.9), Inches(0.52), Inches(8), Inches(0.3),
         eyebrow, size=11, color=CYAN, font=MONO, bold=True)
    text(s, Inches(0.9), Inches(0.82), Inches(11.5), Inches(0.75),
         title, size=30, color=TXT, bold=True)
    if sub:
        text(s, Inches(0.9), Inches(1.52), Inches(11.0), Inches(0.4),
             sub, size=13, color=TXT2)
    # 标题下装饰线
    ul = s.shapes.add_connector(1, Inches(0.92), Inches(1.48), Inches(2.6), Inches(1.48))
    ul.line.color.rgb = CYAN; ul.line.width = Pt(2); ul.shadow.inherit = False

def pic_framed(s, path, x, y, w=None, h=None, border=CYAN, note=None, alpha_frame=True,
               max_h=None):
    """带科技感边框的截图：外发光边 + 底部标签条；支持 max_h 约束防溢出"""
    im = Image.open(path); iw, ih = im.size; ratio = iw / ih
    if w is None and h is None:
        w = Inches(5)
    if w is not None and h is None:
        h = Emu(int(w / ratio))
    if h is not None and w is None:
        w = Emu(int(h * ratio))
    if max_h is not None and h > max_h:
        h = max_h
        w = Emu(int(h * ratio))
        if w > Inches(12.9):
            w = Inches(12.9); h = Emu(int(w / ratio))
    # 外框（发光感用双层线框模拟）
    f1 = rect(s, x - Inches(0.05), y - Inches(0.05), w + Inches(0.1), h + Inches(0.1),
              fill=RGBColor(0x0D, 0x16, 0x28), line=border, lw=1.2)
    pic = s.shapes.add_picture(path, x, y, width=w, height=h)
    if note:
        nb = rect(s, x - Inches(0.05), y + h + Inches(0.07), w + Inches(0.1), Inches(0.32),
                  fill=RGBColor(0x0D, 0x16, 0x28), line=border, lw=0.5)
        tf = nb.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.1); tf.margin_right = Inches(0.1)
        tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        r = p.add_run(); r.text = note
        r.font.size = Pt(10); r.font.color.rgb = TXT2; r.font.name = FONT
    return pic

def glow_dot(s, x, y, color=CYAN, d=0.09):
    sp = s.shapes.add_shape(MSO_SHAPE.OVAL, x, y, Inches(d), Inches(d))
    sp.fill.solid(); sp.fill.fore_color.rgb = color; _noline(sp)
    sp.shadow.inherit = False
    return sp

# ---------------- 动画 XML ----------------
def set_transition(slide, kind='fade', ms=700):
    """页面切换动画：fade / push / wipe / split"""
    xml = (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        '<mc:Choice xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" Requires="p14">'
        f'<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="slow" p14:dur="{ms}">'
        f'<p:{kind}/></p:transition></mc:Choice>'
        '<mc:Fallback>'
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="slow">'
        f'<p:{kind}/></p:transition></mc:Fallback></mc:AlternateContent>'
    )
    from lxml import etree
    cSld = slide._element
    # transition 插在 cSld 之后
    el = etree.fromstring(xml)
    cSld.append(el)

def animate_in(slide, shape, effect='fade', delay=0, duration=500):
    """入场动画（简化版 timing 树）"""
    import uuid
    def _u():
        return str(uuid.uuid4()).upper()
    sp_id = shape.shape_id
    par = (
        f'<p:par xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<p:cTn id="{_u()}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" nodeType="afterEffect">'
        f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst>'
        f'<p:childTnLst>'
        f'<p:set>'
        f'<p:cBhvr>'
        f'<p:cTn id="{_u()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{sp_id}"/></p:tgtEl>'
        f'<p:attrNameLst><a:attrName>style.visibility</a:attrName></p:attrNameLst>'
        f'</p:cBhvr>'
        f'<p:to><p:strVal val="visible"/></p:to>'
        f'</p:set>'
        f'<p:animEffect transition="in" filter="{_FILTERS[effect]}">'
        f'<p:cBhvr>'
        f'<p:cTn id="{_u()}" dur="{duration}"/>'
        f'<p:tgtEl><p:spTgt spid="{sp_id}"/></p:tgtEl>'
        f'</p:cBhvr></p:animEffect>'
        f'</p:childTnLst></p:cTn></p:par>'
    )
    return par

_FILTERS = {
    'fade': 'fade',
    'wipe': 'wipe(right)',
    'float': 'slide(fromBottom)',
}

def build_anim(slide, shapes_with_effect):
    """为一批 shape 生成一个 timing 节点（afterEffect 链式延迟入场）"""
    from lxml import etree
    import uuid
    def _u():
        return str(uuid.uuid4()).upper()
    pars = []
    delay = 0
    for shape, effect, dur in shapes_with_effect:
        pars.append(animate_in(slide, shape, effect, delay, dur))
        delay += dur // 2
    timing = (
        '<p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:tnLst><p:par><p:cTn id="%s" dur="indefinite" restart="never" nodeType="tmRoot">'
        '<p:childTnLst><p:seq concurrent="1" nextAc="seek">'
        '<p:cTn id="%s" dur="indefinite" nodeType="mainSeq">'
        '<p:childTnLst><p:par><p:cTn id="%s" fill="hold">'
        '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
        '<p:childTnLst>%s</p:childTnLst></p:cTn></p:par></p:childTnLst>'
        '</p:cTn></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>'
        '</p:timing>'
    ) % (_u(), _u(), _u(), ''.join(pars))
    el = etree.fromstring(timing.encode())
    slide._element.append(el)

# =========================================================
# S1 封面：品牌 Logo + 主标题
# =========================================================
s = add_slide()
# 装饰网格 + 光晕
decor(s, '', None)
# 大圆环装饰（左下与右上）
ring1 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(-1.8), Inches(3.8), Inches(6), Inches(6))
ring1.fill.background(); ring1.line.color.rgb = RGBColor(0x14, 0x2A, 0x44); ring1.line.width = Pt(1.2)
ring1.shadow.inherit = False
ring2 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.6), Inches(-2.4), Inches(7), Inches(7))
ring2.fill.background(); ring2.line.color.rgb = RGBColor(0x1B, 0x2C, 0x4A); ring2.line.width = Pt(1.0)
ring2.shadow.inherit = False

# 品牌徽标（圆环 + 对勾，呼应 logo.png）
lg = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.92), Inches(0.62), Inches(1.5), Inches(1.5))
lg.fill.solid(); lg.fill.fore_color.rgb = RGBColor(0x0A, 0x0A, 0x0A)
lg.line.color.rgb = CYAN; lg.line.width = Pt(2.5); lg.shadow.inherit = False
chk = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(6.36), Inches(1.13), Inches(0.34), Inches(0.44))
chk.rotation = 45
chk.fill.solid(); chk.fill.fore_color.rgb = TEAL; _noline(chk); chk.shadow.inherit = False
# 用真 Logo
try:
    s.shapes.add_picture('logo.png', Inches(5.92), Inches(0.62), height=Inches(1.5))
except Exception:
    pass

# 主标题
t = text(s, Inches(1.5), Inches(2.45), Inches(10.33), Inches(1.5),
         [('CyberNWT', {'size': 64, 'color': TXT, 'bold': True, 'font': MONO})],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
t2 = text(s, Inches(1.5), Inches(3.75), Inches(10.33), Inches(0.6),
          [('深信服交付现场 · 智能作战终端', {'size': 24, 'color': CYAN, 'bold': True})],
          align=PP_ALIGN.CENTER)
# 英文点缀
text(s, Inches(1.5), Inches(4.35), Inches(10.33), Inches(0.4),
     'DELIVERY  FIELD  INTELLIGENCE  TERMINAL', size=12, color=TXT3, font=MONO, align=PP_ALIGN.CENTER)
# 赛道徽标
chip(s, Inches(3.4), Inches(5.0), 'SANGFOR AI 区域争霸赛', CYAN)
chip(s, Inches(5.9), Inches(5.0), 'AI 赛道', TEAL)
chip(s, Inches(7.7), Inches(5.0), 'Vibe Coding 作品', VIOLET)
# 底部信息
text(s, Inches(1.5), Inches(5.85), Inches(10.33), Inches(0.4),
     '测速 · 感知 · 记录 · 诊断 · 复盘 —— 一个终端覆盖交付全流程', size=14,
     color=TXT2, align=PP_ALIGN.CENTER)
text(s, Inches(1.5), Inches(6.6), Inches(10.33), Inches(0.35),
     '汇报人：翁炀彬   ·   AI 区域争霸赛', size=12, color=TXT3, align=PP_ALIGN.CENTER)
set_transition(s, 'fade', 900)

# =========================================================
# S2 产品介绍：定位与解决的问题
# =========================================================
s = add_slide()
decor(s, '01 / PRODUCT', 2)
sec_head(s, 'INTRODUCTION', '产品介绍：为交付现场而生的 AI 作战终端',
         '不是又一个聊天机器人，而是解决深信服交付工程师真实痛点的专用工具')

# 左：痛点（问题）
px = Inches(0.9); py = Inches(2.2); pw = Inches(5.6)
hdr = rect(s, px, py, pw, Inches(0.5), fill=RGBColor(0x1A, 0x10, 0x18), line=AMBER, lw=1)
text(s, px + Inches(0.15), py + Inches(0.09), pw - Inches(0.3), Inches(0.35),
     [('⚠ 现场交付的真实痛点', {'size': 14, 'color': AMBER, 'bold': True})])
pains = [
    ('资料难找', '设备手册、案例散落各处，现场翻文档效率低'),
    ('经验断层', '老工程师经验难沉淀，新人上手慢、排障靠碰运气'),
    ('过程难记', '实施过程与关键决策零散，复盘靠回忆、报告靠憋'),
    ('网络难测', '客户现场网络状况未知，缺乏快速透视手段'),
]
yy = py + Inches(0.66)
for name, desc in pains:
    glow_dot(s, px + Inches(0.06), yy + Inches(0.10), AMBER, 0.08)
    text(s, px + Inches(0.3), yy, pw - Inches(0.4), Inches(0.7),
         [(name + '　', {'size': 13, 'color': TXT, 'bold': True}),
          (desc, {'size': 12, 'color': TXT2})])
    yy += Inches(0.62)

# 右：方案（答案）
qx = Inches(7.0); qw = Inches(5.4)
hdr2 = rect(s, qx, py, qw, Inches(0.5), fill=RGBColor(0x0D, 0x18, 0x28), line=TEAL, lw=1)
text(s, qx + Inches(0.15), py + Inches(0.09), qw - Inches(0.3), Inches(0.35),
     [('✦ CyberNWT 的回答', {'size': 14, 'color': TEAL, 'bold': True})])
sol = [
    ('知识库沉淀', '深信服设备资料/故障案例构建专业知识库，有据可查'),
    ('AI 引导排查', '30 年经验专家智能体，一步步带工程师定位故障'),
    ('案例复盘沉淀', '项目过程输入，AI 自动生成结构化复盘报告'),
    ('全流程工具', '测速/拓扑感知/悬浮白板，交付现场一体化'),
]
yy = py + Inches(0.66)
for name, desc in sol:
    glow_dot(s, qx + Inches(0.06), yy + Inches(0.10), TEAL, 0.08)
    text(s, qx + Inches(0.3), yy, qw - Inches(0.4), Inches(0.7),
         [(name + '　', {'size': 13, 'color': TXT, 'bold': True}),
          (desc, {'size': 12, 'color': TXT2})])
    yy += Inches(0.62)

# 底部条：定位一句话
bar = rect(s, Inches(0.9), Inches(5.3), Inches(11.5), Inches(1.1),
           fill=RGBColor(0x0A, 0x14, 0x26), line=CYAN, lw=1)
text(s, Inches(1.15), Inches(5.5), Inches(11.0), Inches(0.75),
     [('定位：', {'size': 14, 'color': CYAN, 'bold': True}),
      ('面向深信服交付工程师的 AI 智能助手终端 —— 把"资料、经验、工具"装进一个本地终端，'
       '让每一次交付都有知识可查、有智能可依、有过程可溯。', {'size': 13.5, 'color': TXT})])
set_transition(s, 'fade', 700)

# =========================================================
# S3 能力总览（五大模块）
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 3)
sec_head(s, 'CAPABILITIES', '五大能力，覆盖交付全流程',
         '测速看清网络，感知看清现场，记录沉淀灵感，诊断扫清障碍，复盘萃取经验')

mods = [
    ('01', '灵犀测速', 'SPEEDLENS', '一键全链路测速：握手/延迟/突发上下行，约 4 秒出结果；实时波形 + 全链路透视 + 智能诊断结论，标准 JSON / Prometheus 输出。', CYAN),
    ('02', '内网感知', 'NETSENSE', '接入客户内网即感知：实测接入方式、网关与网段；自动生成可视化拓扑、网段/VLAN 表与设备清单，深信服设备建模部署建议。', TEAL),
    ('03', '随心记录', 'WHITEBOARD', '全站悬浮白板：右下角一键唤起，自由绘制、点击即写、截图标注，内容自动保存本地，一键导出 PNG。', VIOLET),
    ('04', '故障诊断', 'AI ASSISTANT', '对话式排查深信服设备实施故障：上架/割接/VPN/链路/无线漫游；引导式排查 + 知识库引用，可粘贴日志分析。', PINK),
    ('05', '案例复盘', 'AI REPORT', '把项目过程讲给 AI，自动生成结构化复盘报告：时间线、根因分析、方法论提炼、风险改进项，Markdown 一键导出。', AMBER),
]
cx = Inches(0.9); cy = Inches(2.25); cw = Inches(3.72); chh = Inches(2.12)
gap = Inches(0.17)
for i, (num, name, en, desc, color) in enumerate(mods):
    col = i % 3; row = i // 3
    x = cx + col * (cw + gap) + (row * Inches(0.62))
    y = cy + row * (chh + Inches(0.22))
    card = rect(s, x, y, cw, chh, fill=BG2, line=RGBColor(0x1C, 0x2C, 0x48), lw=0.75)
    # 顶部彩条
    rect(s, x, y, cw, Inches(0.06), fill=color)
    # 编号
    text(s, x + Inches(0.2), y + Inches(0.18), Inches(1.2), Inches(0.5),
         [(num, {'size': 26, 'color': color, 'bold': True, 'font': MONO})])
    # 名称
    text(s, x + Inches(0.95), y + Inches(0.22), cw - Inches(1.1), Inches(0.45),
         [(name, {'size': 17, 'color': TXT, 'bold': True}),
          ('  ' + en, {'size': 9.5, 'color': TXT3, 'font': MONO})])
    # 描述
    text(s, x + Inches(0.2), y + Inches(0.78), cw - Inches(0.4), chh - Inches(0.95),
         desc, size=11, color=TXT2, line_spacing=1.25)
# 第6格：闭环
x6 = cx + 2 * (cw + gap) + Inches(0.62)
y6 = cy + (chh + Inches(0.22))
card6 = rect(s, x6, y6, cw, chh, fill=RGBColor(0x0C, 0x1A, 0x2E), line=CYAN, lw=1)
rect(s, x6, y6, cw, Inches(0.06), fill=CYAN)
text(s, x6 + Inches(0.2), y6 + Inches(0.18), Inches(1.2), Inches(0.5),
     [('∞', {'size': 26, 'color': CYAN, 'bold': True, 'font': MONO})])
text(s, x6 + Inches(0.95), y6 + Inches(0.22), cw - Inches(1.1), Inches(0.45),
     [('能力闭环', {'size': 17, 'color': TXT, 'bold': True}),
      ('  CLOSED LOOP', {'size': 9.5, 'color': TXT3, 'font': MONO})])
text(s, x6 + Inches(0.2), y6 + Inches(0.78), cw - Inches(0.4), chh - Inches(0.95),
     '五环相扣形成交付闭环：现场发现问题 → 知识库找依据 → 智能体带排查 → 复盘沉淀经验 → 经验反哺知识库。',
     size=11, color=TXT2, line_spacing=1.25)
set_transition(s, 'push', 700)

# =========================================================
# S4 核心能力 0：灵犀测速 SpeedLens
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 4)
sec_head(s, 'SPEEDLENS · 核心能力 01', '灵犀测速：把"测速"重做一遍',
         '不止给你一个数字，而是直接回答——"网速到底怎么回事"')
_rows = [
    ('一键全链路体检', '握手 → 延迟 → 突发下载 → 突发上传 → 智能诊断，五阶段全程约 4 秒', CYAN),
    ('结论优先', '综合评分 S/A/B/C，逐条输出瓶颈定位、原因分析与处置建议', TEAL),
    ('全链路透视', '终端 → 网关 → 运营商 → CDN → 源站，逐跳延迟 + 缓存 HIT/MISS 可视化', VIOLET),
    ('也服务于"机器"', '标准 JSON / Prometheus 指标 / 阈值告警，直接接入 CI 与监控无人值守', AMBER),
]
yy = Inches(2.05)
_anim = []
for t1, t2, c in _rows:
    glow_dot(s, Inches(0.95), yy + Inches(0.10), c, 0.10)
    b1 = text(s, Inches(1.25), yy, Inches(4.7), Inches(0.32),
              [(t1, {'size': 15, 'color': c, 'bold': True})])
    b2 = text(s, Inches(1.25), yy + Inches(0.36), Inches(4.7), Inches(0.62),
              t2, size=11.5, color=TXT2)
    _anim += [(b1, 'fade', 450), (b2, 'fade', 450)]
    yy += Inches(1.04)
chip(s, Inches(0.95), Inches(6.42), '秒级测量', CYAN)
chip(s, Inches(2.17), Inches(6.42), '智能诊断', TEAL)
chip(s, Inches(3.39), Inches(6.42), 'CI / 监控', AMBER)
_pic = pic_framed(s, os.path.join('docs', 'shots', '03b-speedtest-run.png'),
                  Inches(6.4), Inches(2.0), w=Inches(6.25), max_h=Inches(4.0),
                  note='灵犀测速实测：实时波形 + 全链路透视 + 智能诊断结论')
_anim.append((_pic, 'float', 600))
build_anim(s, _anim)
set_transition(s, 'wipe', 700)

# =========================================================
# S5 核心能力 0：内网感知 NetSense
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 5)
sec_head(s, 'NETSENSE · 核心能力 02', '内网感知：走进客户现场的第一分钟',
         '告别"听客户描述 + 手动画拓扑"，接入即可看见整个网络')
# 顶部四步流程
_steps = [('接入现场网络', '网线 / Wi-Fi 均可', CYAN),
          ('真实探针感知', '存活主机 · 网关 · 网段', TEAL),
          ('自动绘制拓扑', '分层布局 · 实时流动画', VIOLET),
          ('给出部署建议', '深信服上架模式', AMBER)]
cxx, cyy, cwid = Inches(0.9), Inches(2.02), Inches(3.0)
_anim = []
for i, (t1, t2, c) in enumerate(_steps):
    cv = rect(s, cxx + Inches(int(2.85 * i)), cyy, cwid, Inches(0.78),
              fill=BG2, line=c, lw=1.2, shape=MSO_SHAPE.CHEVRON)
    try:
        cv.adjustments[0] = 0.35
    except Exception:
        pass
    b1 = text(s, cxx + Inches(int(2.85 * i)) + Inches(0.30), cyy + Inches(0.09),
              cwid - Inches(0.55), Inches(0.3),
              [(t1, {'size': 12.5, 'color': TXT, 'bold': True})], align=PP_ALIGN.CENTER)
    b2 = text(s, cxx + Inches(int(2.85 * i)) + Inches(0.30), cyy + Inches(0.42),
              cwid - Inches(0.55), Inches(0.26),
              t2, size=9, color=TXT3, align=PP_ALIGN.CENTER)
    _anim += [(cv, 'wipe', 400), (b1, 'fade', 350), (b2, 'fade', 350)]
_rows = [
    ('真实探针引擎', 'ICMP 存活探测 + 系统 ARP 表 + OUI 厂商指纹 + 端口特征识别，结果是"探"出来的', CYAN),
    ('Wi-Fi 就能感知', '不抢占客户网口：笔记本连上现场 Wi-Fi，即可"看见"整个内网环境', TEAL),
    ('所见即所得', '网段 / VLAN 表、设备指纹清单、可视化拓扑，一键导出 Mermaid / PNG 进交付文档', VIOLET),
    ('落地到实施', '按现场环境推荐网桥 / 路由 / 旁路部署模式，附可勾选的上架检查清单', AMBER),
]
yy = Inches(3.18)
for t1, t2, c in _rows:
    glow_dot(s, Inches(0.95), yy + Inches(0.10), c, 0.10)
    b1 = text(s, Inches(1.25), yy, Inches(5.35), Inches(0.32),
              [(t1, {'size': 15, 'color': c, 'bold': True})])
    b2 = text(s, Inches(1.25), yy + Inches(0.36), Inches(5.35), Inches(0.62),
              t2, size=11.5, color=TXT2)
    _anim += [(b1, 'fade', 450), (b2, 'fade', 450)]
    yy += Inches(0.98)
chip(s, Inches(0.95), Inches(7.0), 'ICMP + ARP', CYAN)
chip(s, Inches(2.35), Inches(7.0), 'OUI 指纹', TEAL)
chip(s, Inches(3.55), Inches(7.0), '拓扑即所得', VIOLET)
_pic = pic_framed(s, os.path.join('docs', 'shots', '04-topology.png'),
                  Inches(6.85), Inches(3.12), w=Inches(5.8), max_h=Inches(3.55),
                  note='内网感知实测：自动生成的客户内网拓扑')
_anim.append((_pic, 'float', 600))
build_anim(s, _anim)
set_transition(s, 'split', 700)

# =========================================================
# S6 核心能力 1：故障诊断智能体（产品核心）
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 6)
sec_head(s, 'CORE · AI AGENT', '故障诊断智能体：30 年经验的"远程专家"',
         '不直接给答案，而是像前辈一样一步步带工程师排查 —— 引导式排查 + 知识库强约束')

# 左：工作机制
lft = [
    ('引导式排查', '每轮只给一个具体动作（查命令/看日志/看指示灯），根据反馈走下一步，拒绝"一步登天"式答案', CYAN),
    ('知识库强约束', '所有判断必须基于深信服故障诊断知识库；库里没有就明说，严禁编造 —— 杜绝 AI 幻觉', TEAL),
    ('结构化输出', '当前步骤 → 请执行操作 → 预期结果 → 注意事项，现场工程师一眼看懂', VIOLET),
    ('风险前置警告', '涉及重启设备/修改核心配置/主备切换等高风险操作，琥珀色警告 + 变更窗口提醒', AMBER),
]
yy = Inches(2.25)
for name, desc, c in lft:
    b = rect(s, Inches(0.9), yy, Inches(6.2), Inches(0.96), fill=BG2, line=RGBColor(0x1C, 0x2C, 0x48), lw=0.75)
    rect(s, Inches(0.9), yy, Inches(0.05), Inches(0.96), fill=c)
    text(s, Inches(1.15), yy + Inches(0.10), Inches(5.8), Inches(0.35),
         [(name, {'size': 14, 'color': c, 'bold': True})])
    text(s, Inches(1.15), yy + Inches(0.44), Inches(5.8), Inches(0.5),
         desc, size=11.5, color=TXT2, line_spacing=1.2)
    yy += Inches(1.08)

# 右：实测截图（对话预览）
pic_framed(s, os.path.join(PROC, '故障诊断排查skill预览.png'),
           Inches(7.5), Inches(2.25), w=Inches(4.9), max_h=Inches(2.10),
           border=CYAN, note='智能体对话排查预览 · 引导式步骤输出')
pic_framed(s, os.path.join(PROC, '故障诊断排查skill预览2.png'),
           Inches(7.5), Inches(4.62), w=Inches(4.9), max_h=Inches(2.10),
           border=TEAL, note='结构化输出：步骤/操作/预期/注意事项')
set_transition(s, 'fade', 700)

# =========================================================
# S5 核心能力 2：专业知识库（底气所在）
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 7)
sec_head(s, 'CORE · KNOWLEDGE BASE', '深信服故障诊断知识库：AI 的"专业底气"',
         '有依据的回答才敢用 —— 资料搜集 → 知识库构建 → 检索调试 → 实测验证')

# 顶部四步流程
steps = [
    ('资料搜集', '故障排查社区/aDesk 资料库/官方文档', '故障排查社区资料搜集.png', CYAN),
    ('知识库构建', '深信服故障诊断知识库 + 案例复盘库', '创建深信服故障诊断知识库.png', TEAL),
    ('检索调试', '搜索设置调优，命中率与引用来源可控', '深信服故障诊断知识库搜索设置调试.png', VIOLET),
    ('实测验证', '真实故障场景测试，答案有据可查', '故障诊断排查知识库测试1.png', PINK),
]
sx = Inches(0.9); sy = Inches(2.2); sw_ = Inches(2.86); sh_ = Inches(2.5)
for i, (name, desc, img, c) in enumerate(steps):
    x = sx + i * (sw_ + Inches(0.18))
    pic_framed(s, os.path.join(PROC, img), x, sy, w=sw_, border=c)
    text(s, x, sy + Inches(1.62), sw_, Inches(0.32),
         [(name, {'size': 13, 'color': c, 'bold': True})], align=PP_ALIGN.CENTER)
    text(s, x, sy + Inches(1.94), sw_, Inches(0.5),
         desc, size=10, color=TXT2, align=PP_ALIGN.CENTER, line_spacing=1.15)
# 步骤箭头（用小三角）
for i in range(3):
    tri = s.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE,
                             sx + (i + 1) * sw_ + i * Inches(0.18) + Inches(0.02),
                             sy + Inches(1.05), Inches(0.14), Inches(0.18))
    tri.rotation = 90
    tri.fill.solid(); tri.fill.fore_color.rgb = TXT3; _noline(tri); tri.shadow.inherit = False

# 底部要点条
bar = rect(s, Inches(0.9), Inches(5.35), Inches(11.5), Inches(1.0),
           fill=RGBColor(0x0A, 0x14, 0x26), line=TEAL, lw=1)
text(s, Inches(1.15), Inches(5.52), Inches(11.0), Inches(0.7),
     [('双知识库支撑：', {'size': 13.5, 'color': TEAL, 'bold': True}),
      ('故障诊断库（排查依据） + 案例复盘库（经验沉淀）。AI 回答末尾附参考来源（如「AF 故障处理手册 v3.2」），'
       '工程师可溯源验证；案例复盘的报告又回流为知识库素材，形成知识飞轮。', {'size': 12.5, 'color': TXT})],
     line_spacing=1.3)
set_transition(s, 'fade', 700)

# =========================================================
# S6 核心能力 3：案例复盘 + 工具矩阵
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 8)
sec_head(s, 'CORE · REPORT & TOOLS', '案例复盘与全流程工具：交付闭环的最后一块拼图',
         '过程输入 → AI 结构化复盘 → 经验沉淀复用；测速/感知/白板支撑现场每一环')

# 左上：复盘工作流
pic_framed(s, os.path.join(PROC, '案例总结模板工作流.png'),
           Inches(0.9), Inches(2.2), w=Inches(5.9), max_h=Inches(2.0),
           border=VIOLET, note='案例总结模板工作流：过程材料 → 结构化报告')
# 左下：复盘报告 skill
pic_framed(s, os.path.join(PROC, '案例复盘报告skill配置展示.png'),
           Inches(0.9), Inches(4.62), w=Inches(5.9), max_h=Inches(1.95),
           border=TEAL, note='案例复盘报告 skill 配置：报告生成逻辑')
# 右：工具矩阵卡
tx = Inches(7.2); tw = Inches(5.2)
tools = [
    ('灵犀测速  SPEEDLENS', '4 秒一键测速 · 波形透视 · 智能诊断 · JSON/Prometheus', CYAN),
    ('内网感知  NETSENSE', '实测网关/网段 · 拓扑自动生成 · 深信服建模部署建议', TEAL),
    ('悬浮白板  WHITEBOARD', '全站悬浮 · 绘制/打字/截图标注 · 自动保存 · PNG 导出', VIOLET),
]
yy = Inches(2.2)
for name, desc, c in tools:
    b = rect(s, tx, yy, tw, Inches(1.06), fill=BG2, line=RGBColor(0x1C, 0x2C, 0x48), lw=0.75)
    rect(s, tx, yy, Inches(0.05), Inches(1.06), fill=c)
    text(s, tx + Inches(0.22), yy + Inches(0.12), tw - Inches(0.44), Inches(0.35),
         [(name, {'size': 13.5, 'color': c, 'bold': True})])
    text(s, tx + Inches(0.22), yy + Inches(0.5), tw - Inches(0.44), Inches(0.5),
         desc, size=11, color=TXT2, line_spacing=1.2)
    yy += Inches(1.18)
# 右下：闭环说明
bar = rect(s, tx, Inches(5.85), tw, Inches(0.82), fill=RGBColor(0x0C, 0x1A, 0x2E), line=CYAN, lw=1)
text(s, tx + Inches(0.2), Inches(5.98), tw - Inches(0.4), Inches(0.6),
     [('复盘 → 沉淀 → 复用：', {'size': 12, 'color': CYAN, 'bold': True}),
      ('报告回流知识库，经验不再锁在个人脑子里', {'size': 11.5, 'color': TXT})], line_spacing=1.25)
set_transition(s, 'push', 700)

# =========================================================
# S9 核心能力 5：随心记录悬浮白板
# =========================================================
s = add_slide()
decor(s, '02 / CAPABILITIES', 9)
sec_head(s, 'INSTANT BOARD · 核心能力 05', '随心记录：悬浮白板，灵感不落地',
         '在任意页面一键唤起，记录不打断手头的工作')
_rows = [
    ('全局悬浮球', '任意页面右下角一键唤起：测速中途、AI 对话途中，都能随手把要点记下来', CYAN),
    ('画 + 写双模式', '4 色画笔、三档粗细、橡皮与撤销；点击白板任意位置直接开始打字', TEAL),
    ('自动保存本机', '关闭再打开内容仍在；支持一键导出 PNG，直接归档进交付文档', VIOLET),
    ('为实施现场而生', '割接步骤、临时变更、客户口头需求——随手记、随手查，事后即素材', AMBER),
]
yy = Inches(2.05)
_anim = []
for t1, t2, c in _rows:
    glow_dot(s, Inches(0.95), yy + Inches(0.10), c, 0.10)
    b1 = text(s, Inches(1.25), yy, Inches(4.7), Inches(0.32),
              [(t1, {'size': 15, 'color': c, 'bold': True})])
    b2 = text(s, Inches(1.25), yy + Inches(0.36), Inches(4.7), Inches(0.62),
              t2, size=11.5, color=TXT2)
    _anim += [(b1, 'fade', 450), (b2, 'fade', 450)]
    yy += Inches(1.04)
chip(s, Inches(0.95), Inches(6.42), '悬浮窗', CYAN)
chip(s, Inches(2.05), Inches(6.42), '手绘 + 打字', TEAL)
chip(s, Inches(3.45), Inches(6.42), '自动保存', AMBER)
_pic = pic_framed(s, os.path.join('docs', 'shots', '02-home.png'),
                  Inches(6.4), Inches(2.0), w=Inches(6.25), max_h=Inches(4.0),
                  note='功能首页右下角：悬浮球常驻，点开即白板')
_anim.append((_pic, 'float', 600))
build_anim(s, _anim)
set_transition(s, 'fade', 700)

# =========================================================
# S7 背后的故事：创作过程（放"过程"截图）
# =========================================================
s = add_slide()
decor(s, '03 / STORY', 10)
sec_head(s, 'BEHIND THE STORY', '背后的故事：从想法到落地，每一步都有迹可循',
         'Vibe Coding 全程驱动 —— 与 AI 结对，把"30 年专家经验"一点点教给它')

# 时间线（横向）
phases = [
    ('① 需求与灵感', 'AI 赛道培训启发：从身边真实痛点出发 —— 交付现场"资料难找、经验断层"', 'ai视频内容提炼2.png', CYAN),
    ('② 资料收集', '深信服社区/aDesk 资料库系统性搜集故障案例与设备资料，建立素材池', 'aDesk桌面云资料库.png', TEAL),
    ('③ 知识库搭建', '构建故障诊断 + 案例复盘双知识库，描述与检索设置反复打磨', '深信服故障诊断知识库描述.png', VIOLET),
    ('④ 智能体开发', '编写 30 年专家提示词，配置引导式排查逻辑，Skill 化沉淀', '创作工作台智能体.png', PINK),
    ('⑤ 测试与调优', '真实故障场景测试 → 调整检索参数 → 优化输出格式，多轮迭代', '故障诊断排查知识库测试2.png', AMBER),
]
# 时间线主轴
axis = s.shapes.add_connector(1, Inches(1.0), Inches(2.62), Inches(12.4), Inches(2.62))
axis.line.color.rgb = RGBColor(0x1E, 0x30, 0x50); axis.line.width = Pt(1.5)
axis.shadow.inherit = False
pxs = Inches(0.95); pw_ = Inches(2.34); gap_ = Inches(0.13)
for i, (name, desc, img, c) in enumerate(phases):
    x = pxs + i * (pw_ + gap_)
    # 节点圆
    glow_dot(s, x + pw_/2 - Inches(0.055), Inches(2.56), c, 0.13)
    # 标题
    text(s, x, Inches(2.85), pw_, Inches(0.3),
         [(name, {'size': 12.5, 'color': c, 'bold': True})], align=PP_ALIGN.CENTER)
    # 截图
    im_path = os.path.join(PROC, img)
    pic_framed(s, im_path, x + Inches(0.12), Inches(3.2), w=pw_ - Inches(0.24),
               max_h=Inches(1.72), border=c)
    # 描述
    text(s, x, Inches(5.15), pw_, Inches(0.85),
         desc, size=9.5, color=TXT2, align=PP_ALIGN.CENTER, line_spacing=1.2)
# 底部结语
text(s, Inches(0.9), Inches(6.35), Inches(11.5), Inches(0.5),
     [('创作方式：', {'size': 12, 'color': CYAN, 'bold': True}),
      ('全程 Vibe Coding —— 需求描述给 AI、AI 生成实现、人工验收迭代，零基础也能做出能跑的产品（本 PPT 亦由 AI 生成）',
       {'size': 11.5, 'color': TXT2})], align=PP_ALIGN.CENTER)
set_transition(s, 'fade', 700)

# =========================================================
# S8 改进：真机验证与离线场景（放"改进1"截图）
# =========================================================
s = add_slide()
decor(s, '04 / IMPROVEMENT', 11)
sec_head(s, 'ITERATION', '改进：从"演示能跑"到"现场可用"',
         '不做"刚好能用"的作品 —— 真机部署验证、离线场景兜底、体验持续打磨')

# 左：真机运行验证
pic_framed(s, os.path.join(IMPR, '在朋友上运行的情况.jpg'),
           Inches(0.9), Inches(2.2), h=Inches(3.95),
           border=TEAL, note='真机部署验证：在同事电脑上实际运行')
# 中上：改进点1
pic_framed(s, os.path.join(IMPR, '改进1.png'),
           Inches(4.35), Inches(2.2), w=Inches(4.0), max_h=Inches(1.92),
           border=CYAN, note='智能体输出优化：排查步骤更聚焦')
# 中下：改进点3
pic_framed(s, os.path.join(IMPR, '改进3.png'),
           Inches(4.35), Inches(4.42), w=Inches(4.0), max_h=Inches(1.92),
           border=VIOLET, note='知识库命中与引用来源优化')
# 右：离线兜底 + 改进4
pic_framed(s, os.path.join(IMPR, '没网的时候.png'),
           Inches(8.55), Inches(2.2), w=Inches(3.9), max_h=Inches(1.92),
           border=AMBER, note='离线场景兜底：客户现场没网的应对')
pic_framed(s, os.path.join(IMPR, '改进4.jpg'),
           Inches(8.55), Inches(4.42), w=Inches(3.9), max_h=Inches(1.92),
           border=PINK, note='端到端验收：核心链路真实跑通')

# 底部改进清单
imps = [
    ('真机验证', '不只在自己电脑能跑，同事机器部署验证', TEAL),
    ('离线兜底', '客户现场无网场景预案，断网也有基础能力', AMBER),
    ('输出调优', '排查步骤更聚焦、引用来源更明确', CYAN),
    ('端到端验收', '真实跑通核心链路，拒绝"演示专用"', PINK),
]
xx = Inches(0.9); yy = Inches(6.35)
for name, desc, c in imps:
    glow_dot(s, xx, yy + Inches(0.06), c, 0.09)
    text(s, xx + Inches(0.18), yy - Inches(0.02), Inches(2.9), Inches(0.6),
         [(name + '　', {'size': 11.5, 'color': TXT, 'bold': True}),
          (desc, {'size': 10, 'color': TXT2})], line_spacing=1.15)
    xx += Inches(2.95)
set_transition(s, 'push', 700)

# =========================================================
# S12 技术架构与工程细节
# =========================================================
s = add_slide()
decor(s, '05 / ENGINEERING', 12)
sec_head(s, 'ENGINEERING · 工程细节', '零依赖的工程化实现',
         '只用 Python 标准库，把一个"作品"做成可交付的"产品"')
# 左：五层架构
_layers = [
    ('前端层', '单文件 HTML/CSS/JS · 零构建依赖 · 深色玻璃拟态界面', CYAN),
    ('服务层', '标准库 HTTP 服务 · 会话 / 静态资源 / Range 流媒体', TEAL),
    ('探针引擎', 'ICMP 存活 / ARP 表 / OUI 指纹 / 端口特征 · 并发探测', VIOLET),
    ('AI 通道', 'OpenAI 兼容直连 · 诊断/复盘双模型 · 本地知识库检索注入', PINK),
    ('数据层', 'SQLite：用户 / 会话 / 测速与拓扑记录', AMBER),
]
yy = Inches(2.05)
_anim = []
for name, desc, c in _layers:
    b = rect(s, Inches(0.9), yy, Inches(5.7), Inches(0.78),
             fill=BG2, line=RGBColor(0x1C, 0x2C, 0x48), lw=0.75)
    rect(s, Inches(0.9), yy, Inches(0.05), Inches(0.78), fill=c)
    b1 = text(s, Inches(1.15), yy + Inches(0.10), Inches(1.6), Inches(0.3),
              [(name, {'size': 13.5, 'color': c, 'bold': True})])
    b2 = text(s, Inches(2.75), yy + Inches(0.13), Inches(3.75), Inches(0.56),
              desc, size=10.5, color=TXT2)
    _anim += [(b, 'wipe', 400), (b1, 'fade', 300), (b2, 'fade', 300)]
    yy += Inches(0.92)
chip(s, Inches(0.9), Inches(6.72), '纯标准库', CYAN)
chip(s, Inches(2.0), Inches(6.72), '零第三方依赖', TEAL)
chip(s, Inches(3.55), Inches(6.72), '一键打包', AMBER)
# 右：工程亮点
_pts = [
    ('安全设计', 'PBKDF2 十二万次迭代加盐存储密码；HttpOnly 会话 Cookie；默认仅本机绑定', CYAN),
    ('健壮性兜底', 'AI 空回复自动重试、reasoning 内容兜底、图片输入不支持时自动降级为文本', TEAL),
    ('自动化交付', 'pack.py 一键打包产品 zip，解压双击即用；测速输出 JSON / Prometheus 供 CI', VIOLET),
    ('诚实的演示口径', '实测与建模数据在界面中显式标注，绝不混淆——工程态度也是竞争力', AMBER),
]
yy = Inches(2.05)
for t1, t2, c in _pts:
    glow_dot(s, Inches(7.05), yy + Inches(0.10), c, 0.10)
    b1 = text(s, Inches(7.35), yy, Inches(5.3), Inches(0.32),
              [(t1, {'size': 14.5, 'color': c, 'bold': True})])
    b2 = text(s, Inches(7.35), yy + Inches(0.34), Inches(5.3), Inches(0.62),
              t2, size=11, color=TXT2)
    _anim += [(b1, 'fade', 450), (b2, 'fade', 450)]
    yy += Inches(1.12)
build_anim(s, _anim)
set_transition(s, 'push', 700)

# =========================================================
# S9 升华：愿景与致谢
# =========================================================
s = add_slide()
decor(s, '06 / VISION', 13)
# 装饰
ring = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4.42), Inches(0.75), Inches(4.5), Inches(4.5))
ring.fill.background(); ring.line.color.rgb = RGBColor(0x14, 0x2A, 0x44); ring.line.width = Pt(1.2)
ring.shadow.inherit = False
ring2 = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4.92), Inches(1.25), Inches(3.5), Inches(3.5))
ring2.fill.background(); ring2.line.color.rgb = RGBColor(0x1B, 0x2C, 0x4A); ring2.line.width = Pt(0.8)
ring2.shadow.inherit = False

text(s, Inches(1.5), Inches(1.15), Inches(10.33), Inches(0.4),
     'VISION & THANKS', size=13, color=CYAN, font=MONO, bold=True, align=PP_ALIGN.CENTER)
text(s, Inches(1.5), Inches(1.7), Inches(10.33), Inches(1.0),
     [('让 AI 的专业经验，', {'size': 34, 'color': TXT, 'bold': True}),
      ('守护每一次交付', {'size': 34, 'color': CYAN, 'bold': True})],
     align=PP_ALIGN.CENTER, line_spacing=1.3)

# 三句升华
lines = [
    ('从"会用工具"到"用好 AI"', '这次比赛教会我的，不是某个工具的操作，而是一套方法：把真实问题说清楚，让 AI 拆解、实现、验证、迭代。', CYAN),
    ('AI 赋能不是开发者的专利', '零基础也能做出解决真实问题的作品 —— 只要你愿意把身边的痛点当回事。', TEAL),
    ('让经验不再"人走茶凉"', '把工程师的 30 年经验沉淀为知识库与智能体，让专业能力可传承、可复用、可进化。', VIOLET),
]
yy = Inches(3.3)
for t1, t2, c in lines:
    glow_dot(s, Inches(2.6), yy + Inches(0.10), c, 0.10)
    text(s, Inches(2.9), yy, Inches(8.0), Inches(0.35),
         [(t1, {'size': 15, 'color': c, 'bold': True})])
    text(s, Inches(2.9), yy + Inches(0.38), Inches(8.0), Inches(0.4),
         t2, size=12, color=TXT2)
    yy += Inches(0.92)

# 致谢
text(s, Inches(1.5), Inches(6.15), Inches(10.33), Inches(0.8),
     [('衷心感谢深信服、感谢各位评审老师，愿意给我这样一个机会使用 AI、研究 AI、展示自己的作品。', 
       {'size': 13.5, 'color': TXT, 'bold': True})],
     align=PP_ALIGN.CENTER)
text(s, Inches(1.5), Inches(6.75), Inches(10.33), Inches(0.4),
     'CyberNWT · 翁炀彬 · AI 区域争霸赛', size=11, color=TXT3, font=MONO, align=PP_ALIGN.CENTER)
set_transition(s, 'fade', 900)

# =========================================================
# 保存
# =========================================================
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CyberNWT-演示PPT.pptx')
try:
    prs.save(out)
    print('SAVED:', out)
except PermissionError:
    alt = out.replace('.pptx', '-v2.pptx')
    prs.save(alt)
    print('SAVED(FALLBACK，原文件被占用，请关闭后重命名或重跑脚本):', alt)
_d = r'D:\桌面\计算机网络方向\深信服sangfor\AI区域争霸赛\CyberNWT-演示PPT.pptx'
if os.path.isdir(os.path.dirname(_d)):
    prs.save(_d)
    print('SAVED:', _d)
print('slides:', len(prs.slides._sldIdLst))
