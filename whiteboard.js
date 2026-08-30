/* CyberNWT · 随心记录 —— 全局悬浮白板组件
 * 在任意页面引入 <script src="whiteboard.js" defer></script> 即可：
 *   · 右下角悬浮按钮，点击弹出白板（不离开当前界面）
 *   · 自由手绘（4 色 / 3 粗细 / 橡皮 / 撤销）+ 点击白板任意处直接打字
 *   · 白板可拖动、可缩放、可最小化；内容自动保存到浏览器本地
 *   · 支持导出 PNG
 * 对外接口：CyberBoard.open() / .close() / .toggle()
 */
(function () {
  'use strict';

  var STORE_KEY = 'cybernwt.board.v1';
  var W = 1600, H = 1200;                 // 白板内部分辨率（与显示尺寸解耦，缩放不糊）
  var COLORS = ['#1e293b', '#2563eb', '#dc2626', '#16a34a'];
  var SIZES = [5, 11, 20];
  var state = { mode: 'pen', color: COLORS[0], size: 1, strokes: [], texts: [], seq: 0 };
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

    '.cb-tools{display:flex;align-items:center;gap:6px;padding:8px 12px;flex-wrap:wrap;',
    'border-bottom:1px solid var(--border,rgba(126,206,244,.14));}',
    '.cb-tools .grp{display:flex;gap:4px;padding:3px;border-radius:4px;background:var(--accent-bg,rgba(126,206,244,.08));}',
    '.cb-tbtn{border:none;background:transparent;color:var(--text-2,#cfe3f8);cursor:pointer;border-radius:4px;',
    'min-width:30px;height:28px;padding:0 8px;font-size:12.5px;display:flex;align-items:center;gap:4px;',
    'font-family:"Microsoft YaHei",sans-serif;transition:background .15s;}',
    '.cb-tbtn:hover{background:var(--accent-bg,rgba(126,206,244,.16));}',
    '.cb-tbtn.on{background:var(--accent,linear-gradient(135deg,#1a56c4,#0f8a5f));color:var(--accent-contrast,#fff);}',
    '.cb-sw{width:17px;height:17px;border-radius:50%;border:2px solid transparent;cursor:pointer;padding:0;flex:none;}',
    '.cb-sw.on{border-color:var(--accent,#fff);}',
    '.cb-undo{margin-left:auto;}',

    '.cb-body{position:relative;flex:1;overflow:hidden;background:#f7f9fc;}',
    '.cb-canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:crosshair;}',
    '.cb-canvas.text-mode{cursor:text;}',
    '.cb-texts{position:absolute;inset:0;pointer-events:none;}',
    '.cb-text{position:absolute;pointer-events:auto;outline:none;font:15px/1.5 "Microsoft YaHei",sans-serif;',
    'color:#1e293b;min-width:24px;padding:2px 4px;border-radius:4px;white-space:pre-wrap;word-break:break-all;}',
    '.cb-text:focus{background:var(--accent-bg,rgba(37,99,235,.07));box-shadow:0 0 0 1.5px var(--accent-border,rgba(37,99,235,.45));}',
    '.cb-text::placeholder{color:#94a3b8;}',

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
  var PEN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/></svg>';
  var fab = el('button', 'cb-fab');
  fab.title = '随心记录';
  fab.innerHTML = PEN_SVG;
  document.body.appendChild(fab);

  var panel = el('div', 'cb-panel');
  panel.innerHTML =
    '<div class="cb-head"><span class="dot"></span><b>随心记录</b>' +
    '<span class="cb-saved">已自动保存</span>' +
    '<button class="cb-min" title="收起">—</button><button class="cb-close" title="关闭">✕</button></div>' +
    '<div class="cb-tools"></div>' +
    '<div class="cb-body"><canvas class="cb-canvas"></canvas><div class="cb-texts"></div>' +
    '<div class="cb-resize"></div></div>' +
    '<div class="cb-hint">点击白板任意位置即可打字 · 内容自动保存本机 · Esc 关闭</div>';
  document.body.appendChild(panel);

  ui.head = panel.querySelector('.cb-head');
  ui.saved = panel.querySelector('.cb-saved');
  ui.tools = panel.querySelector('.cb-tools');
  ui.body = panel.querySelector('.cb-body');
  ui.canvas = panel.querySelector('.cb-canvas');
  ui.texts = panel.querySelector('.cb-texts');
  ui.resize = panel.querySelector('.cb-resize');
  var ctx = ui.canvas.getContext('2d');
  ui.canvas.width = W; ui.canvas.height = H;

  /* ---------- 工具栏 ---------- */
  var modeBtns = {};
  function toolBtn(label, title, cls, onclick) {
    var b = el('button', 'cb-tbtn' + (cls ? ' ' + cls : ''), label);
    b.title = title; b.type = 'button';
    b.addEventListener('click', onclick);
    ui.tools.appendChild(b);
    return b;
  }
  var penGrp = el('div', 'grp'); ui.tools.appendChild(penGrp);
  function setMode(m) {
    state.mode = m;
    ['pen', 'eraser', 'text'].forEach(function (k) {
      modeBtns[k].classList.toggle('on', k === m);
    });
    ui.canvas.classList.toggle('text-mode', m === 'text');
    if (m === 'text') drawBoard();
  }
  modeBtns.pen = toolBtn('✎ 画笔', '自由绘制', '', function () { setMode('pen'); });
  penGrp.appendChild(modeBtns.pen);
  COLORS.forEach(function (c, i) {
    var s = el('button', 'cb-sw' + (i === 0 ? ' on' : ''));
    s.type = 'button'; s.style.background = c; s.title = '颜色';
    s.addEventListener('click', function () {
      state.color = c;
      penGrp.querySelectorAll('.cb-sw').forEach(function (x) { x.classList.remove('on'); });
      s.classList.add('on');
      setMode('pen');
    });
    penGrp.appendChild(s);
  });
  [0, 1, 2].forEach(function (i) {
    var b = toolBtn('·'.repeat(i + 1) || '·', '笔迹粗细', i === 1 ? 'on' : '',
      function () {
        state.size = i;
        ui.tools.querySelectorAll('.cb-size').forEach(function (x) { x.classList.remove('on'); });
        b.classList.add('on'); setMode('pen');
      });
    b.classList.add('cb-size');
    if (i === 1) { state.size = 1; }
  });
  modeBtns.eraser = toolBtn(' ◠ 橡皮', '擦除笔迹', '', function () { setMode('eraser'); });
  modeBtns.text = toolBtn('T 打字', '点击白板处插入文字', '', function () { setMode('text'); });
  ui.tools.appendChild(el('div', 'grp'));
  toolBtn('↩ 撤销', '撤销上一步', 'cb-undo', undo);
  toolBtn('⇩ 导出', '导出 PNG', '', exportPNG);
  toolBtn('✕ 清空', '清空白板（不可恢复）', '', clearBoard);
  setMode('pen');

  /* ---------- 渲染 ---------- */
  function drawGrid() {
    ctx.fillStyle = '#f7f9fc';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(100,140,190,.12)';
    ctx.lineWidth = 1;
    for (var x = 40; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, H); ctx.stroke(); }
    for (var y = 40; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(W, y + .5); ctx.stroke(); }
  }
  function strokePath(s) {
    if (s.pts.length < 2) return;
    ctx.strokeStyle = s.color; ctx.lineWidth = s.size;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(s.pts[0][0] * W, s.pts[0][1] * H);
    for (var i = 1; i < s.pts.length; i++) ctx.lineTo(s.pts[i][0] * W, s.pts[i][1] * H);
    ctx.stroke();
  }
  function drawBoard() {
    drawGrid();
    state.strokes.forEach(strokePath);
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
      d.textContent = t.text === undefined ? '' : t.text;
      d.style.left = (t.x * 100) + '%';
      d.style.top = (t.y * 100) + '%';
      d.style.maxWidth = '72%';
      if (t.key === activeKey) { /* 恢复焦点由调用方处理 */ }
      d.addEventListener('input', function () {
        t.text = d.textContent;
        t.h = d.offsetHeight / ui.texts.offsetHeight;
        saveSoon();
      });
      d.addEventListener('blur', function () {
        if (!d.textContent.trim()) {
          state.texts = state.texts.filter(function (x) { return x.key !== t.key; });
          saveSoon();
        }
        drawBoard();
      });
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
    if (state.mode === 'text') {
      var p = pos(e);
      var t = { key: 't' + (++state.seq), x: Math.min(p[0], .86), y: Math.min(p[1], .92), text: '', h: 0 };
      state.texts.push(t);
      saveSoon();
      var node = renderTexts();
      if (node) node.focus();
      return;
    }
    ui.canvas.setPointerCapture(e.pointerId);
    var eraser = state.mode === 'eraser';
    drawing = { key: 's' + (++state.seq), color: eraser ? '#f7f9fc' : state.color, size: eraser ? SIZES[state.size] * 2.6 : SIZES[state.size], pts: [pos(e)] };
    state.strokes.push(drawing);
  });
  ui.canvas.addEventListener('pointermove', function (e) {
    if (!drawing) return;
    drawing.pts.push(pos(e));
    drawGrid();
    state.strokes.forEach(strokePath);
  });
  function endStroke() {
    if (!drawing) return;
    drawing = null;
    saveSoon();
  }
  ui.canvas.addEventListener('pointerup', endStroke);
  ui.canvas.addEventListener('pointercancel', endStroke);

  function undo() {
    var lastS = state.strokes[state.strokes.length - 1];
    var lastT = state.texts[state.texts.length - 1];
    if (!lastS && !lastT) return;
    if (lastS && (!lastT || lastS.key > lastT.key)) state.strokes.pop();
    else state.texts.pop();
    drawBoard();
    saveSoon();
  }
  function clearBoard() {
    if (state.strokes.length + state.texts.length === 0) return;
    if (!confirm('确定清空白板上的全部内容？')) return;
    state.strokes = []; state.texts = [];
    drawBoard(); saveSoon();
  }
  function exportPNG() {
    var c = document.createElement('canvas');
    c.width = W; c.height = H;
    var g = c.getContext('2d');
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, W, H);
    state.strokes.forEach(function (s) {
      if (s.pts.length < 2) return;
      g.strokeStyle = s.color; g.lineWidth = s.size;
      g.lineCap = 'round'; g.lineJoin = 'round';
      g.beginPath();
      g.moveTo(s.pts[0][0] * W, s.pts[0][1] * H);
      for (var i = 1; i < s.pts.length; i++) g.lineTo(s.pts[i][0] * W, s.pts[i][1] * H);
      g.stroke();
    });
    g.fillStyle = '#1e293b';
    g.font = '28px "Microsoft YaHei", sans-serif';
    state.texts.forEach(function (t) {
      if (!t.text) return;
      (t.text.split('\n')).forEach(function (line, i) {
        g.fillText(line, t.x * W + 4, t.y * H + 28 + i * 40);
      });
    });
    var a = document.createElement('a');
    var d = new Date();
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    a.download = '随心记录-' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '-' + pad(d.getHours()) + pad(d.getMinutes()) + '.png';
    a.href = c.toDataURL('image/png');
    a.click();
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
    if (e.key === 'Escape' && panel.classList.contains('show') &&
        !(document.activeElement && document.activeElement.classList.contains('cb-text'))) close();
  });

  /* ---------- 本地持久化 ---------- */
  var saveTimer = null;
  function saveSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify({ strokes: state.strokes, texts: state.texts, seq: state.seq }));
        ui.saved.style.opacity = '1';
        setTimeout(function () { ui.saved.style.opacity = '0'; }, 1400);
      } catch (e) { /* 存储满等情况静默 */ }
    }, 400);
  }
  (function restore() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      state.strokes = d.strokes || [];
      state.texts = d.texts || [];
      state.seq = d.seq || state.strokes.length + state.texts.length;
    } catch (e) { /* 数据损坏时忽略 */ }
  })();

  window.CyberBoard = { open: open, close: close, toggle: toggle };
})();
