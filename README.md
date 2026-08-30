# CyberNWT（演示版）

登录 + 项目展示骨架站。零第三方依赖：后端为 Python 标准库 HTTP 服务器 + SQLite。

## 启动

```
python server.py            # 默认端口 8642，启动后自动打开浏览器
python server.py 9000       # 自定义端口
```

启动后访问 http://127.0.0.1:8642/

- 演示账号：**admin / admin**（首次启动自动写入数据库）
- 也可以在登录页自行注册新账号

## 文件结构

| 文件 | 说明 |
|------|------|
| `server.py` | 后端：静态文件服务 + 注册/登录/会话 API + 测速 API + AI 代理 + SQLite 存储 |
| `login.html` | 登录/注册页（深信服粒子 Logo 动效背景 + 玻璃拟态卡片） |
| `home.html` | 登录后的功能首页（四大功能模块入口） |
| `speedtest.html` | 灵犀测速：一键全链路测速 + 智能诊断 + JSON/Prometheus 输出 |
| `diagnose.html` | 故障诊断 AI 助手（深信服实施场景，预留 FastGPT 接入） |
| `review.html` | 案例复盘：输入项目过程，AI 生成结构化复盘报告 |
| `topology.html` | 内网感知 NetSense：识别本机接入方式与网关（实测），建模生成客户内网拓扑 + 部署模式建议 |
| `whiteboard.js` | 随心记录：全局悬浮白板组件（绘制 + 打字 + 自动保存），任意页面引入即用 |
| `test_api.py` | 接口自动化测试（18 项断言），运行：`python test_api.py`（需先启动 server） |
| `data.db` | SQLite 数据库，首次启动自动创建；删除后重启即重置（admin 会重新生成） |

## 功能模块

登录后进入功能首页，包含四个模块：

1. **灵犀测速**（`speedtest.html`）：一键测速，全过程约 4 秒；实时波形 + 全链路透视 + 评分与智能诊断结论 + 标准 JSON / Prometheus 指标 / 阈值告警。
2. **内网感知**（`topology.html`）：笔记本接入客户内网后感知接入方式（Wi-Fi/有线，实测）、网关与网段；生成可视化拓扑、网段/VLAN 表、设备清单与深信服部署模式建议，支持 Mermaid / JSON / PNG 导出。本机网卡为实测数据，内网设备为建模数据（真实部署时在 `server.py` 的 `build_modeled_network` 处接入 ARP/SNMP 探针引擎）。
3. **随心记录**（`whiteboard.js`，全站悬浮）：右下角悬浮球唤起白板，自由绘制与打字，自动保存浏览器本地，可导出 PNG。
4. **故障诊断助手**（`diagnose.html`）：AI 对话式排查深信服设备实施故障（上架/割接/VPN/链路等）。
5. **案例复盘**（`review.html`）：输入项目过程，AI 生成结构化复盘报告，可复制/下载 Markdown。

## 接入 FastGPT（可选）

AI 功能默认以「演示模式」运行（本地规则模板生成回答）。设置环境变量后自动切换为 FastGPT 真实大模型：

```
set FASTGPT_BASE=https://your-fastgpt.example.com/api/v1   # OpenAI 兼容地址
set FASTGPT_KEY=fastgpt-xxx
python server.py
```

## 安全说明（演示级）

- 密码使用 PBKDF2-SHA256（12 万次迭代 + 随机盐）加密存储，不存明文
- 会话使用 HttpOnly Cookie，有效期 7 天
- 未登录访问 `home.html` 会被服务端 302 重定向回登录页
- 服务仅绑定 127.0.0.1，不对局域网开放
