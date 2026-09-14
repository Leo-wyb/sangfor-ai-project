/* 品牌 Logo 透镜效果（全页面页头通用）
   - logo + 名字绑定为整体对象；点击 / 回车 → 返回首页 home.html
   - 鼠标悬停出现小圆形透镜：圈内内容反色显示，跟随零延迟
   - 明亮主题 = 深色镜片/亮字；暗黑主题 = 浅色镜片/暗字                     */
(function () {
  'use strict';
  function init() {
    var logo = document.querySelector('header .logo');
    if (!logo || logo.dataset.lensBound) return;
    logo.dataset.lensBound = '1';

    var HOME = 'home.html';
    var D = 48;      // 镜片直径

    logo.classList.add('logo-home-link');
    logo.setAttribute('role', 'link');
    logo.setAttribute('tabindex', '0');
    logo.title = '返回首页';

    // 镜片：圆形窗口 + logo 克隆（反色），窗口中心 = 鼠标位置
    var lens = document.createElement('span');
    lens.className = 'logo-lens';
    lens.setAttribute('aria-hidden', 'true');
    var clone = document.createElement('span');
    clone.className = 'logo logo-lens-clone';
    clone.setAttribute('aria-hidden', 'true');
    for (var i = 0; i < logo.childNodes.length; i++) {
      clone.appendChild(logo.childNodes[i].cloneNode(true));
    }
    lens.appendChild(clone);
    logo.appendChild(lens);

    function apply(mx, my) {
      var r = logo.getBoundingClientRect();
      var cx = Math.max(0, Math.min(mx - r.left, r.width));
      var cy = Math.max(0, Math.min(my - r.top, r.height));
      lens.style.left = (cx - D / 2) + 'px';
      lens.style.top = (cy - D / 2) + 'px';
      // 克隆反向平移：透镜窗口里看到的正是鼠标下方那块内容的反色
      clone.style.left = -(cx - D / 2) + 'px';
      clone.style.top = -(cy - D / 2) + 'px';
      lens.classList.add('on');
    }
    function onMove(e) {
      apply(e.clientX, e.clientY);   // 同步直写：零延迟，后台标签页也不会乱序
    }
    logo.addEventListener('mouseenter', function (e) { apply(e.clientX, e.clientY); });
    logo.addEventListener('mousemove', onMove);
    logo.addEventListener('mouseleave', function () { lens.classList.remove('on'); });

    logo.addEventListener('click', function () { location.href = HOME; });
    logo.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); location.href = HOME; }
    });

    // 样式（亮色主题：深色镜片；暗色主题：浅暖白镜片；克隆一律反色）
    var css = document.createElement('style');
    css.textContent = [
      'header .logo.logo-home-link { position: relative; cursor: pointer; border-radius: 10px; }',
      'header .logo.logo-home-link:focus-visible { outline: 2px solid var(--blue, #5aa7e8); outline-offset: 2px; }',
      '.logo-lens { position: absolute; width: ' + D + 'px; height: ' + D + 'px; border-radius: 50%;',
      '  overflow: hidden; pointer-events: none; z-index: 70; display: block;',
      '  background: #2b2721; box-shadow: 0 8px 22px rgba(0,0,0,.30);',
      '  opacity: 0; transition: opacity .15s ease; will-change: left, top; }',
      '.logo-lens.on { opacity: 1; }',
      'html[data-theme="dark"] .logo-lens { background: #ece5d3; box-shadow: 0 8px 22px rgba(0,0,0,.5); }',
      '.logo-lens-clone { position: absolute; left: 0; top: 0;',
      '  filter: invert(1); white-space: nowrap; will-change: left, top; }',
      '.logo-lens-clone .dot { -webkit-user-drag: none; }'
    ].join('\n');
    document.head.appendChild(css);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
