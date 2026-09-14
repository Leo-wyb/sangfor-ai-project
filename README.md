# CyberNWT（演示版）

登录 + 项目展示骨架站。零第三方依赖：后端为 Python 标准库 HTTP 服务器 + SQLite。

## 启动

最终用户（产品包形态，零安装）：

```
双击 CyberNWT.exe           # 自带 runtime\ Python 运行环境，默认端口 8642，自动打开登录页
CyberNWT.exe 8643           # 自定义端口
```

开发调试（本机已装 Python 3）：

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
| `diagnose.html` | 故障诊断 AI 助手（深信服实施场景，对接 FastGPT） |
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

AI 功能默认以「演示模式」运行（本地规则模板生成回答）。对接 FastGPT（OpenAI 兼容接口）后自动切换为真实大模型，由 FastGPT 双知识库（故障诊断知识库 + 设备部署知识库）提供领域支撑。在 `fastgpt.config`（KEY=VALUE 每行一条，已加入 .gitignore）配置，环境变量优先：

```
LLM_BASE=https://cloud.fastgpt.cn/api/v1   # FastGPT 的 OpenAI 兼容地址
LLM_KEY=fastgpt-xxx                        # FastGPT「API 密钥」处创建
LLM_MODEL_DIAG=模型名                      # 诊断模型（可选）
LLM_MODEL_REVIEW=模型名                    # 复盘模型（可选）
LLM_THINKING=on                            # 可选，默认 off 加快出答案速度
```

配置后重启服务，启动日志出现 `[config] FastGPT 已接入` 即生效。

### 密钥加密存储（公网部署建议）

明文 `fastgpt.config` 配置好后，在本目录执行一次：

```
..\runtime\python.exe encrypt_config.py
```

会生成加密文件 `fastgpt.config.enc` 并自动删除明文（先解密回读校验，校验通过才删）。服务启动时优先读取 `.enc` 并在内存中解密，功能与交互完全不变；算法为 PBKDF2（20 万次迭代）+ HMAC 流加密 + 防篡改校验，仅用标准库实现，**不绑定机器**，整包拷到任何电脑均可正常解密使用。

- 改密钥：`..\runtime\python.exe encrypt_config.py --decrypt` 还原明文，改完后再执行一次加密；
- 加密后磁盘与启动日志均不出现密钥明文；`.enc` 与 `fastgpt.config` 均被 pack.py 排除、HTTP 层不可下载。

## 安全说明（演示级）

- 密码使用 PBKDF2-SHA256（12 万次迭代 + 随机盐）加密存储，不存明文
- 会话使用 HttpOnly Cookie，有效期 7 天
- 未登录访问 `home.html` 会被服务端 302 重定向回登录页
- 服务监听 8642 端口，默认本机访问；想让局域网其他电脑访问，放行防火墙后用 http://<本机IP>:8642
