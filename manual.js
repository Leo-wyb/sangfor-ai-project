/* CyberNWT · 使用手册 —— 居中手册式图文介绍
 *
 * 形态：居中圆角大面板（约 50vw × 63vh）+ 左侧多级目录 + 右侧图文 / 视频展示。
 * - 封面：第一页为欢迎封面，「下一步」进入第一章；
 * - 目录：六个功能章节，各用一种主题色；灵犀测速 / 内网感知为「大点」，下设小节（小点）：
 *   点击父点进入该章概览并在目录展开小点，点父点右侧箭头仅展开 / 折叠；点小点直达小节页；
 *   翻页（下一步 / ← →）进入含小节的章节时，左侧目录自动展开该章小点（手风琴）；
 * - 展示：含小节的章节概览页 = 左侧章节文案 + 右侧「本章小节」导航卡（替代原配图，点击直达小节）；
 *   小节页 = 左侧讲解要点 + 右侧真人演示视频；其余章节保持原图文排版；
 * - 交互：上一步/下一步、进度条、键盘 ←/→ 切页、Esc 关闭；
 * - 进度记忆：翻页自动保存，重开停留在上次位置；
 * - 接入：引入本文件（defer），页脚/顶栏放 <a data-cm-open> 或 <a id="cg-replay">，
 *   调用 CyberManual.open() 打开。
 */
(function () {
  'use strict';

  /* ---------- 章节数据 ----------
   * subs 非空的章节为「大点」：概览页右侧改为小节导航卡，每个小节独立成页（右侧为演示视频）。
   * 小节字段：name 名称 / brief 一句话简介（概览导航卡用）/ tagline 副题 / desc 讲解 /
   *          points 要点列表 / video 演示视频 / poster 视频海报。 */
  var CHAPTERS = [
    {
      no: '01', name: '灵犀测速', color: '#58a6ff',
      tagline: 'AI 驱动的网络体检',
      desc: '公网 / 内网双模式一键测速：自动定位就近节点多源并发，自动识别内网多网卡自由选择，实测上下行带宽、延迟与抖动；支持历史溯源对比与持续测速出报告，测完灵犀直接解读瓶颈与建议，不只是测速，更能用于排障！',
      chips: ['多节点测速', 'AI 指标解读', '历史回溯', '持续测速出报告'],
      subs: [
        {
          name: '公网测速',
          brief: '就近节点多源并发，实测真实上下行带宽',
          tagline: '就近节点 · 多源并发，实测真实带宽',
          desc: '点「开始测速」即自动锁定就近节点、多源并发，实测上下行带宽与延迟、抖动；测完逐跳查看链路，瓶颈段标红，慢在哪一段一目了然。',
          points: [
            '自动定位就近节点，多源并发',
            '延迟 / 抖动 / 上下行 / 丢包同屏',
            '逐跳还原线路，瓶颈段标红',
            '灵犀 AI 解读，给出排障建议'
          ],
          video: 'docs/videos/speedtest-wan.mp4',
          poster: 'docs/videos/posters/speedtest-wan.jpg'
        },
        {
          name: '内网测速',
          brief: '多网卡自由选路，内网链路质量一测便知',
          tagline: '多网卡自由选路，摸清内网真实质量',
          desc: '切到「内网测速」：自动识别多张网卡、自由选择线路；对端留空即测网关延迟，填内网 IP 可互测上下行，快速判断瓶颈在内网还是出口。',
          points: [
            '自动识别多网卡，自由选路',
            '留空测网关，填 IP 互测带宽',
            '定位内网 / 出口链路瓶颈',
            '历史自动保存，悬停对比'
          ],
          video: 'docs/videos/speedtest-lan.mp4',
          poster: 'docs/videos/posters/speedtest-lan.jpg'
        },
        {
          name: '持续测速',
          brief: '循环实测自动汇总，长时间观测不盯屏',
          tagline: '指定停止条件，循环实测自动出报告',
          desc: '设好停止条件（时间 / 轮数）点开始：独立小窗口运行，关页面也不断测；到点自动汇总全部轮次，一键导出 Word 报告，波动卡顿有据可查。',
          points: [
            '独立小窗口，关页面不断测',
            '到点自动汇总全部轮次',
            '一键导出 Word 测速报告',
            '长时观测不盯屏更省心'
          ],
          video: 'docs/videos/speedtest-loop.mp4',
          poster: 'docs/videos/posters/speedtest-loop.jpg'
        }
      ]
    },
    {
      no: '02', name: '内网感知', color: '#3ecf8e',
      tagline: '内网拓扑，一眼可辨',
      desc: '接入网络后真实 ping 扫描网段与在线设备，谁在线、谁掉线一眼可辨；节点持续感知、异常立即高亮，链路健康度同步可视，并给出深信服设备部署建议；支持导入已有拓扑或自由创建，结果支持导出。',
      chips: ['拓扑自动发现', '状态实时感知', '异常节点标注', '链路健康可视'],
      subs: [
        {
          name: '开始感知',
          brief: '接入内网一键扫描，实测拓扑自动生成',
          tagline: '接入即扫，实测拓扑自动生成',
          desc: '接入客户内网（网线 / Wi-Fi 均可），点「开始感知」一键扫描：真实 ping + ARP + 端口指纹自动绘出拓扑，打印机自动标记，并同步给出部署建议。',
          points: [
            '网线 / Wi-Fi 均可接入',
            '真实 ping+ARP+端口指纹',
            '终端 / 打印机自动标记',
            '多网段扫描 + SNMP 链路'
          ],
          video: 'docs/videos/topo-scan.mp4',
          poster: 'docs/videos/posters/topo-scan.jpg'
        },
        {
          name: '导入已有拓扑',
          brief: '图片描点 / .topo 文件，旧图秒变活图',
          tagline: '图片描点 · .topo 转换，旧图变活图',
          desc: '点「已有拓扑」导入：图片可作底图描点建模，.topo 文件自动转换且不改原文件；画完点「保存并导出」为 JSON / PNG / .topo，随时还原、持续维护。',
          points: [
            '图片底图描点或自动建模',
            '.topo 自动转换',
            '导出 JSON / PNG / .topo',
            '导入后可继续感知编辑'
          ],
          video: 'docs/videos/topo-import.mp4',
          poster: 'docs/videos/posters/topo-import.jpg'
        },
        {
          name: '自由创建',
          brief: '设备点选即上图，网络结构随心绘制',
          tagline: '从零搭建，网络结构随心绘制',
          desc: '点「添加设备」展开工具栏，八类设备点选即上图；连线只需点两个节点，框选、拖拽随意调整，「树状排布」一键对齐，「保存并导出」即可交付。',
          points: [
            '八类设备点选即上图',
            '连线 / 框选 / 拖拽布局',
            '树状排布一键对齐',
            '保存导出即可交付'
          ],
          video: 'docs/videos/topo-create.mp4',
          poster: 'docs/videos/posters/topo-create.jpg'
        }
      ]
    },
    {
      no: '03', name: '随心记录', color: '#ffa94d',
      tagline: '随手画、随手记的悬浮白板',
      desc: '任意页面点右下角悬浮球即可开画：画笔、橡皮、文字一应俱全，页面截图框选即插即用；右键直接剪切、复制、粘贴，内容自动保存本机，支持导出，解决工程师记录时总是需要来回切换跳转记录工具，随时展开随时悬浮，打开即可用，让记录和标记更顺心更自由！',
      chips: ['自由手绘', '截图插入', '右键编辑', '自动保存'],
      video: 'docs/videos/whiteboard.mp4',
      poster: 'docs/videos/posters/whiteboard.jpg'
    },
    {
      no: '04', name: '故障诊断助手', color: '#ff7b92',
      tagline: '把现象讲给 AI 听',
      desc: '用自然语言描述故障现象，支持上传图片、视频和文档进行分析，灵犀对接 FastGPT，结合深信服故障诊断知识库给出排查思路与处置建议，思考过程简洁可视，并且以表格的形式展现，精简易读，支持多轮追问，不用多开会话，为排障提高效率，让排障变得轻松！',
      chips: ['现象化诊断', '排查步骤生成', '双知识库', '多轮追问'],
      video: 'docs/videos/diagnose.mp4',
      poster: 'docs/videos/posters/diagnose.jpg'
    },
    {
      no: '05', name: '案例复盘', color: '#a78bfa',
      tagline: '项目经验，沉淀成册',
      desc: '把项目过程讲给灵犀，自动沉淀为结构化复盘报告：时间线、根因分析、可复用方法论一并成文，支持直接在线编辑，支持插入图片，一键导出 Word / PDF 即可归档汇报。好的经验不再散落，团队踩过的坑从此变成可复用的资产，让学习和复盘更加轻松！',
      chips: ['AI 生成报告', '结构化复盘', '一键导出', '经验可复用'],
      video: 'docs/videos/review.mp4',
      poster: 'docs/videos/posters/review.jpg'
    },
    {
      no: '06', name: '设计巧思', color: '#2dd4bf',
      tagline: '细节里的一致性',
      desc: '<b style="color:var(--c);font-size:14px">测得快·看得清·随手记·查得准·留得下</b><br>把一次交付现场变成可复用的经验，把每次 AI 结论变成可复核的证据。<span style="display:block;margin-top:12px">人无完人，金无足赤，我会继续把产品优化、更新迭代，正如 AI 赛道所说：<span style="color:#3d8f8a">AI 赋能从来都不是开发者的专利，而是我们每个普通人都能用上的工具！</span>感谢深信服，感谢大家。</span>',
      chips: ['深浅色自适应', '玻璃拟态 UI', '零依赖纯前端', '数据本地化'],
      cards: [
        { icon: 'bolt', t: '零门槛，才是真落地', d: '无需安装、解压即用，客户内网没有外网也能完整工作；2.4 秒冷启动，随时开工。' },
        { icon: 'grid', t: '不重复造轮子', d: '顶栏直达深信服社区与 PRM 系统，在 Web 界面就能完成全程工程实施，遇事有处可问。' },
        { icon: 'chat', t: '让经验得到记忆', d: '复盘回流知识库，老师傅的经验沉淀成组织资产——人会流动，经验留了下来。' }
      ]
    }
  ];

  /* ---------- 小图标 ---------- */
  var CARET_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
  /* 设计巧思章节卡片小图标（仅该章节使用） */
  var CARD_ICONS = {
    bolt: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 2 4.5 13.5H11L9.5 22 19 10h-6.5L13 2z"/></svg>',
    grid: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="8" cy="8" r="2.7"/><circle cx="16.2" cy="8" r="2.7"/><circle cx="8" cy="16.2" r="2.7"/><circle cx="16.2" cy="16.2" r="2.7"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
  };
  var PLAY_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>';
  var SOUND_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';

  /* ---------- 样式 ---------- */
  var CSS = [
    '.cm-root{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;',
    '  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;}',
    '.cm-root[hidden]{display:none;}',

    '.cm-mask{position:absolute;inset:0;background:rgba(4,8,14,.55);',
    '  backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);animation:cm-fade .3s both;}',
    '@keyframes cm-fade{from{opacity:0}to{opacity:1}}',

    /* 手册面板：居中圆角，约 50vw × 63vh；底色接近不透明，保证文字清晰 */
    '.cm-panel{position:relative;width:min(50vw,1060px);min-width:660px;height:min(63vh,700px);min-height:470px;',
    '  display:flex;border-radius:22px;overflow:hidden;color:var(--text,#EDEDED);',
    '  background:rgba(17,23,32,.97);',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.2));',
    '  box-shadow:0 30px 90px rgba(0,0,0,.55);',
    '  animation:cm-pop .4s cubic-bezier(.22,1,.36,1) both;}',
    '[data-theme="light"] .cm-panel{background:rgba(250,252,255,.98);}',
    '@keyframes cm-pop{from{opacity:0;transform:translateY(20px) scale(.94);}to{opacity:1;transform:none;}}',

    /* 左侧目录：封面 + 六色章节（大点可展开小点，超高时目录区内部滚动） */
    '.cm-rail{width:184px;flex:none;display:flex;flex-direction:column;gap:4px;padding:24px 14px 16px;',
    '  overflow-y:auto;scrollbar-width:none;',
    '  background:color-mix(in srgb,var(--accent-bg,rgba(126,190,244,.08)) 55%,transparent);',
    '  border-right:1px solid var(--panel-border,rgba(205,214,224,.18));}',
    '.cm-rail::-webkit-scrollbar{display:none;}',
    '.cm-brand{display:flex;align-items:center;gap:8px;padding:0 10px 14px;}',
    '.cm-brand b{font-size:13.5px;letter-spacing:1px;}',
    '.cm-tab{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;',
    '  border:1px solid transparent;background:transparent;cursor:pointer;font-family:inherit;',
    '  font-size:13px;color:var(--text-2,#9CA3AF);text-align:left;transition:all .22s;flex:none;}',
    '.cm-tab .cm-dotc{width:9px;height:9px;border-radius:50%;background:var(--c);flex:none;',
    '  box-shadow:0 0 8px color-mix(in srgb,var(--c) 70%,transparent);transition:transform .22s;}',
    '.cm-tab .cm-no{margin-left:auto;font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:10.5px;color:var(--text-2,#9CA3AF);opacity:.7;}',
    '.cm-tab:hover{color:var(--text,#EDEDED);transform:translateX(2px);',
    '  background:var(--accent-bg,rgba(126,190,244,.1));}',
    '.cm-tab.on{color:var(--text,#EDEDED);font-weight:600;',
    '  background:color-mix(in srgb,var(--c) 14%,transparent);',
    '  border-color:color-mix(in srgb,var(--c) 45%,transparent);}',
    '.cm-tab.on .cm-dotc{transform:scale(1.3);}',

    /* 大点展开箭头：折叠时朝右，展开时朝下；点箭头仅展开 / 折叠，不跳转 */
    '.cm-tab .cm-caret{flex:none;width:14px;height:14px;margin-left:2px;display:flex;align-items:center;justify-content:center;',
    '  opacity:.65;transform:rotate(-90deg);transition:transform .28s cubic-bezier(.22,1,.36,1),opacity .2s;}',
    '.cm-tab .cm-caret:hover{opacity:1;}',
    '.cm-tab .cm-caret svg{width:9px;height:9px;}',
    '.cm-tab.exp .cm-caret{transform:rotate(0);}',

    /* 小点子页列表：随所在章节展开 / 收起（grid 行高动画，不限高度，任何缩放下都完整显示） */
    '.cm-subs{display:grid;grid-template-rows:0fr;opacity:0;',
    '  transition:grid-template-rows .32s cubic-bezier(.22,1,.36,1),opacity .3s ease;}',
    '.cm-subs.open{grid-template-rows:1fr;opacity:1;}',
    '.cm-subs-in{overflow:hidden;min-height:0;}',
    '.cm-sub{display:flex;align-items:center;gap:8px;margin:2px 0 2px 22px;padding:6px 10px;',
    '  border-radius:8px;font-size:12px;color:var(--text-2,#9CA3AF);cursor:pointer;',
    '  font-family:inherit;text-align:left;background:transparent;border:none;transition:all .2s;width:calc(100% - 22px);}',
    '.cm-sub .sdot{width:5px;height:5px;border-radius:50%;background:var(--c);opacity:.55;flex:none;transition:all .2s;}',
    '.cm-sub:hover{color:var(--text,#EDEDED);background:var(--accent-bg,rgba(126,190,244,.1));}',
    '.cm-sub.on{color:var(--text,#EDEDED);font-weight:600;',
    '  background:color-mix(in srgb,var(--c) 13%,transparent);}',
    '.cm-sub.on .sdot{opacity:1;box-shadow:0 0 6px color-mix(in srgb,var(--c) 60%,transparent);}',
    '.cm-rail .cm-tip{margin-top:auto;padding:10px 10px 0;font-size:10.5px;line-height:1.8;',
    '  color:var(--text-2,#9CA3AF);border-top:1px dashed var(--panel-border,rgba(205,214,224,.18));}',

    /* 右侧内容区 */
    '.cm-main{flex:1;position:relative;display:flex;flex-direction:column;padding:28px 36px 20px;min-width:0;}',
    '.cm-close{position:absolute;top:14px;right:16px;width:32px;height:32px;border-radius:9px;',
    '  border:1px solid var(--border,rgba(205,214,224,.35));',
    '  background:var(--accent-bg,rgba(126,190,244,.16));color:var(--text,#EDEDED);font-size:15px;cursor:pointer;',
    '  line-height:1;font-family:inherit;transition:all .2s;z-index:3;}',
    '.cm-close:hover{border-color:var(--accent-border,rgba(255,255,255,.45));transform:scale(1.06);color:#fff;}',
    '.cm-ghost{position:absolute;right:26px;bottom:-14px;font-size:128px;font-weight:800;line-height:1;',
    '  font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);pointer-events:none;user-select:none;',
    '  color:color-mix(in srgb,var(--c) 13%,transparent);z-index:0;}',
    '.cm-page{flex:1;display:flex;gap:30px;align-items:flex-start;min-height:0;position:relative;z-index:1;}',
    '.cm-txt{flex:1.05;min-width:0;max-height:100%;overflow-y:auto;padding-bottom:14px;}',
    '.cm-txt::-webkit-scrollbar{width:4px;}',
    '.cm-txt::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--text,#EDEDED) 25%,transparent);border-radius:2px;}',
    '.cm-txt::-webkit-scrollbar-track{background:transparent;}',
    '.cm-pic{flex:1;align-self:stretch;display:flex;align-items:center;justify-content:center;min-width:0;}',
    '.cm-pic img{max-width:100%;max-height:100%;border-radius:14px;',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.2));',
    '  box-shadow:0 18px 46px rgba(0,0,0,.4);object-fit:contain;background:rgba(127,127,127,.06);}',

    '.cm-chipbar{display:inline-flex;align-items:center;gap:9px;font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:11px;font-weight:600;letter-spacing:2.5px;color:var(--c);}',
    '.cm-chipbar .bar{width:26px;height:2px;border-radius:1px;background:var(--c);}',
    '.cm-chipbar .cm-crumb{white-space:nowrap;}',
    '.cm-title{font-size:27px;font-weight:700;margin:12px 0 2px;}',
    '.cm-tagline{display:flex;align-items:center;gap:10px;font-size:13.5px;font-weight:600;letter-spacing:1px;color:var(--c);margin-bottom:14px;}',
    '.cm-desc{font-size:13.5px;line-height:2.3;color:var(--text-2,#9CA3AF);margin:0 0 10px;}',
    '.cm-desc b{color:var(--c);font-weight:700;}',
    '.cm-chips{display:grid;grid-template-columns:repeat(2,minmax(0,max-content));',
    '  gap:10px 12px;justify-content:start;}',
    '.cm-chip{font-size:11.5px;padding:5px 12px;border-radius:999px;color:var(--text,#EDEDED);',
    '  background:color-mix(in srgb,var(--c) 12%,transparent);',
    '  border:1px solid color-mix(in srgb,var(--c) 40%,transparent);}',

    /* 章节概览（带小点的章节）：右侧「本章小节」导航卡，替代原配图，点击直达小节页 */
    '.cm-subcards{flex:1;align-self:stretch;display:flex;flex-direction:column;justify-content:center;gap:11px;',
    '  min-width:0;position:relative;z-index:1;}',
    '.cm-subcards-head{display:flex;align-items:center;gap:9px;font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:11px;font-weight:600;letter-spacing:2.5px;color:var(--c);white-space:nowrap;}',
    '.cm-subcards-head .bar{width:26px;height:2px;border-radius:1px;background:var(--c);flex:none;}',
    '.cm-subcards-head em{font-style:normal;margin-left:auto;font-size:10px;letter-spacing:1.5px;opacity:.75;',
    '  white-space:nowrap;flex:none;overflow:hidden;text-overflow:ellipsis;max-width:60%;}',
    '.cm-subcard{display:flex;align-items:center;gap:14px;padding:13px 16px;border-radius:13px;cursor:pointer;',
    '  text-align:left;font-family:inherit;color:var(--text,#EDEDED);position:relative;z-index:1;',
    '  background:color-mix(in srgb,var(--c) 6%,transparent);',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.2));transition:all .22s;}',
    '.cm-subcard:hover{transform:translateY(-2px);background:color-mix(in srgb,var(--c) 11%,transparent);',
    '  border-color:color-mix(in srgb,var(--c) 48%,transparent);box-shadow:0 10px 26px rgba(0,0,0,.28);}',
    '.cm-subcard .n{flex:none;width:32px;font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:19px;font-weight:800;color:var(--c);}',
    '.cm-subcard .b{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px;}',
    '.cm-subcard .t{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
    '.cm-subcard .d{font-style:normal;font-size:11.5px;line-height:1.5;color:var(--text-2,#9CA3AF);',
    '  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}',
    '.cm-subcard .go{flex:none;width:27px;height:27px;border-radius:50%;display:flex;align-items:center;justify-content:center;',
    '  color:var(--c);border:1px solid color-mix(in srgb,var(--c) 42%,transparent);transition:all .22s;}',
    '.cm-subcard .go svg{width:11px;height:11px;margin-left:1px;}',
    '.cm-subcard:hover .go{background:var(--c);color:#fff;transform:scale(1.06);}',

    /* 设计巧思章节右侧：三张要点卡 + 口号条（仅该章节使用） */
    '.cm-cards{flex:1;align-self:stretch;display:flex;flex-direction:column;justify-content:space-evenly;gap:10px;',
    '  min-width:0;position:relative;z-index:1;padding-top:34px;}',
    '.cm-card{display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:12px;',
    '  background:color-mix(in srgb,var(--c) 6%,transparent);',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.2));}',
    '.cm-card-ic{flex:none;width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;',
    '  color:#fff;background:var(--c);box-shadow:0 4px 12px color-mix(in srgb,var(--c) 40%,transparent);}',
    '.cm-card-ic svg{width:13px;height:13px;}',
    '.cm-card-b{flex:1;min-width:0;}',
    '.cm-card-t{display:block;font-size:12px;font-weight:700;margin-bottom:2px;}',
    '.cm-card-d{display:block;font-size:10.5px;line-height:1.65;color:var(--text-2,#9CA3AF);}',
    '.cm-page.cm-in .cm-cards > *{animation:cm-soft .6s cubic-bezier(.33,1,.68,1) both;}',
    '.cm-page.cm-in .cm-cards > *:nth-child(2){animation-delay:.1s;}',
    '.cm-page.cm-in .cm-cards > *:nth-child(3){animation-delay:.2s;}',
    '.cm-page.cm-in .cm-cards > *:nth-child(4){animation-delay:.3s;}',

    /* 小点子页：左讲解要点 + 右演示视频 */
    '.cm-secbadge{margin-left:auto;flex:none;padding:2px 7px;border-radius:4px;font-size:9.5px;letter-spacing:1.5px;',
    '  color:var(--c);border:1px solid color-mix(in srgb,var(--c) 40%,transparent);opacity:.9;}',
    '.cm-points{list-style:none;margin:4px 0 0;padding:0;display:flex;flex-direction:column;gap:8px;}',
    '.cm-points li{position:relative;padding-left:18px;font-size:12.8px;line-height:1.7;color:var(--text-2,#9CA3AF);}',
    '.cm-points li::before{content:"";position:absolute;left:2px;top:.6em;width:7px;height:7px;border-radius:2px;',
    '  background:var(--c);opacity:.9;box-shadow:0 0 7px color-mix(in srgb,var(--c) 65%,transparent);}',
    '.cm-video{flex:1;align-self:stretch;display:flex;flex-direction:column;justify-content:center;gap:10px;',
    '  min-width:0;max-height:100%;position:relative;z-index:1;}',
    '.cm-video-head{display:flex;align-items:center;gap:9px;min-width:0;font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);',
    '  font-size:10.5px;font-weight:600;letter-spacing:2px;color:var(--c);}',
    '.cm-video-head .bar{width:26px;height:2px;border-radius:1px;background:var(--c);flex:none;}',
    '.cm-video-head .vt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
    '.cm-player{position:relative;width:100%;aspect-ratio:16/10;border-radius:14px;overflow:hidden;',
    '  border:1px solid var(--panel-border,rgba(205,214,224,.2));',
    '  box-shadow:0 18px 46px rgba(0,0,0,.4);background:#0d1013;}',
    '.cm-player video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;}',
    '.cm-video-tip{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--text-2,#9CA3AF);}',
    '.cm-video-tip svg{width:12px;height:12px;color:var(--c);flex:none;}',

    /* 底部：进度条 + 翻页 */
    '.cm-foot{display:flex;align-items:center;gap:14px;margin-top:16px;position:relative;z-index:1;}',
    '.cm-count{font-family:var(--font-mono,SFMono-Regular,Consolas,monospace);font-size:11px;',
    '  color:var(--text-2,#9CA3AF);letter-spacing:1px;}',
    '.cm-prog{flex:1;height:3px;border-radius:2px;overflow:hidden;',
    '  background:var(--prog-track,rgba(255,255,255,.15));}',
    '.cm-prog i{display:block;height:100%;border-radius:2px;background:var(--c);transition:width .4s ease;}',
    '.cm-btn{height:32px;padding:0 16px;border-radius:8px;font-size:12.5px;cursor:pointer;line-height:1;',
    '  font-family:inherit;margin-left:8px;transition:all .2s;}',
    '.cm-prev{background:var(--accent-bg,rgba(126,190,244,.14));',
    '  border:1px solid var(--border,rgba(205,214,224,.4));color:var(--text,#EDEDED);font-weight:600;}',
    '.cm-prev:hover:not(:disabled){border-color:var(--accent-border,rgba(255,255,255,.45));}',
    '.cm-prev:disabled{opacity:.35;cursor:default;}',
    '.cm-next{border:1px solid var(--c);background:var(--c);color:#fff;font-weight:700;letter-spacing:1px;',
    '  box-shadow:0 6px 20px color-mix(in srgb,var(--c) 45%,transparent);}',
    '.cm-next:hover:not(:disabled){filter:brightness(1.08);transform:translateY(-1px);}',
    '.cm-next:disabled{opacity:.35;cursor:default;box-shadow:none;}',

    /* 欢迎封面页（第一页）：全部内容作为一个整体居中展示 */
    '.cm-welcome{flex:1;align-self:stretch;display:flex;flex-direction:column;align-items:center;min-height:0;',
    '  text-align:center;position:relative;z-index:1;}',
    '.cm-wl-body{flex:1;width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;}',
    '.cm-wl-title{font-size:32px;font-weight:700;margin:0 0 18px;color:var(--text,#EDEDED);}',
    '.cm-wl-sub{font-size:16px;letter-spacing:2.5px;color:var(--text-2,#9CA3AF);margin-bottom:24px;}',
    '.cm-wl-div{width:56px;height:2px;border-radius:1px;margin:0 auto 24px;',
    '  background:linear-gradient(90deg,#58a6ff,#3ecf8e);}',
    '.cm-wl-line{font-size:14.5px;line-height:2.1;color:var(--text,#EDEDED);margin:0;}',
    '.cm-wl-line b{font-weight:700;font-size:17px;}',
    '.cm-wl-sound{display:inline-flex;align-items:center;gap:9px;margin:22px 0 22px;padding:9px 18px;',
    '  border-radius:999px;font-size:13px;color:var(--text,#EDEDED);',
    '  background:color-mix(in srgb,#f5a623 13%,transparent);',
    '  border:1px solid color-mix(in srgb,#f5a623 40%,transparent);}',
    '.cm-wl-sound svg{width:15px;height:15px;color:#f5a623;flex:none;}',
    '.cm-wl-doc{font-size:12.5px;color:var(--text-2,#9CA3AF);position:relative;top:12px;}',
    '.cm-wl-doc a{color:var(--c,#58a6ff);text-decoration:underline dotted;',
    '  text-underline-offset:3px;transition:opacity .2s;}',
    '.cm-wl-doc a:hover{opacity:.75;}',

    /* 入场动画：各行柔浮上浮 */
    '.cm-page.cm-in .cm-wl-body > *{animation:cm-soft .72s cubic-bezier(.33,1,.68,1) both;}',
    '.cm-page.cm-in .cm-wl-body > *:nth-child(2){animation-delay:.14s;}',
    '.cm-page.cm-in .cm-wl-body > *:nth-child(3){animation-delay:.28s;}',
    '.cm-page.cm-in .cm-wl-body > *:nth-child(4){animation-delay:.42s;}',
    '.cm-page.cm-in .cm-wl-body > *:nth-child(5){animation-delay:.56s;}',
    '.cm-page.cm-in .cm-wl-body > *:nth-child(6){animation-delay:.7s;}',
    '@keyframes cm-soft{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:none;}}',
    '.cm-page.cm-in .cm-txt > *{animation:cm-soft .6s cubic-bezier(.33,1,.68,1) both;}',
    '.cm-page.cm-in .cm-txt > *:nth-child(2){animation-delay:.08s;}',
    '.cm-page.cm-in .cm-txt > *:nth-child(3){animation-delay:.16s;}',
    '.cm-page.cm-in .cm-txt > *:nth-child(4){animation-delay:.24s;}',
    '.cm-page.cm-in .cm-txt > *:nth-child(5){animation-delay:.32s;}',
    '.cm-page.cm-in .cm-pic img{animation:cm-soft .65s cubic-bezier(.33,1,.68,1) .15s both;}',
    '.cm-page.cm-in .cm-subcards > *{animation:cm-soft .6s cubic-bezier(.33,1,.68,1) both;}',
    '.cm-page.cm-in .cm-subcards > *:nth-child(2){animation-delay:.1s;}',
    '.cm-page.cm-in .cm-subcards > *:nth-child(3){animation-delay:.2s;}',
    '.cm-page.cm-in .cm-subcards > *:nth-child(4){animation-delay:.3s;}',
    '.cm-page.cm-in .cm-video > *{animation:cm-soft .6s cubic-bezier(.33,1,.68,1) both;}',
    '.cm-page.cm-in .cm-video > *:nth-child(2){animation-delay:.1s;}',
    '.cm-page.cm-in .cm-video > *:nth-child(3){animation-delay:.18s;}',

    /* 矮窗口自动收紧排版：内容始终一屏放下，无需滚动 */
    '@media (max-height:820px){',
    '  .cm-main{padding:20px 32px 12px;}',
    '  .cm-title{font-size:23px;margin:8px 0 2px;}',
    '  .cm-tagline{font-size:12.5px;margin-bottom:8px;}',
    '  .cm-desc{font-size:13px;line-height:1.95;margin:0 0 10px;}',
    '  .cm-chips{gap:8px 10px;}',
    '  .cm-chip{font-size:11px;padding:4px 10px;}',
    '  .cm-foot{margin-top:10px;}',
    '  .cm-subcard{padding:10px 14px;gap:11px;}',
    '  .cm-subcard .n{font-size:17px;}',
    '  .cm-points{gap:5px;margin-top:2px;}',
    '  .cm-points li{font-size:12px;line-height:1.7;}',
    '}',
    '@media (max-height:660px){',
    '  .cm-main{padding:14px 24px 8px;}',
    '  .cm-wl-title{font-size:24px;}',
    '  .cm-title{font-size:20px;}',
    '  .cm-tagline{font-size:12px;margin-bottom:8px;}',
    '  .cm-desc{font-size:12px;line-height:1.8;margin:0 0 8px;}',
    '  .cm-chip{font-size:10.5px;padding:4px 9px;}',
    '  .cm-foot{margin-top:8px;}',
    '  .cm-points{gap:4px;}',
    '  .cm-points li{font-size:11.5px;line-height:1.55;}',
    '  .cm-video{gap:7px;}',
    '}',

    /* 较窄视口：小节徽标让位给正文 */
    '@media (max-width:1500px){',
    '  .cm-secbadge{display:none;}',
    '}',

    /* 窄屏兜底：目录横排、图文竖排 */
    '@media (max-width:960px){',
    '  .cm-panel{flex-direction:column;width:92vw;height:auto;max-height:88vh;min-width:0;min-height:0;}',
    '  .cm-rail{width:auto;flex-direction:row;align-items:center;overflow-x:auto;gap:6px;padding:12px;}',
    '  .cm-rail .cm-brand,.cm-rail .cm-tip{display:none;}',
    '  .cm-subs{display:none!important;}',
    '  .cm-tab{flex:none;} .cm-tab .cm-no{display:none;} .cm-tab .cm-caret{display:none;}',
    '  .cm-page{flex-direction:column;align-items:stretch;}',
    '  .cm-pic img{max-height:34vh;}',
    '  .cm-player{max-height:34vh;}',
    '}'
  ].join('\n');

  /* ---------- 组件状态 ---------- */
  var root, panel, railEl, pageEl, progEl, countEl, prevBtn, nextBtn;
  var coverTabEl, chapterTabs = [], subsWraps = [], subBtns = [];
  var built = false, lastFocus = null, cur = -2;
  var PROG_KEY = 'cyber-manual-progress-v2';   // v2：页面含小节后序列变化，重置一次旧进度

  /* 页面序列：封面 + （每个章节：概览页 + 各小节页） */
  var PAGES = [{ type: 'cover' }];
  CHAPTERS.forEach(function (ch, ci) {
    PAGES.push({ type: 'chapter', ch: ci });   // 概览页（带小点的章节：右侧为小节导航卡）
    (ch.subs || []).forEach(function (s, si) { PAGES.push({ type: 'sub', ch: ci, sub: si }); });
  });

  function saveProgress(pi) { try { localStorage.setItem(PROG_KEY, String(pi)); } catch (e) {} }
  function loadProgress() {
    try {
      var v = parseInt(localStorage.getItem(PROG_KEY), 10);
      return isNaN(v) ? null : Math.min(Math.max(v, 0), PAGES.length - 1);
    } catch (e) { return null; }
  }
  function pagesOfChapter(ci) {
    var first = -1, last = -1;
    PAGES.forEach(function (p, i) {
      if (p.ch === ci) { if (first < 0) first = i; last = i; }
    });
    return { first: first, last: last };
  }
  function pageOfSub(ci, si) {
    for (var i = 0; i < PAGES.length; i++) {
      if (PAGES[i].type === 'sub' && PAGES[i].ch === ci && PAGES[i].sub === si) return i;
    }
    return 0;
  }

  function el(parent, tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    parent.appendChild(e);
    return e;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function chipbarHtml(no, crumb) {
    return '<div><span class="cm-chipbar"><span class="bar"></span>CHAPTER ' + no +
      (crumb ? '<span class="cm-crumb">· ' + crumb + '</span>' : '') + '</span></div>';
  }
  function pauseVideos() {
    Array.prototype.forEach.call(pageEl.querySelectorAll('video'), function (v) {
      try { v.pause(); } catch (e) {}
    });
  }

  /* ---------- 构建 ---------- */
  function build() {
    if (built) return;
    built = true;
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    root = el(document.body, 'div', 'cm-root');
    root.hidden = true;
    el(root, 'div', 'cm-mask').addEventListener('click', close);
    panel = el(root, 'div', 'cm-panel');

    railEl = el(panel, 'nav', 'cm-rail');
    var brand = el(railEl, 'div', 'cm-brand');
    el(brand, 'b').textContent = '使用手册';
    // 封面目录项
    coverTabEl = el(railEl, 'button', 'cm-tab');
    coverTabEl.type = 'button';
    coverTabEl.style.setProperty('--c', '#8fa3b8');
    coverTabEl.innerHTML = '<span class="cm-dotc"></span><span>封面</span><span class="cm-no">—</span>';
    coverTabEl.addEventListener('click', function () { render(0); });
    // 六个章节（大点）：带小点的章节附展开箭头与小点列表
    CHAPTERS.forEach(function (ch, ci) {
      var t = el(railEl, 'button', 'cm-tab');
      t.type = 'button';
      t.style.setProperty('--c', ch.color);
      t.innerHTML = '<span class="cm-dotc"></span><span>' + ch.name + '</span><span class="cm-no">' + ch.no + '</span>' +
        '<span class="cm-caret"' + (ch.subs ? ' title="展开 / 折叠小节"' : '') + '>' + (ch.subs ? CARET_SVG : '') + '</span>';
      t.addEventListener('click', function () { render(pagesOfChapter(ci).first); });   // 点父点：进章并展开小点
      if (ch.subs) {
        t.querySelector('.cm-caret').addEventListener('click', function (e) {
          e.stopPropagation();                                                          // 点箭头：仅展开 / 折叠，不跳转
          var w = subsWraps[ci];
          w.classList.toggle('open', !w.classList.contains('open'));
          t.classList.toggle('exp', w.classList.contains('open'));
        });
      }
      chapterTabs.push(t);
      if (ch.subs && ch.subs.length) {
        var wrap = el(railEl, 'div', 'cm-subs');
        var inner = el(wrap, 'div', 'cm-subs-in');
        var btns = [];
        ch.subs.forEach(function (s, si) {
          var b = el(inner, 'button', 'cm-sub');
          b.type = 'button';
          b.style.setProperty('--c', ch.color);
          b.innerHTML = '<span class="sdot"></span><span>' + s.name + '</span>';
          b.addEventListener('click', function () { render(pageOfSub(ci, si)); });
          btns.push(b);
        });
        subsWraps.push(wrap);
        subBtns.push(btns);
      } else {
        subsWraps.push(null);
        subBtns.push(null);
      }
    });
    var tip = el(railEl, 'div', 'cm-tip');
    tip.innerHTML = '← → 切换内容<br>Esc 关闭手册';

    var main = el(panel, 'section', 'cm-main');
    var closeBtn = el(main, 'button', 'cm-close');
    closeBtn.type = 'button'; closeBtn.textContent = '✕'; closeBtn.title = '关闭 (Esc)';
    closeBtn.addEventListener('click', close);
    pageEl = el(main, 'div', 'cm-page');
    // 入场动画结束后清除动画标记：避免 translateY 残影被计入滚动区，产生幻影滚动条
    pageEl.addEventListener('animationend', function (e) {
      if (e.animationName === 'cm-soft' && e.target && e.target.style) e.target.style.animation = 'none';
    });
    var foot = el(main, 'div', 'cm-foot');
    countEl = el(foot, 'span', 'cm-count');
    progEl = el(foot, 'div', 'cm-prog');
    el(progEl, 'i');
    prevBtn = el(foot, 'button', 'cm-btn cm-prev');
    prevBtn.type = 'button'; prevBtn.textContent = '上一步';
    nextBtn = el(foot, 'button', 'cm-btn cm-next');
    nextBtn.type = 'button'; nextBtn.textContent = '下一步';
    prevBtn.addEventListener('click', function () { if (cur > 0) render(cur - 1); });
    nextBtn.addEventListener('click', function () { if (cur < PAGES.length - 1) render(cur + 1); else close(); });

    document.addEventListener('keydown', onKey);
  }

  /* ---------- 渲染 ---------- */
  function render(pi) {
    cur = pi;
    saveProgress(pi);
    var pg = PAGES[pi];
    var ch = pg.ch === undefined ? null : CHAPTERS[pg.ch];
    panel.style.setProperty('--c', ch ? ch.color : '#58a6ff');

    /* 目录：封面/章节高亮，小点随所在章节自动展开（点父点或下一步进入该章时同样生效） */
    coverTabEl.classList.toggle('on', pg.type === 'cover');
    chapterTabs.forEach(function (t, ci) {
      var on = pg.ch === ci;
      t.classList.toggle('on', on);
      if (subsWraps[ci]) t.classList.toggle('exp', on);
    });
    subsWraps.forEach(function (w, ci) {
      if (w) w.classList.toggle('open', pg.ch === ci);
    });
    subBtns.forEach(function (btns, ci) {
      if (!btns) return;
      btns.forEach(function (b, si) {
        b.classList.toggle('on', pg.type === 'sub' && pg.ch === ci && pg.sub === si);
      });
    });

    /* 进度与按钮态（计数保持「章节号 / 总章数」，进度条按页推进） */
    countEl.textContent = pg.type === 'cover' ? '封面' : pad(pg.ch + 1) + ' / ' + pad(CHAPTERS.length);
    progEl.firstElementChild.style.width = (pi / (PAGES.length - 1) * 100) + '%';
    prevBtn.disabled = pi === 0;
    nextBtn.textContent = pi === PAGES.length - 1 ? '完 成' : '下一步';

    /* 内容 */
    pauseVideos();
    pageEl.classList.remove('cm-in');
    if (pg.type === 'cover') {
      pageEl.innerHTML =
        '<div class="cm-welcome">' +
        '  <div class="cm-wl-body">' +
        '    <h3 class="cm-wl-title">欢迎来到 CyberNWT</h3>' +
        '    <div class="cm-wl-sub">您的专属 · 赛博网络工具</div>' +
        '    <div class="cm-wl-div"></div>' +
        '    <p class="cm-wl-line">我们的设计理念是 —— <b>简洁实用，而又不失全面</b></p>' +
        '    <div class="cm-wl-sound">' +
        '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>' +
        '      </svg>' +
        '      <span>手册中录有真人演示视频，辛苦您打开声音观看！</span>' +
        '    </div>' +
        '    <div class="cm-wl-doc">详细介绍与说明请移步至<a href="download/CyberNWT-产品文档V2.docx" download>《产品文档》</a></div>' +
        '  </div>' +
        '</div>';
    } else if (pg.type === 'sub') {
      var sub = ch.subs[pg.sub];
      pageEl.innerHTML =
        '<div class="cm-txt">' +
        '  ' + chipbarHtml(ch.no) +
        '  <h3 class="cm-title">' + sub.name + '</h3>' +
        '  <div class="cm-tagline">' + sub.tagline + '</div>' +
        '  <p class="cm-desc" style="line-height:2.15">' + sub.desc + '</p>' +
        '  <ul class="cm-points">' + sub.points.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul>' +
        '</div>' +
        '<div class="cm-video">' +
        '  <div class="cm-video-head"><span class="bar"></span><span class="vt">演示视频 · DEMO</span>' +
        '<span class="cm-secbadge">SEC ' + pad(pg.sub + 1) + '/' + pad(ch.subs.length) + '</span></div>' +
        '  <div class="cm-player"><video controls preload="metadata" playsinline poster="' + sub.poster + '" src="' + sub.video + '"></video></div>' +
        '  <div class="cm-video-tip">' + SOUND_SVG + '<span>真人操作演示 · 点击播放，建议打开声音</span></div>' +
        '</div>' +
        '<div class="cm-ghost">' + ch.no + '</div>';
    } else if (ch.subs && ch.subs.length) {
      /* 大点概览页：去图片，右侧放「本章小节」导航卡（替代原配图，点击直达小节） */
      pageEl.innerHTML =
        '<div class="cm-txt">' +
        '  ' + chipbarHtml(ch.no) +
        '  <h3 class="cm-title">' + ch.name + '</h3>' +
        '  <div class="cm-tagline">' + ch.tagline + '</div>' +
        '  <p class="cm-desc">' + ch.desc + '</p>' +
        '  <div class="cm-chips">' + ch.chips.map(function (c) { return '<span class="cm-chip">' + c + '</span>'; }).join('') + '</div>' +
        '</div>' +
        '<div class="cm-subcards">' +
        '  <div class="cm-subcards-head"><span class="bar"></span>本章小节<em>' + ch.subs.length + ' 节 · 点击进入</em></div>' +
        ch.subs.map(function (s, si) {
          return '<button class="cm-subcard" type="button" data-pi="' + pageOfSub(pg.ch, si) + '" title="进入小节：' + s.name + '">' +
            '<span class="n">' + pad(si + 1) + '</span>' +
            '<span class="b"><span class="t">' + s.name + '</span><span class="d">' + s.brief + '</span></span>' +
            '<span class="go">' + PLAY_SVG + '</span></button>';
        }).join('') +
        '</div>' +
        '<div class="cm-ghost">' + ch.no + '</div>';
      Array.prototype.forEach.call(pageEl.querySelectorAll('.cm-subcard'), function (card) {
        card.addEventListener('click', function () { render(parseInt(card.dataset.pi, 10)); });
      });
    } else {
      pageEl.innerHTML =
        '<div class="cm-txt">' +
        '  ' + chipbarHtml(ch.no) +
        '  <h3 class="cm-title">' + ch.name + '</h3>' +
        '  <div class="cm-tagline">' + ch.tagline + '</div>' +
        '  <p class="cm-desc">' + ch.desc + '</p>' +
        '  <div class="cm-chips">' + ch.chips.map(function (c) { return '<span class="cm-chip">' + c + '</span>'; }).join('') + '</div>' +
        '</div>' +
        (ch.cards
          ? // 设计巧思章节：右侧三张要点卡 + 口号条（替代原 logo 配图）
          '<div class="cm-cards">' +
          ch.cards.map(function (c) {
            return '<div class="cm-card">' +
              '<span class="cm-card-ic">' + (CARD_ICONS[c.icon] || '') + '</span>' +
              '<span class="cm-card-b"><span class="cm-card-t">' + c.t + '</span><span class="cm-card-d">' + c.d + '</span></span>' +
              '</div>';
          }).join('') +
          '</div>'
          : ch.video
          ? // 配视频章节：右侧真人演示视频（与配图章节同一版位）
          '<div class="cm-video">' +
          '  <div class="cm-video-head"><span class="bar"></span><span class="vt">演示视频 · DEMO</span></div>' +
          '  <div class="cm-player"><video controls preload="metadata" playsinline poster="' + ch.poster + '" src="' + ch.video + '"></video></div>' +
          '  <div class="cm-video-tip">' + SOUND_SVG + '<span>真人操作演示 · 点击播放，建议打开声音</span></div>' +
          '</div>'
          : '<div class="cm-pic"><img src="' + ch.img + '" alt="' + ch.name + '"></div>') +
        '<div class="cm-ghost">' + ch.no + '</div>';
    }
    void pageEl.offsetWidth;   // 重触发入场动画
    pageEl.classList.add('cm-in');
  }

  function onKey(e) {
    if (root.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowRight' || e.key === 'PageDown') { if (cur < PAGES.length - 1) render(cur + 1); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { if (cur > 0) render(cur - 1); }
  }

  function open(pi) {
    build();
    lastFocus = document.activeElement;
    root.hidden = false;
    // 未指定起始页时恢复上次观看位置；无记录则从欢迎封面开始
    if (pi === undefined) {
      var saved = loadProgress();
      render(saved === null ? 0 : saved);
    } else {
      render(Math.min(Math.max(pi, 0), PAGES.length - 1));
    }
  }

  function close() {
    if (pageEl) pauseVideos();
    root.hidden = true;
    if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
  }

  window.CyberManual = { open: open, close: close };

  /* ---------- 自动接入：绑定页脚/顶栏的打开入口 ---------- */
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    function bindOpen(n) {
      if (!n || n.__cmBound) return;
      n.__cmBound = true;
      n.addEventListener('click', function (e) { e.preventDefault(); open(); });
    }
    bindOpen(document.getElementById('cg-replay'));
    Array.prototype.forEach.call(document.querySelectorAll('[data-cm-open]'), bindOpen);
  });
})();
