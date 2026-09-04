/* ============================================================
 * bg-live.js —— 共享夜间动态背景引擎
 * WebGL2 液态金属流体（含鼠标 flowmap 交互）+ 漂浮星尘层。
 * 画布固定铺满视口（.fx，z-index:0），位于全部页面内容之下；
 * 浅色主题（data-theme="light"）下由 CSS 控制淡出。
 * 供 home / diagnose / review / speedtest / topology 共用。
 *
 * 使用前提：页面须包含 <canvas id="fluid" class="fx"></canvas>
 * 与 <canvas id="stage" class="fx"></canvas>。缺任一画布时本脚本自动跳过。
 * ============================================================ */
(function () {
  'use strict';

  var fluidEl = document.getElementById('fluid');
  var stageEl = document.getElementById('stage');
  if (!fluidEl || !stageEl) return;   // 无画布页面直接跳过，避免顶层报错

  /* 主题探测：home 白天模式也希望呈现“亮银液态金属”，
     其余页白天通常隐藏画布；此处按 data-theme 给两套金属调色板。 */
  function isLight() {
    return document.documentElement.getAttribute('data-theme') === 'light';
  }
  const PALETTES = {
    dark: {                      // 夜间：深灰金属
      glow: ['#e8ecef', '#9aa4ae', '#2c343c'],
      colors: ['#020304', '#101318', '#23282f', '#5a626c', '#a6aeb8'],
      glowIntensity: 0.13, lightCore: 0.1, lightHalo: 0.12, grain: 0.005,
      bloomThreshold: 0.61, bloomRange: 0.18, bloomStrength: 0.3,
      vignette: 0.45, starDark: false
    },
    light: {                     // 白天：柔和中灰银（非刺眼白，明暗可见鼠标扰动）
      glow: ['#ffffff', '#aab3bc', '#7c8791'],
      colors: ['#dfe4e9', '#c7cdd4', '#aab3bc', '#7c8791', '#4f5862'],
      glowIntensity: 0.06, lightCore: 0.07, lightHalo: 0.05, grain: 0.004,
      bloomThreshold: 0.68, bloomRange: 0.12, bloomStrength: 0.14,
      vignette: 0.08, starDark: true
    }
  };
  function palette() { return PALETTES[isLight() ? 'light' : 'dark']; }

  const WEBGL2_OK = (function () {
    try { return !!document.createElement('canvas').getContext('webgl2'); } catch (e) { return false; }
  })();
  // ---------- 1. 流体材质背景 ----------
  function initFluid() {
    const canvas = document.getElementById('fluid');
    let gl = null;
    // preserveDrawingBuffer: true —— html2canvas 截图需要读取 WebGL 画布像素；
    // 不开启时帧缓冲合成后被清空，截图里动态背景会变成灰色空块
    try { gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false, powerPreference: 'low-power', preserveDrawingBuffer: true }); } catch (e) {}
    if (!gl) return;

    // 运行参数；colors/glow 按主题切换，白天为亮银金属
    const CFG = {
      mouseRadius: 0.09, mouseStrength: 1.45, mouseSmoothing: 0.1, mouseVelocity: 0.18, decay: 0.925,
      distortBoost: 2.2, swirlBoost: 0.8,
      speed: 28, scale: 1.77, offsetX: -124, offsetY: -48
    };
    const rgb = function (h) {
      h = h.replace('#', '');
      return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255];
    };

    const VERT = '#version 300 es\n' +
      'in vec4 a_position;\nout vec2 vUv;\n' +
      'void main() { vUv = a_position.xy * 0.5 + 0.5; gl_Position = a_position; }';

    // flowmap 笔刷：R=鼠标存在感（高斯），GB=速度方向；每帧衰减形成拖尾
    const FRAG_BRUSH = '#version 300 es\n' +
      'precision mediump float;\nin vec2 vUv;\n' +
      'uniform sampler2D u_prev;\nuniform vec2 u_mouse;\nuniform vec2 u_velocity;\n' +
      'uniform float u_brushRadius;\nuniform float u_brushStrength;\nuniform float u_decay;\n' +
      'out vec4 fragColor;\n\n' +
      'void main() {\n' +
      '  vec4 prev = texture(u_prev, vUv);\n' +
      '  prev.r *= u_decay;\n' +
      '  prev.gb = mix(vec2(0.5), prev.gb, u_decay);\n' +
      '  float dist = distance(vUv, u_mouse);\n' +
      '  float influence = exp(-dist * dist / (u_brushRadius * u_brushRadius * 0.5));\n' +
      '  influence = max(0.0, influence - 0.01);\n' +
      '  float speed = length(u_velocity);\n' +
      '  float presenceStrength = u_brushStrength * 0.3;\n' +
      '  float velBonus = min(speed * 3.0, 0.7) * u_brushStrength;\n' +
      '  float totalStrength = presenceStrength + velBonus;\n' +
      '  prev.r = max(prev.r, influence * totalStrength);\n' +
      '  float blendAmt = influence * min(totalStrength, 0.4) * 0.3;\n' +
      '  prev.g = mix(prev.g, clamp(u_velocity.x * 2.0 + 0.5, 0.0, 1.0), blendAmt);\n' +
      '  prev.b = mix(prev.b, clamp(u_velocity.y * 2.0 + 0.5, 0.0, 1.0), blendAmt);\n' +
      '  fragColor = prev;\n' +
      '}';

    // 流体本体：simplex 噪声域扭曲 + flowmap 鼠标扰动/辉光 + 颗粒/bloom/光源/暗角
    const FRAG_FLUID = '#version 300 es\n' +
      'precision mediump float;\nin vec2 vUv;\n' +
      'uniform float u_time;\nuniform vec2 u_resolution;\n' +
      'uniform float u_scale;\nuniform vec2 u_offset;\nuniform float u_grain;\n' +
      'uniform sampler2D u_flowmap;\n' +
      'uniform float u_distortBoost;\nuniform float u_swirlBoost;\nuniform float u_glowIntensity;\n' +
      'uniform vec3 u_glowColor1;\nuniform vec3 u_glowColor2;\nuniform vec3 u_glowColor3;\n' +
      'uniform vec3 u_c1;\nuniform vec3 u_c2;\nuniform vec3 u_c3;\nuniform vec3 u_c4;\nuniform vec3 u_c5;\n' +
      'uniform vec2 u_lightPos;\n' +
      'uniform float u_lightCore;\nuniform float u_lightHalo;\nuniform float u_vignette;\n' +
      'uniform float u_bloomThreshold;\nuniform float u_bloomRange;\nuniform float u_bloomStrength;\n' +
      'out vec4 fragColor;\n\n' +
      'vec3 mod289v3(vec3 x){return x-floor(x*(1./289.))*289.;}\n' +
      'vec4 mod289v4(vec4 x){return x-floor(x*(1./289.))*289.;}\n' +
      'vec4 permute(vec4 x){return mod289v4(((x*34.)+1.)*x);}\n' +
      'vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}\n' +
      'float snoise(vec3 v){\n' +
      '  const vec2 C=vec2(1./6.,1./3.);\n  const vec4 D=vec4(0.,.5,1.,2.);\n' +
      '  vec3 i=floor(v+dot(v,C.yyy));\n  vec3 x0=v-i+dot(i,C.xxx);\n' +
      '  vec3 g=step(x0.yzx,x0.xyz);\n  vec3 l=1.-g;\n' +
      '  vec3 i1=min(g.xyz,l.zxy);\n  vec3 i2=max(g.xyz,l.zxy);\n' +
      '  vec3 x1=x0-i1+C.xxx;\n  vec3 x2=x0-i2+C.yyy;\n  vec3 x3=x0-D.yyy;\n' +
      '  i=mod289v3(i);\n' +
      '  vec4 p=permute(permute(permute(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));\n' +
      '  float n_=.142857142857;\n  vec3 ns=n_*D.wyz-D.xzx;\n' +
      '  vec4 j=p-49.*floor(p*ns.z*ns.z);\n' +
      '  vec4 x_=floor(j*ns.z);\n  vec4 y_=floor(j-7.*x_);\n' +
      '  vec4 x=x_*ns.x+ns.yyyy;\n  vec4 y=y_*ns.x+ns.yyyy;\n' +
      '  vec4 h=1.-abs(x)-abs(y);\n' +
      '  vec4 b0=vec4(x.xy,y.xy);\n  vec4 b1=vec4(x.zw,y.zw);\n' +
      '  vec4 s0=floor(b0)*2.+1.;\n  vec4 s1=floor(b1)*2.+1.;\n' +
      '  vec4 sh=-step(h,vec4(0.));\n' +
      '  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;\n  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;\n' +
      '  vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);\n' +
      '  vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);\n' +
      '  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));\n' +
      '  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;\n' +
      '  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);\n' +
      '  m=m*m;\n' +
      '  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));\n' +
      '}\n' +
      'float hash(vec2 p){\n' +
      '  vec3 p3=fract(vec3(p.xyx)*.1031);\n  p3+=dot(p3,p3.yzx+33.33);\n' +
      '  return fract((p3.x+p3.y)*p3.z);\n}\n' +
      'float fbm(vec3 p){\n' +
      '  float v=0.,amp=.6;vec3 shift=vec3(100.);\n' +
      '  for(int i=0;i<1;i++){v+=amp*snoise(p);p=p*2.+shift;amp*=.4;}\n  return v;\n}\n' +
      'float fluidNoise(vec2 uv,float t){\n' +
      '  float n1=fbm(vec3(uv*.6,t*.06));\n  float n2=fbm(vec3(uv*.6+5.2,t*.06+1.3));\n' +
      '  vec2 w1=vec2(n1,n2)*.6;\n' +
      '  float n3=fbm(vec3((uv+w1)*.7+1.7,t*.05+3.1));\n' +
      '  float n4=fbm(vec3((uv+w1)*.7+9.2,t*.05+5.7));\n' +
      '  vec2 w2=vec2(n3,n4)*.5;\n' +
      '  return fbm(vec3((uv+w1+w2)*.5,t*.04));\n}\n' +
      'vec2 curlish(vec2 uv,float t){\n' +
      '  float eps=.02;\n  float n=snoise(vec3(uv*.8,t));\n' +
      '  float nx=snoise(vec3((uv+vec2(eps,0.))*.8,t));\n' +
      '  float ny=snoise(vec3((uv+vec2(0.,eps))*.8,t));\n' +
      '  return vec2(-(ny-n)/eps,(nx-n)/eps)*.003;\n}\n\n' +
      'void main(){\n' +
      '  float aspect=u_resolution.x/u_resolution.y;\n' +
      '  vec2 uv=gl_FragCoord.xy/u_resolution;\n' +
      '  vec2 suv=vec2(uv.x*aspect, uv.y) * u_scale + u_offset;\n' +
      '  float t=u_time;\n\n' +
      '  vec4 flow = texture(u_flowmap, uv);\n' +
      '  float influence = flow.r;\n' +
      '  vec2 flowDir = (flow.gb - 0.5) * 2.0;\n\n' +
      '  suv += flowDir * influence * u_distortBoost * 0.8;\n' +
      '  float swirlAngle = influence * u_swirlBoost * 2.5;\n' +
      '  float cs = cos(swirlAngle), sn = sin(swirlAngle);\n' +
      '  vec2 delta = suv - vec2(uv.x * aspect, uv.y) * u_scale;\n' +
      '  suv += (mat2(cs, sn, -sn, cs) * delta - delta) * influence;\n\n' +
      '  vec2 curl=curlish(suv,t*.04);\n' +
      '  vec2 uvD=suv+curl*12.;\n' +
      '  float f=fluidNoise(uvD,t);\n' +
      '  float swirl=snoise(vec3(uvD*.8+f*1.5,t*.035))*.5+.5;\n' +
      '  float n=f*.5+.5;\n' +
      '  vec3 col=mix(u_c1,u_c2,smoothstep(.2,.5,n));\n' +
      '  col=mix(col,u_c3,smoothstep(.35,.65,n+swirl*.25));\n' +
      '  col=mix(col,u_c4,smoothstep(.6,.85,swirl)*.55);\n' +
      '  col=mix(col,u_c5,smoothstep(.5,.8,n*swirl)*.35);\n\n' +
      '  float glow = smoothstep(0.0, 0.8, influence);\n' +
      '  float glowNoise = snoise(vec3(uvD * 1.5, t * 0.08)) * 0.5 + 0.5;\n' +
      '  float glowDist = smoothstep(0.0, 1.0, influence);\n' +
      '  vec3 glowMix = mix(u_glowColor3, u_glowColor2, glowDist);\n' +
      '  glowMix = mix(glowMix, u_glowColor1, glowDist * glowNoise);\n' +
      '  col = mix(col, glowMix, glow * u_glowIntensity);\n\n' +
      '  if(u_grain>0.0){\n' +
      '    vec2 flowOffset = (uvD - suv) * u_resolution.y;\n' +
      '    vec2 gp = floor((gl_FragCoord.xy + flowOffset) / 5.0);\n' +
      '    float gr=hash(gp)*2.-1.;\n    col+=gr*u_grain;\n  }\n\n' +
      '  float luma=dot(col,vec3(.299,.587,.114));\n' +
      '  float bloom=smoothstep(u_bloomThreshold-u_bloomRange,u_bloomThreshold+u_bloomRange,luma);\n' +
      '  col+=(col*.85+vec3(.15,.145,.13))*bloom*u_bloomStrength;\n\n' +
      '  float ld=length((uv-u_lightPos)*vec2(aspect,1.));\n' +
      '  float core=exp(-ld*ld*4.5);\n  float halo=exp(-ld*1.8);\n' +
      '  col+=vec3(1.,.98,.94)*core*u_lightCore+vec3(.8,.84,.9)*halo*u_lightHalo;\n\n' +
      '  float vig=1.-smoothstep(.35,.75,length(uv-.5));\n' +
      '  col=mix(col*(1.-u_vignette),col,vig);\n' +
      '  fragColor=vec4(col,1.);\n' +
      '}';

    function shader(type, src) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.error('fluid shader:', gl.getShaderInfoLog(s));
        return null;
      }
      return s;
    }
    function program(fs) {
      const v = shader(gl.VERTEX_SHADER, VERT), f = shader(gl.FRAGMENT_SHADER, fs);
      if (!v || !f) return null;
      const p = gl.createProgram();
      gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
        console.error('fluid link:', gl.getProgramInfoLog(p));
        return null;
      }
      return p;
    }
    function uniforms(p) {
      const o = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < n; i++) {
        const info = gl.getActiveUniform(p, i);
        o[info.name] = gl.getUniformLocation(p, info.name);
      }
      return o;
    }
    const pBrush = program(FRAG_BRUSH), pFluid = program(FRAG_FLUID);
    if (!pBrush || !pFluid) return;
    const ub = uniforms(pBrush), uf = uniforms(pFluid);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    function bindQuad(p) {
      const a = gl.getAttribLocation(p, 'a_position');
      gl.bindBuffer(gl.ARRAY_BUFFER, quad);
      gl.enableVertexAttribArray(a);
      gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    }

    // 1/4 分辨率 flowmap 双缓冲（ping-pong）
    function makeTarget(w, h, data) {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, data || null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const fbo = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      return { fbo: fbo, tex: tex };
    }
    const dpr0 = Math.min(window.devicePixelRatio || 1, 1.5);
    const fw = Math.max(2, Math.round(canvas.clientWidth * dpr0 / 4));
    const fh = Math.max(2, Math.round(canvas.clientHeight * dpr0 / 4));
    const seed = new Uint8Array(fw * fh * 4);
    for (let i = 0; i < fw * fh; i++) { seed[i * 4] = 0; seed[i * 4 + 1] = 128; seed[i * 4 + 2] = 128; seed[i * 4 + 3] = 255; }
    let tA = makeTarget(fw, fh, seed), tB = makeTarget(fw, fh, seed), flip = false;

    const m = { x: 0.5, y: 0.5, sx: 0.5, sy: 0.5, svx: 0, svy: 0 };
    window.addEventListener('mousemove', function (e) {
      m.x = e.clientX / window.innerWidth;
      m.y = 1 - e.clientY / window.innerHeight;
    });

    let visible = true;
    new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(canvas);

    const t0 = performance.now();
    let last = 0, cw = 0, ch = 0;
    const STEP = 1000 / 30;

    // 首帧前同步定一次尺寸，避免 rAF 被节流时画布停留在默认大小
    cw = Math.round(canvas.clientWidth * Math.min(window.devicePixelRatio || 1, 1.5)) || 1;
    ch = Math.round(canvas.clientHeight * Math.min(window.devicePixelRatio || 1, 1.5)) || 1;
    canvas.width = cw;
    canvas.height = ch;

    function render(now) {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
      if (w !== cw || h !== ch) { cw = w; ch = h; canvas.width = w; canvas.height = h; }

      m.sx += (m.x - m.sx) * CFG.mouseSmoothing;
      m.sy += (m.y - m.sy) * CFG.mouseSmoothing;
      m.svx += ((m.x - m.sx) * 0.5 - m.svx) * CFG.mouseVelocity;
      m.svy += ((m.y - m.sy) * 0.5 - m.svy) * CFG.mouseVelocity;

      const src = flip ? tA : tB, dst = flip ? tB : tA;
      flip = !flip;

      // pass 1：更新 flowmap
      gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fbo);
      gl.viewport(0, 0, fw, fh);
      gl.useProgram(pBrush);
      bindQuad(pBrush);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, src.tex);
      gl.uniform1i(ub.u_prev, 0);
      gl.uniform2f(ub.u_mouse, m.sx, m.sy);
      gl.uniform2f(ub.u_velocity, m.svx, m.svy);
      gl.uniform1f(ub.u_brushRadius, CFG.mouseRadius);
      gl.uniform1f(ub.u_brushStrength, CFG.mouseStrength);
      gl.uniform1f(ub.u_decay, CFG.decay);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

      // pass 2：流体主渲染
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, w, h);
      gl.useProgram(pFluid);
      bindQuad(pFluid);
      gl.bindTexture(gl.TEXTURE_2D, dst.tex);
      gl.uniform1i(uf.u_flowmap, 0);
      gl.uniform1f(uf.u_time, (now - t0) * 0.001 * (CFG.speed / 100));
      gl.uniform2f(uf.u_resolution, w, h);
      gl.uniform1f(uf.u_scale, CFG.scale);
      gl.uniform2f(uf.u_offset, CFG.offsetX / 100, CFG.offsetY / 100);
      gl.uniform1f(uf.u_grain, palette().grain);
      gl.uniform1f(uf.u_distortBoost, CFG.distortBoost);
      gl.uniform1f(uf.u_swirlBoost, CFG.swirlBoost);
      gl.uniform1f(uf.u_glowIntensity, palette().glowIntensity);
      const g1 = rgb(palette().glow[0]), g2 = rgb(palette().glow[1]), g3 = rgb(palette().glow[2]);
      gl.uniform3f(uf.u_glowColor1, g1[0], g1[1], g1[2]);
      gl.uniform3f(uf.u_glowColor2, g2[0], g2[1], g2[2]);
      gl.uniform3f(uf.u_glowColor3, g3[0], g3[1], g3[2]);
      for (let i = 0; i < 5; i++) {
        const c = rgb(palette().colors[i] || palette().colors[palette().colors.length - 1]);
        gl.uniform3f(uf['u_c' + (i + 1)], c[0], c[1], c[2]);
      }
      gl.uniform2f(uf.u_lightPos, m.sx, m.sy);
      gl.uniform1f(uf.u_lightCore, palette().lightCore);
      gl.uniform1f(uf.u_lightHalo, palette().lightHalo);
      gl.uniform1f(uf.u_vignette, palette().vignette);
      gl.uniform1f(uf.u_bloomThreshold, palette().bloomThreshold);
      gl.uniform1f(uf.u_bloomRange, palette().bloomRange);
      gl.uniform1f(uf.u_bloomStrength, palette().bloomStrength);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    function frame(now) {
      requestAnimationFrame(frame);
      if (!visible || now - last < STEP) return;
      last = now - (now - last) % STEP;
      render(now);
    }
    requestAnimationFrame(frame);
    render(performance.now()); // 首帧同步出图，rAF 被节流时也有首屏画面
  }

  if (WEBGL2_OK) {
    initFluid();
  }


  /* ---------- 星尘层（移植自登录页 2D 粒子引擎，仅保留漂浮尘埃） ---------- */
  var canvas = document.getElementById('stage');
  var ctx = canvas.getContext('2d');
  var W = 0, H = 0, DPR = 1;
  var dust = [];
  function themeLight() { return document.documentElement.getAttribute('data-theme') === 'light'; }

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }

  function initDust() {
    dust.length = 0;
    var n = Math.round(W * H / 16000);
    for (var i = 0; i < n; i++) {
      dust.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.06, vy: -0.02 - Math.random() * 0.08,
        s: Math.random() < 0.8 ? 1 : 1.6, a: 0.12 + Math.random() * 0.3,
        tw: Math.random() * Math.PI * 2, ts: 0.5 + Math.random() * 1.5,
        c: Math.random() < 0.7 ? 'rgba(255,255,255,0.9)' : 'rgba(150,205,255,0.9)'
      });
    }
  }

  function step() {
    for (var i = 0; i < dust.length; i++) {
      var d = dust[i];
      d.x += d.vx; d.y += d.vy;
      if (d.y < -4) { d.y = H + 4; d.x = Math.random() * W; }
      if (d.x < -4) d.x = W + 4; else if (d.x > W + 4) d.x = -4;
    }
  }

  function render(t) {
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < dust.length; i++) {
      var d = dust[i];
      var tw = 0.5 + 0.5 * Math.sin(t * 0.001 * d.ts + d.tw);
      ctx.globalAlpha = Math.min(1, d.a * (0.5 + 0.85 * tw));
      ctx.fillStyle = d.c;
      ctx.fillRect(d.x, d.y, d.s, d.s);
    }
    ctx.globalAlpha = 1;
  }

  function loop(t) {
    requestAnimationFrame(loop);
    if (themeLight()) return;
    step();
    render(t);
  }

  resize();
  initDust();
  requestAnimationFrame(loop);

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { resize(); initDust(); }, 200);
  });
})();
