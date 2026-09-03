/* CyberNWT · 随心记录 —— 全局悬浮白板组件
 * 在任意页面引入 <script src="whiteboard.js" defer></script> 即可：
 *   · 右下角悬浮按钮，点击弹出白板（不离开当前界面）
 *   · 自由手绘（彩色球选色 / 悬停滑杆调粗细 / 橡皮滑杆调范围 / 撤销）+ 点击白板任意处直接打字
 *   · 一键截图：把当前页面捕获为图片插入画板，作为涂画参考（html2canvas，本地组件）
 *   · 底衬可在「网格 / 空白」间切换；网格画在最底层，橡皮永远擦不掉网格
 *   · 白板可拖动、可缩放、可最小化；内容自动保存到浏览器本地；支持导出 PNG
 * 对外接口：CyberBoard.open() / .close() / .toggle()
 */
(function () {
  'use strict';

  var STORE_KEY = 'cybernwt.board.v1';
  var W = 1600, H = 1200;                 // 白板内部分辨率（与显示尺寸解耦，缩放不糊）
  var COLORS = ['#1e293b', '#2563eb', '#dc2626', '#16a34a'];
  var state = {
    mode: 'pen', color: COLORS[0], size: 11, eraserSize: 30,
    bg: 'grid',                           // 'grid' | 'blank'
    strokes: [], images: [], texts: [], hist: [], seq: 0
  };
  var imgCache = {};                      // key → HTMLImageElement（截图重绘缓存）
  var ui = {};

  /* ---------- 样式 ---------- */
  var css = [
    '.cb-fab{position:fixed;right:24px;bottom:24px;z-index:9990;width:var(--fab-size,56px);height:var(--fab-size,56px);',
    'border:1px solid var(--accent-border,rgba(126,206,244,.35));border-radius:var(--fab-radius,50%);cursor:pointer;',
    'color:var(--accent-contrast,#fff);display:flex;align-items:center;justify-content:center;',
    'background:var(--accent,linear-gradient(135deg,#1a56c4,#0f8a5f));box-shadow:none;transition:transform .18s,filter .18s;}',
    '.cb-fab:hover{transform:translateY(-2px);filter:brightness(.9);}',
    '.cb-fab svg{width:22px;height:22px;fill:none;stroke:var(--accent-contrast,#fff);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}',

    '.cb-panel{position:fixed;right:24px;bottom:96px;z-index:9991;width:560px;height:480px;min-width:380px;min-height:320px;',
    'display:none;flex-direction:column;border-radius:6px;overflow:hidden;',
    'background:var(--panel,rgba(10,21,33,.92));backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);',
    'border:1px solid var(--border,rgba(126,206,244,.28));box-shadow:0 24px 70px rgba(0,0,0,.55);',
    'animation:cb-pop .18s ease-out;}',
    '.cb-panel.show{display:flex;}',
    '@keyframes cb-pop{from{opacity:0;transform:translateY(14px) scale(.97);}to{opacity:1;transform:none;}}',

    '.cb-head{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:move;user-select:none;',
    'background:var(--accent-bg,rgba(126,206,244,.08));border-bottom:1px solid var(--border,rgba(126,206,244,.18));}',
    '.cb-head .dot{width:10px;height:10px;border-radius:50%;flex:none;',
    'background:var(--accent,radial-gradient(circle at 35% 35%,#6FBA2C,#00663B));}',
    '.cb-head b{color:var(--text,#e8f2ff);font-size:13.5px;letter-spacing:1px;font-family:"Microsoft YaHei",sans-serif;}',
    '.cb-saved{color:var(--text-2,#7ee2a8);font-size:11.5px;opacity:0;transition:opacity .4s;font-family:"Microsoft YaHei",sans-serif;}',
    '.cb-min,.cb-close{margin-left:auto;border:none;background:transparent;color:var(--text-2,#8fa8c7);font-size:16px;',
    'cursor:pointer;width:28px;height:28px;border-radius:4px;line-height:1;flex:none;}',
    '.cb-min:hover,.cb-close:hover{background:var(--accent-bg,rgba(126,206,244,.14));color:var(--text,#fff);}',
    '.cb-close{margin-left:0;}',

    /* 工具栏 */
    '.cb-tools{position:relative;z-index:30;display:flex;align-items:center;gap:6px;padding:8px 12px;flex-wrap:wrap;',
    'border-bottom:1px solid var(--border,rgba(126,206,244,.14));}',
    '.cb-tools .grp{display:flex;gap:4px;padding:3px;border-radius:4px;background:var(--accent-bg,rgba(126,206,244,.08));}',
    '.cb-tbtn{border:none;background:transparent;color:var(--text-2,#cfe3f8);cursor:pointer;border-radius:4px;',
    'min-width:30px;height:28px;padding:0 8px;font-size:12.5px;display:flex;align-items:center;gap:5px;',
    'font-family:"Microsoft YaHei",sans-serif;transition:background .15s;}',
    '.cb-tbtn:hover{background:var(--accent-bg,rgba(126,206,244,.16));}',
    '.cb-tbtn.on{background:var(--accent,#fff);color:var(--accent-contrast,#0a0a0a);}',
    '.cb-tbtn svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none;}',
    '.cb-undo{margin-left:auto;}',

    /* 彩色球（当前颜色为球心） */
    '.cb-ball{width:18px;height:18px;border-radius:50%;border:none;cursor:pointer;padding:0;flex:none;',
    'background:radial-gradient(circle at 50% 50%,var(--cur,#1e293b) 0 4.5px,transparent 5px),',
    'conic-gradient(#ef4444,#f59e0b,#22c55e,#06b6d4,#3b82f6,#a855f7,#ef4444);}',
    '.cb-cpick{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}',

    /* 悬停弹层：笔 / 橡皮的粗细滑杆、颜色快捷选择（仅悬停显示，移开即收起） */
    '.cb-wrap{position:relative;display:flex;gap:4px;align-items:center;}',
    '.cb-wrap::after{content:"";position:absolute;top:100%;left:0;width:100%;height:10px;}',
    '.cb-pop{position:absolute;top:100%;left:0;z-index:40;display:none;align-items:center;gap:8px;',
    'padding:10px 12px;border-radius:6px;background:var(--panel,#111);color:var(--text,#e8f2ff);',
    'border:1px solid var(--border,rgba(255,255,255,.14));box-shadow:0 12px 34px rgba(0,0,0,.4);white-space:nowrap;}',
    '.cb-wrap:hover .cb-pop{display:flex;}',
    '.cb-pop input[type=range]{width:150px;accent-color:#2563eb;cursor:pointer;}',
    '.cb-pop .cb-v{font-size:11.5px;min-width:34px;text-align:right;font-family:"JetBrains Mono",Consolas,monospace;}',
    '.cb-pop .cb-lb{font-size:12px;color:var(--text-2,#9ca3af);font-family:"Microsoft YaHei",sans-serif;}',
    '.cb-pop .cb-sw{width:17px;height:17px;border-radius:50%;border:2px solid transparent;cursor:pointer;padding:0;flex:none;}',
    '.cb-pop .cb-sw.on{border-color:var(--accent,#fff);}',
    '.cb-pop .cb-custom{border:none;background:transparent;color:var(--text,#e8f2ff);cursor:pointer;',
    'font-size:12px;font-family:"Microsoft YaHei",sans-serif;padding:2px 4px;border-radius:4px;}',
    '.cb-pop .cb-custom:hover{background:var(--accent-bg,rgba(126,206,244,.14));}',

    /* 截图框选遮罩 */
    '.cb-shotui{position:fixed;inset:0;z-index:10000;cursor:crosshair;user-select:none;-webkit-user-select:none;}',
    '.cb-shotui .cb-fullmask{position:absolute;inset:0;background:rgba(0,0,0,.35);}',
    '.cb-shotui .cb-rect{position:absolute;border:1.5px dashed #22c55e;display:none;',
    'box-shadow:0 0 0 100000px rgba(0,0,0,.35);}',
    '.cb-shotui .cb-size{position:absolute;display:none;background:#22c55e;color:#04120a;font-size:11px;',
    'padding:2px 7px;border-radius:4px;font-family:"JetBrains Mono",Consolas,monospace;}',
    '.cb-shotui .cb-tipbar{position:absolute;top:14px;left:50%;transform:translateX(-50%);',
    'background:#111;color:#fff;font-size:12.5px;padding:8px 18px;border-radius:999px;',
    'font-family:"Microsoft YaHei",sans-serif;letter-spacing:1px;}',

    /* 截图图片：可拖动 / 可缩放 */
    '.cb-imgs{position:absolute;inset:0;pointer-events:none;}',
    '.cb-imgitem{position:absolute;pointer-events:auto;}',
    '.cb-imgitem img{width:100%;height:100%;display:block;box-shadow:0 4px 18px rgba(0,0,0,.18);}',
    '.cb-imgsel{position:absolute;display:none;border:1.5px dashed #2563eb;cursor:move;pointer-events:auto;z-index:6;}',
    '.cb-imgsel .cb-h{position:absolute;width:9px;height:9px;background:#2563eb;border:1.5px solid #fff;',
    'border-radius:2px;box-shadow:0 1px 4px rgba(0,0,0,.35);}',
    '.cb-h[data-d=n]{left:calc(50% - 5px);top:-5px;cursor:ns-resize;}',
    '.cb-h[data-d=s]{left:calc(50% - 5px);bottom:-5px;cursor:ns-resize;}',
    '.cb-h[data-d=e]{right:-5px;top:calc(50% - 5px);cursor:ew-resize;}',
    '.cb-h[data-d=w]{left:-5px;top:calc(50% - 5px);cursor:ew-resize;}',
    '.cb-h[data-d=ne]{right:-5px;top:-5px;cursor:nesw-resize;}',
    '.cb-h[data-d=nw]{left:-5px;top:-5px;cursor:nwse-resize;}',
    '.cb-h[data-d=se]{right:-5px;bottom:-5px;cursor:nwse-resize;}',
    '.cb-h[data-d=sw]{left:-5px;bottom:-5px;cursor:nesw-resize;}',
    '.cb-imgsel .cb-seltag{position:absolute;left:0;top:-20px;background:#2563eb;color:#fff;font-size:10.5px;',
    'padding:1px 7px;border-radius:3px;white-space:nowrap;}',

    '.cb-body{position:relative;flex:1;overflow:hidden;background:#f7f9fc;}',
    '.cb-layer,.cb-canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none;}',
    '.cb-canvas{cursor:crosshair;}',
    ".cb-canvas.pen-mode{cursor:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><g stroke-linejoin='round'><path d='M8.4 23.9 19.7 12.6 15.4 8.3 4.1 19.6Z' fill='%23334155' stroke='%23ffffff' stroke-width='1.2'/><path d='M2 26 8.4 23.9 4.1 19.6Z' fill='%23f59e0b' stroke='%23ffffff' stroke-width='1'/></g></svg>\") 2 26, crosshair;}",
    '.cb-canvas.text-mode{cursor:text;}',
    '.cb-texts{position:absolute;inset:0;pointer-events:none;}',
    '.cb-text{position:absolute;pointer-events:auto;outline:none;font:15px/1.5 "Microsoft YaHei",sans-serif;',
    'color:#1e293b;min-width:24px;padding:2px 4px;border-radius:4px;white-space:pre-wrap;word-break:break-all;}',
    '.cb-text:focus{background:rgba(37,99,235,.07);box-shadow:0 0 0 1.5px rgba(37,99,235,.45);}',
    '.cb-text::placeholder{color:#94a3b8;}',
    '.cb-text .cb-tmv{position:absolute;top:-19px;left:-19px;width:19px;height:19px;border-radius:50%;',
    'cursor:move;opacity:0;transition:opacity .15s;pointer-events:auto;user-select:none;',
    'background:#fff;border:1px solid rgba(100,116,139,.45);box-shadow:0 1px 5px rgba(0,0,0,.22);',
    'display:flex;align-items:center;justify-content:center;}',
    '.cb-text .cb-tmv svg{width:11px;height:11px;fill:none;stroke:#475569;stroke-width:2;',
    'stroke-linecap:round;stroke-linejoin:round;}',
    '.cb-text .cb-trz{position:absolute;right:-7px;bottom:-7px;width:13px;height:13px;cursor:nwse-resize;',
    'opacity:0;transition:opacity .15s;background:#2563eb;border:2px solid #fff;border-radius:3px;pointer-events:auto;}',
    '.cb-text:hover .cb-tmv,.cb-text:hover .cb-trz,.cb-text:focus .cb-tmv,.cb-text:focus .cb-trz{opacity:1;}',

    '.cb-resize{position:absolute;right:0;bottom:0;width:18px;height:18px;cursor:nwse-resize;z-index:5;',
    'background:linear-gradient(135deg,transparent 50%,var(--accent,rgba(126,206,244,.5)) 50%);}',
    '.cb-hint{padding:5px 14px;font-size:11px;color:var(--text-2,#6f88a8);border-top:1px solid var(--border,rgba(126,206,244,.12));',
    'font-family:"Microsoft YaHei",sans-serif;}'
  ].join('');

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  /* ---------- DOM ---------- */
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  /* 图标：Lucide (MIT) https://lucide.dev */
  var ICONS = {
    pen: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/></svg>',
    eraser: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/></svg>',
    shot: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2-3z"/><circle cx="12" cy="13" r="3"/></svg>',
    grid: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/></svg>',
    blank: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
    type: '<svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/><line x1="12" x2="12" y1="4" y2="20"/></svg>',
    undo: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>'
  };
  var fab = el('button', 'cb-fab');
  fab.title = '随心记录';
  fab.innerHTML = ICONS.pen;
  document.body.appendChild(fab);

  var panel = el('div', 'cb-panel');
  panel.innerHTML =
    '<div class="cb-head"><span class="dot"></span><b>随心记录</b>' +
    '<span class="cb-saved">已自动保存</span>' +
    '<button class="cb-min" title="收起">—</button><button class="cb-close" title="关闭">✕</button></div>' +
    '<div class="cb-tools"></div>' +
    '<div class="cb-body">' +
    '<canvas class="cb-layer" id="cb-grid"></canvas>' +
    '<div class="cb-imgs" id="cb-imgs"></div>' +
    '<canvas class="cb-canvas"></canvas>' +
    '<div class="cb-imgsel" id="cb-sel"><span class="cb-seltag">截图 · 拖动移动 / 手柄上下左右缩放</span>' +
    '<span class="cb-h" data-d="n"></span><span class="cb-h" data-d="s"></span>' +
    '<span class="cb-h" data-d="e"></span><span class="cb-h" data-d="w"></span>' +
    '<span class="cb-h" data-d="ne"></span><span class="cb-h" data-d="nw"></span>' +
    '<span class="cb-h" data-d="se"></span><span class="cb-h" data-d="sw"></span></div>' +
    '<div class="cb-texts"></div>' +
    '<div class="cb-resize"></div></div>' +
    '<div class="cb-hint">画笔 / 橡皮：悬停调粗细 · 彩色球选颜色 · 截图后拖拽框选区域，双击图片可移动 / 缩放 · 文字可拖动与调字号 · 网格底衬不会被擦除 · Esc 关闭</div>';
  document.body.appendChild(panel);

  ui.head = panel.querySelector('.cb-head');
  ui.saved = panel.querySelector('.cb-saved');
  ui.tools = panel.querySelector('.cb-tools');
  ui.body = panel.querySelector('.cb-body');
  ui.grid = panel.querySelector('#cb-grid');
  ui.imgs = panel.querySelector('#cb-imgs');
  ui.sel = panel.querySelector('#cb-sel');
  ui.canvas = panel.querySelector('.cb-canvas');
  ui.texts = panel.querySelector('.cb-texts');
  ui.resize = panel.querySelector('.cb-resize');
  var gctx = ui.grid.getContext('2d');
  var ctx = ui.canvas.getContext('2d');
  [ui.grid, ui.canvas].forEach(function (c) { c.width = W; c.height = H; });
  var selectedImg = null;   // 当前选中的截图 key（可拖动 / 缩放）

  /* ---------- 工具栏 ---------- */
  var modeBtns = {};
  function toolBtn(parent, label, title, cls, onclick) {
    var b = el('button', 'cb-tbtn' + (cls ? ' ' + cls : ''), label);
    b.title = title; b.type = 'button';
    b.addEventListener('click', onclick);
    parent.appendChild(b);
    return b;
  }
  /* 悬停弹层容器：按钮 + 弹层（滑杆 / 色板） */
  function wrapBtn(parent, icon, label, title, popover, onclick) {
    var wrap = el('span', 'cb-wrap');
    var b = el('button', 'cb-tbtn', icon + (label ? ' ' + label : ''));
    b.title = title; b.type = 'button';
    if (onclick) b.addEventListener('click', onclick);
    wrap.appendChild(b);
    wrap.appendChild(popover);
    parent.appendChild(wrap);
    return b;
  }

  function sliderPop(min, max, value, label, onInput) {
    var pop = el('div', 'cb-pop');
    var lb = el('span', 'cb-lb', label);
    var r = el('input'); r.type = 'range'; r.min = min; r.max = max; r.value = value;
    var v = el('span', 'cb-v', value + 'px');
    r.addEventListener('input', function () {
      v.textContent = r.value + 'px';
      onInput(parseInt(r.value, 10));
    });
    // 拖完松手即失焦，弹层随鼠标移开立即收起（避免焦点残留导致不消失）
    r.addEventListener('pointerup', function () { try { r.blur(); } catch (e) {} });
    r.addEventListener('change', function () { try { r.blur(); } catch (e) {} });
    pop.appendChild(lb); pop.appendChild(r); pop.appendChild(v);
    return pop;
  }

  /* 画笔 + 粗细滑杆 */
  var penGrp = el('div', 'grp'); ui.tools.appendChild(penGrp);
  modeBtns.pen = wrapBtn(penGrp, ICONS.pen, '画笔', '自由绘制（悬停调粗细）',
    sliderPop(2, 40, state.size, '粗细', function (v) { state.size = v; setMode('pen'); }),
    function () { setMode('pen'); });

  /* 彩色球 + 快捷色板 / 自定义色 */
  var colorPop = el('div', 'cb-pop');
  var ball = el('button', 'cb-ball');
  ball.title = '画笔颜色'; ball.type = 'button';
  ball.style.setProperty('--cur', state.color);
  var cpick = el('input', 'cb-cpick'); cpick.type = 'color'; cpick.value = state.color;
  function setColor(c) {
    state.color = c;
    ball.style.setProperty('--cur', c);
    cpick.value = c;
    colorPop.querySelectorAll('.cb-sw').forEach(function (x) { x.classList.remove('on'); });
    setMode('pen');
  }
  COLORS.forEach(function (c, i) {
    var s = el('button', 'cb-sw' + (i === 0 ? ' on' : ''));
    s.type = 'button'; s.style.background = c; s.title = c;
    s.addEventListener('click', function () {
      s.classList.add('on');
      setColor(c);
      try { s.blur(); } catch (e) {}   // 选完即失焦，色板随鼠标移开收起
    });
    colorPop.appendChild(s);
  });
  var custom = el('button', 'cb-custom', '更多颜色…');
  custom.type = 'button';
  custom.addEventListener('click', function () {
    cpick.click();
    try { custom.blur(); } catch (e) {}
  });
  cpick.addEventListener('input', function () { setColor(cpick.value); });
  cpick.addEventListener('change', function () { try { cpick.blur(); } catch (e) {} });
  cpick.addEventListener('input', function () { setColor(cpick.value); });
  colorPop.appendChild(custom);
  colorPop.appendChild(cpick);
  var colorWrap = el('span', 'cb-wrap');
  colorWrap.appendChild(ball);
  colorWrap.appendChild(colorPop);
  penGrp.appendChild(colorWrap);
  ball.addEventListener('click', function () { cpick.click(); setMode('pen'); });

  /* 橡皮 + 范围滑杆 */
  var erGrp = el('div', 'grp'); ui.tools.appendChild(erGrp);
  modeBtns.eraser = wrapBtn(erGrp, ICONS.eraser, '橡皮', '擦除笔迹（悬停调范围）',
    sliderPop(8, 80, state.eraserSize, '范围', function (v) { state.eraserSize = v; setMode('eraser'); }),
    function () { setMode('eraser'); });

  /* 截图 / 打字 */
  var midGrp = el('div', 'grp'); ui.tools.appendChild(midGrp);
  modeBtns.shot = toolBtn(midGrp, ICONS.shot + ' 截图', '截取当前页面，插入画板作参考', '', doScreenshot);
  modeBtns.text = toolBtn(midGrp, ICONS.type + ' 打字', '点击白板处插入文字', '', function () { setMode('text'); });

  /* 底衬切换 + 撤销 / 导出 / 清空 */
  var endGrp = el('div', 'grp'); ui.tools.appendChild(endGrp);
  modeBtns.bg = toolBtn(endGrp, ICONS.grid + ' 网格', '切换底衬：网格 / 空白', '', function () {
    state.bg = state.bg === 'grid' ? 'blank' : 'grid';
    modeBtns.bg.innerHTML = (state.bg === 'grid' ? ICONS.grid : ICONS.blank) + (state.bg === 'grid' ? ' 网格' : ' 空白');
    modeBtns.bg.title = state.bg === 'grid' ? '当前：网格底衬（点击切换空白）' : '当前：空白底衬（点击切换网格）';
    drawGridLayer();
    saveSoon();
  });

  var endGrp2 = el('div', 'grp'); ui.tools.appendChild(endGrp2);
  toolBtn(endGrp2, ICONS.undo + ' 撤销', '撤销上一步', 'cb-undo', undo);
  toolBtn(endGrp2, '⇩ 导出', '导出 PNG', '', exportPNG);
  toolBtn(endGrp2, '✕ 清空', '清空白板（不可恢复）', '', clearBoard);

  function setMode(m) {
    state.mode = m;
    ['pen', 'eraser', 'text'].forEach(function (k) {
      if (modeBtns[k]) modeBtns[k].classList.toggle('on', k === m);
    });
    ui.canvas.classList.toggle('pen-mode', m === 'pen');
    ui.canvas.classList.toggle('text-mode', m === 'text');
    if (m === 'text') drawBoard();
  }
  setMode('pen');
  syncBgBtn();

  function syncBgBtn() {
    modeBtns.bg.innerHTML = (state.bg === 'grid' ? ICONS.grid : ICONS.blank) + (state.bg === 'grid' ? ' 网格' : ' 空白');
    modeBtns.bg.title = state.bg === 'grid' ? '当前：网格底衬（点击切换空白）' : '当前：空白底衬（点击切换网格）';
  }

  /* ---------- 渲染：三层 ---------- */
  /* 第 1 层：底衬（网格 / 空白）——独立画布，橡皮永远作用不到 */
  function drawGridLayer() {
    gctx.fillStyle = '#f7f9fc';
    gctx.fillRect(0, 0, W, H);
    if (state.bg === 'grid') {
      gctx.strokeStyle = 'rgba(100,140,190,.12)';
      gctx.lineWidth = 1;
      for (var x = 40; x < W; x += 40) { gctx.beginPath(); gctx.moveTo(x + .5, 0); gctx.lineTo(x + .5, H); gctx.stroke(); }
      for (var y = 40; y < H; y += 40) { gctx.beginPath(); gctx.moveTo(0, y + .5); gctx.lineTo(W, y + .5); gctx.stroke(); }
    }
  }

  /* 第 2 层：截图图片（DOM 元素：双击选中后可拖动 / 缩放） */
  function renderImages() {
    ui.imgs.innerHTML = '';
    state.images.forEach(function (im) {
      var d = el('div', 'cb-imgitem');
      d.dataset.key = im.key;
      d.style.left = (im.x * 100) + '%';
      d.style.top = (im.y * 100) + '%';
      d.style.width = (im.w * 100) + '%';
      d.style.height = (im.h * 100) + '%';
      var img = imgCache[im.key];
      if (!img || img.src !== im.data) {
        img = new Image();
        img.src = im.data;
        imgCache[im.key] = img;
      }
      d.appendChild(img);
      ui.imgs.appendChild(d);
    });
    if (selectedImg) {
      var it = state.images.filter(function (x) { return x.key === selectedImg; })[0];
      if (!it) { selectedImg = null; } else { syncSelBox(it); }
    }
    if (!selectedImg) ui.sel.style.display = 'none';
  }
  function syncSelBox(im) {
    ui.sel.style.display = 'block';
    ui.sel.style.left = (im.x * 100) + '%';
    ui.sel.style.top = (im.y * 100) + '%';
    ui.sel.style.width = (im.w * 100) + '%';
    ui.sel.style.height = (im.h * 100) + '%';
  }
  function selectImage(key) {
    selectedImg = key;
    renderImages();
  }
  function deselectImage() {
    if (!selectedImg) return;
    selectedImg = null;
    ui.sel.style.display = 'none';
  }
  /* 选中后：整体拖动移动；手柄上下左右自由拉伸 */
  function syncItemStyle(im) {
    var d = ui.imgs.querySelector('[data-key="' + im.key + '"]');
    if (d) {
      d.style.left = (im.x * 100) + '%';
      d.style.top = (im.y * 100) + '%';
      d.style.width = (im.w * 100) + '%';
      d.style.height = (im.h * 100) + '%';
    }
  }
  ui.sel.addEventListener('pointerdown', function (e) {
    var h = e.target.closest('.cb-h');
    var im = state.images.filter(function (x) { return x.key === selectedImg; })[0];
    if (!im) return;
    e.preventDefault(); e.stopPropagation();
    var r = ui.imgs.getBoundingClientRect();
    var sx = e.clientX, sy = e.clientY;
    var o = { x: im.x, y: im.y, w: im.w, h: im.h };
    var dir = h ? h.dataset.d : '';
    var MINW = 0.08, MINH = 0.06;
    function mv(ev) {
      var dx = (ev.clientX - sx) / r.width, dy = (ev.clientY - sy) / r.height;
      if (!dir) {   // 移动
        im.x = Math.min(Math.max(o.x + dx, 0), 1 - o.w);
        im.y = Math.min(Math.max(o.y + dy, 0), 1 - o.h);
      } else {      // 上下左右自由拉伸
        if (dir.indexOf('e') !== -1) im.w = Math.max(MINW, Math.min(o.w + dx, 1 - o.x));
        if (dir.indexOf('s') !== -1) im.h = Math.max(MINH, Math.min(o.h + dy, 1 - o.y));
        if (dir.indexOf('w') !== -1) {
          im.w = Math.max(MINW, Math.min(o.w - dx, o.x + o.w));
          im.x = o.x + o.w - im.w;
        }
        if (dir.indexOf('n') !== -1) {
          im.h = Math.max(MINH, Math.min(o.h - dy, o.y + o.h));
          im.y = o.y + o.h - im.h;
        }
      }
      syncSelBox(im);
      syncItemStyle(im);
    }
    function up() {
      window.removeEventListener('pointermove', mv);
      window.removeEventListener('pointerup', up);
      saveSoon();
    }
    window.addEventListener('pointermove', mv);
    window.addEventListener('pointerup', up);
  });

  /* 第 3 层：笔迹（橡皮 = destination-out 真擦除，只作用于本层） */
  function strokePath(s) {
    if (s.pts.length < 2 && !s.erase) return;
    if (s.erase) {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.strokeStyle = 'rgba(0,0,0,1)';
      ctx.lineWidth = s.size;
    } else {
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.size;
    }
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(s.pts[0][0] * W, s.pts[0][1] * H);
    for (var i = 1; i < s.pts.length; i++) ctx.lineTo(s.pts[i][0] * W, s.pts[i][1] * H);
    ctx.stroke();
    ctx.globalCompositeOperation = 'source-over';
  }
  function redrawStrokes() {
    ctx.clearRect(0, 0, W, H);
    state.strokes.forEach(strokePath);
  }
  function drawBoard() {
    drawGridLayer();
    renderImages();
    redrawStrokes();
    renderTexts();
  }
  function renderTexts() {
    var focus = document.activeElement;
    var activeKey = focus && focus.dataset ? focus.dataset.key : null;
    ui.texts.innerHTML = '';
    state.texts.forEach(function (t) {
      var d = el('div', 'cb-text');
      d.contentEditable = 'true';
      d.spellcheck = false;
      d.dataset.key = t.key;
      if (t.fs) d.style.fontSize = t.fs + 'px';
      d.textContent = t.text === undefined ? '' : t.text;
      d.style.left = (t.x * 100) + '%';
      d.style.top = (t.y * 100) + '%';
      d.style.maxWidth = '72%';
      /* 移动手柄：四向箭头图标，拖动调整位置（纯 SVG，不占文字内容） */
      var mv = el('span', 'cb-tmv');
      mv.title = '拖动移动';
      mv.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"/></svg>';
      mv.addEventListener('pointerdown', function (e) {
        e.preventDefault(); e.stopPropagation();
        try { d.blur(); } catch (err) {}
        state._textDrag = t.key;
        var r = ui.texts.getBoundingClientRect();
        var sx = e.clientX, sy = e.clientY, ox = t.x, oy = t.y;
        function mv2(ev) {
          t.x = Math.min(Math.max(ox + (ev.clientX - sx) / r.width, 0), 0.98);
          t.y = Math.min(Math.max(oy + (ev.clientY - sy) / r.height, 0), 0.96);
          var live = ui.texts.querySelector('[data-key="' + t.key + '"]');
          if (live) { live.style.left = (t.x * 100) + '%'; live.style.top = (t.y * 100) + '%'; }
        }
        function up2() {
          window.removeEventListener('pointermove', mv2);
          window.removeEventListener('pointerup', up2);
          state._textDrag = null;
          drawBoard();
          saveSoon();
        }
        window.addEventListener('pointermove', mv2);
        window.addEventListener('pointerup', up2);
      });
      /* 字号角柄：拖动等比缩放字号 */
      var rz = el('span', 'cb-trz');
      rz.addEventListener('pointerdown', function (e) {
        e.preventDefault(); e.stopPropagation();
        var dr = d.getBoundingClientRect();
        var d0 = Math.hypot(e.clientX - dr.left, e.clientY - dr.top) || 1;
        var of = t.fs || 15;
        state._textDrag = t.key;
        function mv2(ev) {
          var dd = Math.hypot(ev.clientX - dr.left, ev.clientY - dr.top);
          t.fs = Math.min(60, Math.max(10, Math.round(of * dd / d0)));
          var live = ui.texts.querySelector('[data-key="' + t.key + '"]');
          if (live) live.style.fontSize = t.fs + 'px';
        }
        function up2() {
          window.removeEventListener('pointermove', mv2);
          window.removeEventListener('pointerup', up2);
          state._textDrag = null;
          drawBoard();
          saveSoon();
        }
        window.addEventListener('pointermove', mv2);
        window.addEventListener('pointerup', up2);
      });
      d.appendChild(mv);
      d.appendChild(rz);
      d.addEventListener('input', function () {
        t.text = d.textContent;
        t.h = d.offsetHeight / ui.texts.offsetHeight;
        saveSoon();
      });
      d.addEventListener('blur', function () {
        if (state._textDrag === t.key) return;   // 拖动中不重建 DOM
        if (!d.textContent.trim()) {
          removeItem(t.key);
          saveSoon();
        }
        drawBoard();
      });
      if (t.key === activeKey) { d.focus(); }
      ui.texts.appendChild(d);
    });
    return ui.texts.lastElementChild;
  }

  /* ---------- 交互：绘制 / 打字 ---------- */
  var drawing = null;
  function pos(e) {
    var r = ui.canvas.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
  }
  ui.canvas.addEventListener('pointerdown', function (e) {
    e.preventDefault(); // 关键：阻止画布把焦点从新建文本框夺走（否则文本框刚建即被清空）
    if (selectedImg) { deselectImage(); return; }   // 已选中截图：先点击空白取消选中
    if (state.mode === 'text') {
      var p = pos(e);
      var t = { key: 't' + (++state.seq), x: Math.min(p[0], .6), y: Math.min(p[1], .85), text: '', h: 0, fs: 15 };
      state.texts.push(t);
      state.hist.push(t.key);
      saveSoon();
      var node = renderTexts();
      if (node) node.focus();
      return;
    }
    ui.canvas.setPointerCapture(e.pointerId);
    var eraser = state.mode === 'eraser';
    var key = 's' + (++state.seq);
    drawing = eraser
      ? { key: key, erase: true, size: state.eraserSize, pts: [pos(e)] }
      : { key: key, color: state.color, size: state.size, pts: [pos(e)] };
    state.strokes.push(drawing);
    state.hist.push(key);
  });
  ui.canvas.addEventListener('pointermove', function (e) {
    if (!drawing) return;
    drawing.pts.push(pos(e));
    redrawStrokes();
  });
  function endStroke() {
    if (!drawing) return;
    drawing = null;
    saveSoon();
  }
  ui.canvas.addEventListener('pointerup', endStroke);
  ui.canvas.addEventListener('pointercancel', endStroke);

  /* ---------- 撤销 / 清空 / 导出 ---------- */
  function removeItem(key) {
    state.strokes = state.strokes.filter(function (s) { return s.key !== key; });
    state.images = state.images.filter(function (i) { return i.key !== key; });
    state.texts = state.texts.filter(function (t) { return t.key !== key; });
    state.hist = state.hist.filter(function (k) { return k !== key; });
    delete imgCache[key];
  }
  function undo() {
    var key = state.hist.pop();
    if (!key) return;
    removeItem(key);
    drawBoard();
    saveSoon();
  }
  function clearBoard() {
    if (state.hist.length === 0) return;
    if (!confirm('确定清空白板上的全部内容（含截图）？')) return;
    state.strokes = []; state.images = []; state.texts = []; state.hist = [];
    imgCache = {};
    drawBoard(); saveSoon();
  }
  function exportPNG() {
    var c = document.createElement('canvas');
    c.width = W; c.height = H;
    var g = c.getContext('2d');
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, W, H);
    state.images.forEach(function (im) {
      var img = imgCache[im.key];
      if (img && img.complete && img.naturalWidth) g.drawImage(img, im.x * W, im.y * H, im.w * W, im.h * H);
    });
    state.strokes.forEach(function (s) {
      if (s.erase || s.pts.length < 2) return;
      g.strokeStyle = s.color; g.lineWidth = s.size;
      g.lineCap = 'round'; g.lineJoin = 'round';
      g.beginPath();
      g.moveTo(s.pts[0][0] * W, s.pts[0][1] * H);
      for (var i = 1; i < s.pts.length; i++) g.lineTo(s.pts[i][0] * W, s.pts[i][1] * H);
      g.stroke();
    });
    g.fillStyle = '#1e293b';
    state.texts.forEach(function (t) {
      if (!t.text) return;
      var fs = t.fs || 15;
      g.font = Math.round(fs * 1.87) + 'px "Microsoft YaHei", sans-serif';
      (t.text.split('\n')).forEach(function (line, i) {
        g.fillText(line, t.x * W + 4, t.y * H + Math.round(fs * 1.87) + i * Math.round(fs * 1.9));
      });
    });
    var a = document.createElement('a');
    var d = new Date();
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    a.download = '随心记录-' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '-' + pad(d.getHours()) + pad(d.getMinutes()) + '.png';
    a.href = c.toDataURL('image/png');
    a.click();
  }

  /* 双击画板：选中/取消截图图片（可拖动 / 缩放） */
  ui.canvas.addEventListener('dblclick', function (e) {
    var p = pos(e);
    var hit = null;
    for (var i = state.images.length - 1; i >= 0; i--) {
      var im = state.images[i];
      if (p[0] >= im.x && p[0] <= im.x + im.w && p[1] >= im.y && p[1] <= im.y + im.h) { hit = im; break; }
    }
    if (hit) selectImage(hit.key);
    else deselectImage();
  });

  /* ---------- 截图：html2canvas 捕获整页 → 自由框选裁剪 → 插入画板 ---------- */
  var shotLibLoading = false;
  function loadShotLib(cb, fail) {
    if (window.html2canvas) return cb();
    if (shotLibLoading) return;
    shotLibLoading = true;
    var s = document.createElement('script');
    s.src = 'html2canvas.min.js';
    s.onload = function () { shotLibLoading = false; cb(); };
    s.onerror = function () { shotLibLoading = false; fail(); };
    document.head.appendChild(s);
  }
  function doScreenshot() {
    loadShotLib(function () {
      deselectImage();
      // 截图与框选期间画板保持收起（不遮挡选区），完成或取消后再恢复
      panel.classList.remove('show');
      fab.style.display = 'none';
      setTimeout(function () {
        html2canvas(document.body, {
          backgroundColor: '#ffffff',
          scale: Math.min(1.5, 1600 / Math.max(innerWidth, 800)),
          ignoreElements: function (elm) {
            return elm.classList && (elm.classList.contains('cb-panel') || elm.classList.contains('cb-fab'));
          }
        }).then(function (full) {
          startRegionSelect(full, function () {
            CyberBoard.open();
            fab.style.display = '';
          });
        }).catch(function () {
          CyberBoard.open();
          fab.style.display = '';
          alert('截图失败，请重试');
        });
      }, 80);
    }, function () {
      alert('截图组件（html2canvas.min.js）加载失败：请确认文件存在于网站根目录，或检查网络。');
    });
  }

  /* 自由框选：半透明遮罩上拖拽出截图区域，Esc 取消；完成/取消后恢复画板 */
  var shotFull = null, shotScale = 1, shotUI = null;
  function startRegionSelect(full, onDone) {
    shotFull = full;
    shotScale = Math.min(1.5, 1600 / Math.max(innerWidth, 800));
    shotUI = el('div', 'cb-shotui');
    shotUI.innerHTML = '<div class="cb-fullmask"></div>' +
      '<div class="cb-rect"></div><div class="cb-size"></div>' +
      '<div class="cb-tipbar">按住鼠标拖拽，框选要截取的区域 · 松开完成 · Esc 取消</div>';
    document.body.appendChild(shotUI);
    var rectD = shotUI.querySelector('.cb-rect');
    var sizeD = shotUI.querySelector('.cb-size');
    var sx = 0, sy = 0, dragging = false;
    function upd(x0, y0, x1, y1) {
      var x = Math.min(x0, x1), y = Math.min(y0, y1);
      var w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
      rectD.style.left = x + 'px'; rectD.style.top = y + 'px';
      rectD.style.width = w + 'px'; rectD.style.height = h + 'px';
      sizeD.style.left = x + 'px';
      sizeD.style.top = Math.min(y + h + 6, innerHeight - 26) + 'px';
      sizeD.textContent = Math.round(w) + ' × ' + Math.round(h);
    }
    function down(e) {
      if (e.button !== 0) return;
      e.preventDefault();
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      rectD.style.display = 'block'; sizeD.style.display = 'block';
      upd(sx, sy, sx, sy);
    }
    function move(e) { if (dragging) upd(sx, sy, e.clientX, e.clientY); }
    function up(e) {
      if (!dragging) return;
      dragging = false;
      var w = Math.abs(e.clientX - sx), h = Math.abs(e.clientY - sy);
      endSelect();
      if (w < 8 || h < 8) { if (onDone) onDone(); return; }   // 单击 / 过小选择视为取消
      finishRegion({ x: Math.min(sx, e.clientX), y: Math.min(sy, e.clientY), w: w, h: h });
      if (onDone) onDone();
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); endSelect(); if (onDone) onDone(); }
    }
    function endSelect() {
      document.removeEventListener('pointermove', move, true);
      document.removeEventListener('pointerup', up, true);
      document.removeEventListener('keydown', onKey, true);
      if (shotUI && shotUI.parentNode) shotUI.parentNode.removeChild(shotUI);
      shotUI = null;
    }
    shotUI.addEventListener('pointerdown', down);
    shotUI.addEventListener('wheel', function (ev) { ev.preventDefault(); }, { passive: false });
    document.addEventListener('pointermove', move, true);
    document.addEventListener('pointerup', up, true);
    document.addEventListener('keydown', onKey, true);
  }
  function finishRegion(rect) {
    var s = shotScale;
    var docX = rect.x + window.scrollX, docY = rect.y + window.scrollY;
    var outScale = Math.min(s, 1600 / Math.max(rect.w, 40));   // 控制产出尺寸上限
    var c = document.createElement('canvas');
    c.width = Math.max(2, Math.round(rect.w * outScale));
    c.height = Math.max(2, Math.round(rect.h * outScale));
    c.getContext('2d').drawImage(shotFull, docX * s, docY * s, rect.w * s, rect.h * s, 0, 0, c.width, c.height);
    insertImage(c, c.width, c.height);
  }
  /* 裁剪结果插入画板：等比缩放居中放置，并自动选中（可拖动 / 缩放） */
  function insertImage(canvas, w, h) {
    var maxW = W * 0.7, maxH = H * 0.7;
    var sc = Math.min(maxW / w, maxH / h, 1);
    var key = 'i' + (++state.seq);
    var im = {
      key: key,
      data: canvas.toDataURL('image/jpeg', 0.88),
      x: (W - w * sc) / 2 / W,
      y: (H - h * sc) / 2 / H,
      w: w * sc / W,
      h: h * sc / H
    };
    state.images.push(im);
    state.hist.push(key);
    drawBoard();
    selectImage(key);
    saveSoon();
    setMode('pen');
  }

  /* ---------- 拖动 / 缩放 / 开关 ---------- */
  function drag(e, onMove) {
    var sx = e.clientX, sy = e.clientY;
    function mv(ev) { onMove(ev.clientX - sx, ev.clientY - sy); sx = ev.clientX; sy = ev.clientY; }
    function up() {
      window.removeEventListener('pointermove', mv);
      window.removeEventListener('pointerup', up);
    }
    window.addEventListener('pointermove', mv);
    window.addEventListener('pointerup', up);
  }
  ui.head.addEventListener('pointerdown', function (e) {
    if (e.target.closest('button')) return;
    e.preventDefault();
    var r = panel.getBoundingClientRect();
    panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px';
    panel.style.right = 'auto'; panel.style.bottom = 'auto';
    drag(e, function (dx, dy) {
      var x = Math.min(Math.max(panel.offsetLeft + dx, -r.width + 80), innerWidth - 80);
      var y = Math.min(Math.max(panel.offsetTop + dy, 0), innerHeight - 44);
      panel.style.left = x + 'px'; panel.style.top = y + 'px';
    });
  });
  ui.resize.addEventListener('pointerdown', function (e) {
    e.preventDefault(); e.stopPropagation();
    drag(e, function (dx, dy) {
      panel.style.width = Math.max(380, panel.offsetWidth + dx) + 'px';
      panel.style.height = Math.max(320, panel.offsetHeight + dy) + 'px';
    });
  });

  function open() {
    panel.classList.add('show');
    clampIntoView();
    drawBoard();
  }
  function close() { panel.classList.remove('show'); }
  function toggle() { panel.classList.contains('show') ? close() : open(); }
  function clampIntoView() {
    var r = panel.getBoundingClientRect();
    if (r.right > innerWidth - 8) { panel.style.left = Math.max(8, innerWidth - r.width - 8) + 'px'; panel.style.right = 'auto'; }
    if (r.bottom > innerHeight - 8) { panel.style.top = Math.max(8, innerHeight - r.height - 8) + 'px'; panel.style.bottom = 'auto'; }
  }
  fab.addEventListener('click', toggle);
  panel.querySelector('.cb-close').addEventListener('click', close);
  panel.querySelector('.cb-min').addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (shotUI) return;   // 截图框选模式：由其捕获阶段处理取消
    if (selectedImg) { deselectImage(); return; }   // 先取消截图选中态
    if (panel.classList.contains('show') &&
        !(document.activeElement && document.activeElement.classList.contains('cb-text'))) close();
  });

  /* ---------- 本地持久化 ---------- */
  var saveTimer = null;
  function saveSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify({
          strokes: state.strokes, images: state.images, texts: state.texts,
          seq: state.seq, hist: state.hist, bg: state.bg
        }));
        ui.saved.style.opacity = '1';
        setTimeout(function () { ui.saved.style.opacity = '0'; }, 1400);
      } catch (e) {
        /* 存储满（截图较多时可能发生）：提示一次 */
        ui.saved.textContent = '本地空间不足，新截图刷新后将不保留';
        ui.saved.style.opacity = '1';
        setTimeout(function () { ui.saved.style.opacity = '0'; ui.saved.textContent = '已自动保存'; }, 2200);
      }
    }, 400);
  }
  (function restore() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      state.strokes = d.strokes || [];
      state.texts = d.texts || [];
      state.images = d.images || [];
      state.bg = d.bg === 'blank' ? 'blank' : 'grid';
      state.seq = d.seq || 0;
      if (d.hist) {
        state.hist = d.hist;
      } else {
        // 旧版数据迁移：按 seq 顺序重建历史；旧橡皮（画底色）转换为真擦除
        var keys = [];
        state.strokes.forEach(function (s) {
          if (s.color === '#f7f9fc') { s.erase = true; delete s.color; }
          var n = parseInt(String(s.key).slice(1), 10); if (!isNaN(n)) keys.push([n, s.key]);
        });
        state.texts.forEach(function (t) {
          var n = parseInt(String(t.key).slice(1), 10); if (!isNaN(n)) keys.push([n, t.key]);
        });
        keys.sort(function (a, b) { return a[0] - b[0]; });
        state.hist = keys.map(function (k) { return k[1]; });
      }
    } catch (e) { /* 数据损坏时忽略 */ }
  })();

  window.CyberBoard = { open: open, close: close, toggle: toggle };
})();
