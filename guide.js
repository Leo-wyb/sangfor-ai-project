/* CyberNWT · 新手引导（Apple 风格聚光灯 Coach Marks）——通用引擎
 *
 * 页面接入：引入本文件（defer），并设置全局配置：
 *   window.CyberGuideSteps = {
 *     key: 'home-v1',          // 记忆键：看过的页面不再自动弹出
 *     steps: [ ... ]
 *   };
 * 符合条件时首次进入自动播放；页脚放 <a id="cg-replay"> 可手动重播。
 *
 * 步骤字段：
 *   target     CSS 选择器；缺省 = 居中欢迎/结束卡（无聚光灯）
 *   spot       无 target 时可选：{ w, h, cx?, cy? } 按视口比例画居中聚光框
 *              （w/h 为框占视口比例，cx/cy 为框中心位置，缺省 0.5 居中）
 *   placement  'bottom'|'top'|'left'|'right'（缺省自动择位，放不下自动翻转）
 *   enter/exit 进入/离开该步骤的前置动作（如展开手风琴卡片）
 *   nextLabel  覆盖「下一步」文案（最后一步如「开始探索」）
 *
 * 手动播放：CyberGuide.start(steps, key)。
 * 交互：下一步/上一步/跳过按钮、步骤圆点直达、键盘 ←/→/Esc、Tab 圈定在卡片内。
 */
(function () {
  'use strict';

  /* ---------- 样式（全部 cg- 前缀，深浅色随页面主题变量） ---------- */
  var CSS = [
    '.cg-root{position:fixed;inset:0;z-index:10000;',
    '  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;}',
    '.cg-root[hidden]{display:none;}',

    /* 遮罩：四块矩形围出聚光灯挖孔，目标区域可真实交互 */
    '.cg-shade{position:fixed;background:rgba(5,8,13,.6);',
    '  transition:all .45s cubic-bezier(.4,0,.2,1);}',
    /* 后台标签页里 CSS 过渡会被冻结在起始帧，此时改为即时定位保证位置始终正确 */
    '.cg-root.cg-frozen .cg-shade,.cg-root.cg-frozen .cg-ring{transition:none!important;}',
    '.cg-root.cg-frozen .cg-card,.cg-root.cg-frozen .cg-card.cg-in{animation:none!important;opacity:1;}',

    /* 聚光灯描边：冰蓝呼吸光圈（与登录页提示同色系） */
    '.cg-ring{position:fixed;display:none;pointer-events:none;border-radius:14px;',
    '  border:1.5px solid rgba(190,224,255,.95);',
    '  transition:all .45s cubic-bezier(.4,0,.2,1);',
    '  animation:cg-pulse 2.4s ease-in-out infinite;}',
    '@keyframes cg-pulse{',
    '  0%,100%{box-shadow:0 0 0 4px rgba(126,190,244,.2),0 0 22px rgba(126,190,244,.35);}',
    '  50%{box-shadow:0 0 0 9px rgba(126,190,244,.1),0 0 34px rgba(126,190,244,.5);}}',

    /* 引导卡片：玻璃拟态，随主题变量 */
    '.cg-card{position:fixed;width:min(340px,calc(100vw - 24px));padding:16px 20px 13px;',
    '  border-radius:14px;background:var(--panel,rgba(24,30,38,.94));',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.22));color:var(--text,#EDEDED);',
    '  backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);',
    '  box-shadow:0 20px 55px rgba(0,0,0,.5);}',
    '.cg-card.cg-in{animation:cg-in .28s ease both;}',
    '@keyframes cg-in{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:none;}}',
    /* 大卡模式（步骤 big:true）：卡片放大到指定视口比例，文字按钮等比增大，内容垂直居中 */
    '.cg-card.cg-big{width:min(48.5vw,calc(100vw - 24px));min-height:59vh;',
    '  display:flex;flex-direction:column;justify-content:center;padding:34px 46px;}',
    '.cg-card.cg-big .cg-tag{font-size:13px;letter-spacing:2.5px;}',
    '.cg-card.cg-big .cg-title{font-size:30px;margin:12px 0 10px;}',
    '.cg-card.cg-big .cg-desc{font-size:17px;line-height:2;margin-bottom:24px;}',
    '.cg-card.cg-big .cg-dots{gap:7px;}',
    '.cg-card.cg-big .cg-dot{width:8px;height:8px;border-radius:4px;}',
    '.cg-card.cg-big .cg-dot.on{width:22px;}',
    '.cg-card.cg-big .cg-skip{font-size:14px;height:36px;}',
    '.cg-card.cg-big .cg-btn{height:38px;padding:0 20px;border-radius:9px;font-size:14px;}',
    '.cg-card.cg-big .cg-arrow{display:none!important;}',
    '.cg-tag{font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:10px;font-weight:600;letter-spacing:2px;color:var(--text-2,#9CA3AF);}',
    '.cg-title{font-size:16.5px;font-weight:700;margin:7px 0 6px;}',
    '.cg-desc{font-size:13px;line-height:1.8;color:var(--text-2,#9CA3AF);margin-bottom:13px;}',

    /* 指向箭头：与卡片同底色同模糊同边框，按朝向只描外侧两边 */
    '.cg-arrow{position:absolute;width:13px;height:13px;transform:rotate(45deg);display:none;',
    '  background:var(--panel,rgba(24,30,38,.94));',
    '  backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);}',
    '.cg-arrow.cg-a-up{top:-7px;',
    '  border-left:1px solid var(--panel-border,rgba(205,214,224,.22));',
    '  border-top:1px solid var(--panel-border,rgba(205,214,224,.22));}',
    '.cg-arrow.cg-a-down{bottom:-7px;',
    '  border-right:1px solid var(--panel-border,rgba(205,214,224,.22));',
    '  border-bottom:1px solid var(--panel-border,rgba(205,214,224,.22));}',
    '.cg-arrow.cg-a-left{left:-7px;',
    '  border-left:1px solid var(--panel-border,rgba(205,214,224,.22));',
    '  border-bottom:1px solid var(--panel-border,rgba(205,214,224,.22));}',
    '.cg-arrow.cg-a-right{right:-7px;',
    '  border-right:1px solid var(--panel-border,rgba(205,214,224,.22));',
    '  border-top:1px solid var(--panel-border,rgba(205,214,224,.22));}',

    /* 底部：圆点分页 + 按钮 */
    '.cg-foot{display:flex;align-items:center;}',
    '.cg-dots{display:flex;gap:5px;flex:1;}',
    '.cg-dot{width:6px;height:6px;border-radius:3px;border:0;padding:0;font-family:inherit;',
    '  background:var(--prog-track,rgba(255,255,255,.2));cursor:pointer;transition:all .25s;}',
    '.cg-dot:hover{background:var(--text-2,#9CA3AF);}',
    '.cg-dot.on{width:16px;background:var(--accent,#fff);}',
    '.cg-skip{background:none;border:0;color:var(--text-2,#9CA3AF);font-size:12px;',
    '  cursor:pointer;padding:0 6px;height:30px;font-family:inherit;transition:color .2s;}',
    '.cg-skip:hover{color:var(--text,#EDEDED);}',
    '.cg-btn{height:30px;padding:0 14px;border-radius:7px;font-size:12.5px;cursor:pointer;',
    '  line-height:1;font-family:inherit;margin-left:8px;transition:filter .2s,color .2s,border-color .2s;}',
    '.cg-prev{background:transparent;border:1px solid var(--border,rgba(205,214,224,.2));',
    '  color:var(--text-2,#9CA3AF);}',
    '.cg-prev:hover{color:var(--text,#EDEDED);border-color:var(--accent-border,rgba(255,255,255,.4));}',
    '.cg-next{border:1px solid var(--accent,#fff);background:var(--accent,#fff);',
    '  color:var(--accent-contrast,#0A0A0A);font-weight:700;letter-spacing:1px;}',
    '.cg-next:hover{filter:brightness(.92);}',
    '[data-theme="light"] .cg-next{border-color:var(--accent,#0A0A0A);background:var(--accent,#0A0A0A);color:var(--accent-contrast,#FAFAFA);}'
  ].join('\n');

  /* ---------- 元素与状态 ---------- */
  var root, shades = [], ring, card, arrow, tagEl, titleEl, descEl, dotsEl,
      skipBtn, prevBtn, nextBtn;
  var steps = [], idx = -1, running = false, cfgKey = 'manual', timers = [];

  function el(parent, tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    parent.appendChild(e);
    return e;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(v, hi)); }
  function targetEl(s) { return s.target ? document.querySelector(s.target) : null; }
  function clearTimers() { timers.forEach(clearTimeout); timers = []; }
  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }

  function build() {
    if (root) return;
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    root = el(document.body, 'div', 'cg-root');
    root.hidden = true;
    for (var i = 0; i < 4; i++) shades.push(el(root, 'div', 'cg-shade'));
    ring = el(root, 'div', 'cg-ring');
    card = el(root, 'div', 'cg-card');
    arrow = el(card, 'div', 'cg-arrow');
    tagEl = el(card, 'div', 'cg-tag');
    titleEl = el(card, 'h4', 'cg-title');
    descEl = el(card, 'p', 'cg-desc');
    var foot = el(card, 'div', 'cg-foot');
    dotsEl = el(foot, 'div', 'cg-dots');
    skipBtn = el(foot, 'button', 'cg-skip');
    skipBtn.type = 'button'; skipBtn.textContent = '跳过';
    prevBtn = el(foot, 'button', 'cg-btn cg-prev');
    prevBtn.type = 'button'; prevBtn.textContent = '上一步';
    nextBtn = el(foot, 'button', 'cg-btn cg-next');
    nextBtn.type = 'button'; nextBtn.textContent = '下一步';

    skipBtn.addEventListener('click', function () { finish(); });
    prevBtn.addEventListener('click', function () { go(-1); });
    nextBtn.addEventListener('click', function () { go(1); });

    // 后台标签页冻结过渡 → 即时定位；回前台恢复动画并校正一次位置
    document.addEventListener('visibilitychange', function () {
      root.classList.toggle('cg-frozen', document.hidden);
      if (!document.hidden) layout();
    });
    if (document.hidden) root.classList.add('cg-frozen');
  }

  /* ---------- 布局 ---------- */

  // 四块遮罩围出挖孔；r 为 null 时全屏遮罩（居中卡步骤）
  function setShades(r) {
    var w = window.innerWidth, h = window.innerHeight;
    if (!r) {
      shades[0].style.cssText = 'left:0;top:0;width:' + w + 'px;height:' + h + 'px;';
      for (var i = 1; i < 4; i++) shades[i].style.cssText = 'left:0;top:0;width:0;height:0;';
      return;
    }
    shades[0].style.cssText = 'left:0;top:0;width:' + w + 'px;height:' + Math.max(0, r.top) + 'px;';
    shades[1].style.cssText = 'left:0;top:' + r.bottom + 'px;width:' + w + 'px;height:' + Math.max(0, h - r.bottom) + 'px;';
    shades[2].style.cssText = 'left:0;top:' + r.top + 'px;width:' + Math.max(0, r.left) + 'px;height:' + (r.bottom - r.top) + 'px;';
    shades[3].style.cssText = 'left:' + r.right + 'px;top:' + r.top + 'px;width:' + Math.max(0, w - r.right) + 'px;height:' + (r.bottom - r.top) + 'px;';
  }

  // 卡片定位：优先 placement，放不下按 下→上→右→左 兜底，再不行底部居中
  function placeCard(r, pref) {
    var gap = 18, m = 12;
    var cw = card.offsetWidth, ch = card.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight;
    var x, y, side = null;

    if (!r) {
      x = (vw - cw) / 2;
      y = (vh - ch) / 2 - Math.round(vh * 0.03);
    } else {
      var order = (pref && pref !== 'center') ? [pref] : ['bottom', 'top', 'right', 'left'];
      ['bottom', 'top', 'right', 'left'].forEach(function (s) {
        if (order.indexOf(s) < 0) order.push(s);
      });
      for (var i = 0; i < order.length; i++) {
        var sd = order[i];
        // 上下站位只看垂直空间（水平超界则收敛到视口内，箭头随中心偏移）；
        // 左右站位同理只看水平空间
        if (sd === 'bottom') {
          x = clamp(r.left + r.width / 2 - cw / 2, m, vw - cw - m);
          y = r.bottom + gap;
          if (y + ch <= vh - m) { side = sd; break; }
        } else if (sd === 'top') {
          x = clamp(r.left + r.width / 2 - cw / 2, m, vw - cw - m);
          y = r.top - gap - ch;
          if (y >= m) { side = sd; break; }
        } else if (sd === 'right') {
          x = r.right + gap;
          y = clamp(r.top + r.height / 2 - ch / 2, m, vh - ch - m);
          if (x + cw <= vw - m) { side = sd; break; }
        } else {
          x = r.left - gap - cw;
          y = clamp(r.top + r.height / 2 - ch / 2, m, vh - ch - m);
          if (x >= m) { side = sd; break; }
        }
      }
      if (side === null) { x = (vw - cw) / 2; y = vh - ch - m - 16; }  // 底部兜底
      else { x = clamp(x, m, vw - cw - m); y = clamp(y, m, vh - ch - m); }
    }
    card.style.left = Math.round(x) + 'px';
    card.style.top = Math.round(y) + 'px';

    // 箭头：只有贴边站位才有；指向目标中心
    if (r && side) {
      arrow.style.display = 'block';
      arrow.className = 'cg-arrow';
      var ac = 'cg-a-' + (side === 'bottom' ? 'up' : side === 'top' ? 'down' : side === 'right' ? 'left' : 'right');
      arrow.classList.add(ac);
      if (side === 'bottom' || side === 'top') {
        arrow.style.left = clamp(r.left + r.width / 2 - x - 6.5, 14, cw - 27) + 'px';
        arrow.style.top = 'auto'; arrow.style.bottom = 'auto'; arrow.style.right = 'auto';
      } else {
        arrow.style.top = clamp(r.top + r.height / 2 - y - 6.5, 14, ch - 27) + 'px';
        arrow.style.left = 'auto'; arrow.style.right = 'auto'; arrow.style.bottom = 'auto';
      }
    } else {
      arrow.style.display = 'none';
    }
  }

  function layout() {
    if (!running) return;
    var s = steps[idx];
    if (!s) return;
    var t = s._el;
    if (t) {
      var r = t.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) { skipHidden(); return; }  // 目标不可见 → 跳过该步
      var p = 8;  // 挖孔比目标大一圈，留呼吸感
      var hole = { left: r.left - p, top: r.top - p, right: r.right + p, bottom: r.bottom + p };
      setShades(hole);
      ring.style.display = 'block';
      ring.style.left = hole.left + 'px';
      ring.style.top = hole.top + 'px';
      ring.style.width = (hole.right - hole.left) + 'px';
      ring.style.height = (hole.bottom - hole.top) + 'px';
      placeCard(r, s.placement);
    } else if (s.spot) {
      // 无目标元素：按视口比例画居中聚光框（欢迎/总结步骤用）
      var vw = window.innerWidth, vh = window.innerHeight;
      var sw = Math.round(vw * (s.spot.w || 0.5));
      var sh = Math.round(vh * (s.spot.h || 0.5));
      var scx = vw * (s.spot.cx === undefined ? 0.5 : s.spot.cx);
      var scy = vh * (s.spot.cy === undefined ? 0.5 : s.spot.cy);
      var sHole = {
        left: Math.round(scx - sw / 2), top: Math.round(scy - sh / 2),
        right: Math.round(scx + sw / 2), bottom: Math.round(scy + sh / 2)
      };
      setShades(sHole);
      ring.style.display = 'block';
      ring.style.left = sHole.left + 'px';
      ring.style.top = sHole.top + 'px';
      ring.style.width = (sHole.right - sHole.left) + 'px';
      ring.style.height = (sHole.bottom - sHole.top) + 'px';
      placeCard(null);  // 卡片保持居中
    } else {
      setShades(null);
      ring.style.display = 'none';
      placeCard(null);
    }
  }

  /* ---------- 步骤流转 ---------- */

  function buildDots() {
    dotsEl.innerHTML = '';
    steps.forEach(function (_, i) {
      var d = el(dotsEl, 'button', 'cg-dot');
      d.type = 'button';
      d.setAttribute('aria-label', '第 ' + (i + 1) + ' 步');
      d.addEventListener('click', function () { if (i !== idx) jump(i); });
    });
  }

  function syncDots() {
    Array.prototype.forEach.call(dotsEl.children, function (d, i) {
      d.classList.toggle('on', i === idx);
    });
  }

  function renderCard(s) {
    tagEl.textContent = 'STEP ' + pad(idx + 1) + ' / ' + pad(steps.length);
    titleEl.textContent = s.title || '';
    descEl.textContent = s.desc || '';
    card.classList.toggle('cg-big', !!s.big);   // 大卡模式：本步卡片放大
    nextBtn.textContent = s.nextLabel || (idx === steps.length - 1 ? '完 成' : '下一步');
    prevBtn.style.visibility = idx === 0 ? 'hidden' : 'visible';
    skipBtn.style.visibility = idx === steps.length - 1 ? 'hidden' : 'visible';
    syncDots();
    card.classList.remove('cg-in');
    void card.offsetWidth;  // 重触发入场动画
    card.classList.add('cg-in');
  }

  function inViewport(t) {
    var r = t.getBoundingClientRect();
    return r.top >= 0 && r.left >= 0 && r.bottom <= window.innerHeight && r.right <= window.innerWidth;
  }

  function show(i) {
    idx = i;
    clearTimers();
    var s = steps[i];
    s._el = targetEl(s);
    if (s._el && !inViewport(s._el)) s._el.scrollIntoView({ block: 'center' });
    if (s.enter) { try { s.enter(); } catch (e) {} }
    renderCard(s);
    layout();
    if (s._el) [80, 260, 520, 880].forEach(function (ms) { later(layout, ms); });  // 目标自身有过渡时补跟
    nextBtn.focus({ preventScroll: true });
  }

  function jump(i) {
    var cur = steps[idx];
    if (cur && cur.exit) { try { cur.exit(); } catch (e) {} }
    show(i);
  }

  function go(d) {
    var ni = idx + d;
    if (ni >= steps.length) { finish(); return; }
    if (ni < 0) return;
    jump(ni);
  }

  // 目标元素不可见（如窄屏下导航隐藏）时跳过当前步
  function skipHidden() {
    steps.splice(idx, 1);
    if (!steps.length) { finish(); return; }
    buildDots();
    show(Math.min(idx, steps.length - 1));
  }

  function finish() {
    var cur = steps[idx];
    if (cur && cur.exit) { try { cur.exit(); } catch (e) {} }
    running = false;
    clearTimers();
    root.hidden = true;
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('resize', layout);
    try { localStorage.setItem('cyber-guide-' + cfgKey, 'done'); } catch (e) {}
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); finish(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
    else if (e.key === 'Tab') {  // 焦点圈定在卡片按钮内
      var list = Array.prototype.filter.call(
        card.querySelectorAll('button'),
        function (b) { return b.style.visibility !== 'hidden'; }
      );
      if (!list.length) return;
      var i = list.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); list[list.length - 1].focus(); }
      else if (!e.shiftKey && (i === list.length - 1 || i === -1)) { e.preventDefault(); list[0].focus(); }
    }
  }

  /* ---------- 对外 API ---------- */

  function start(stepList, key) {
    steps = (stepList || []).filter(function (s) {
      if (!s.target) return true;
      var t = document.querySelector(s.target);
      return !!(t && t.offsetWidth > 0);
    });
    if (!steps.length) return;
    build();
    if (running) finish();  // 重播时先收起旧场次
    cfgKey = key || 'manual';
    running = true;
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', layout);
    root.hidden = false;
    buildDots();
    show(0);
  }

  window.CyberGuide = { start: start };

  /* ---------- 自动接入：读 CyberGuideSteps 配置，页脚 #cg-replay 可重播 ---------- */
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    var cfg = window.CyberGuideSteps;
    var replay = document.getElementById('cg-replay');
    function replayStart() { if (cfg) CyberGuide.start(cfg.steps, cfg.key); }
    if (replay) replay.addEventListener('click', function (e) { e.preventDefault(); replayStart(); });
    if (!cfg) return;
    var seen = null;
    try { seen = localStorage.getItem('cyber-guide-' + cfg.key); } catch (e) {}
    if (!seen) setTimeout(function () { CyberGuide.start(cfg.steps, cfg.key); }, 900);
  });
})();
