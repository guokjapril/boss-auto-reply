# BOSS直聘自动复聊脚本

## 一、使用说明

### 1. 下载

从 GitHub 仓库下载 `BossAutoReply-Windows.zip`：

> **Actions** → 最新的成功构建 → **Artifacts** → 下载 `BossAutoReply-Windows`

### 2. 解压运行

```
BossAutoReply-Windows/
├── BossAutoReply.exe      ← 双击运行
└── ms-playwright/         ← 浏览器内核（已打包）
```

双击 `BossAutoReply.exe`，会出现控制台窗口。

### 3. 首次扫码登录

启动后控制台会提示：

```
正在检查登录状态…
请使用 BOSS直聘 APP 扫码登录
等待扫码中（超时 120 秒）…
```

打开 **BOSS直聘 APP** → 扫一扫 → 扫码登录。

登录成功后自动保存，**下次启动无需再次扫码**。

### 4. 自动复聊

登录后脚本自动进入消息列表页面，每隔 **10 秒** 轮询一次新消息。

检测到新消息 → 自动匹配关键词 → 发送对应话术。

已回复过的消息会记录到本地 `data/` 目录，不会重复发送。

### 5. 修改回复话术

编辑同目录下的 `config.yaml` 文件：

```yaml
reply:
  templates:
    - keywords: ["你好", "您好", "在吗"]
      reply: "您好！方便发一份您的简历吗？"
    - keywords: ["薪资", "待遇"]
      reply: "薪资面议，您方便的话可以先聊聊～"
```

### 6. 退出

按 `Ctrl+C` 或直接关闭控制台窗口。

---

## 二、实现原理

### 整体架构

```
main.py（入口）
  ├── browser.py  → 启动 Chromium 浏览器，反检测
  ├── login.py    → BOSS 直聘扫码登录，session 持久化
  ├── monitor.py  → 轮询消息列表，提取新消息
  ├── reply_engine.py → 模板匹配回复 / AI 回复
  └── ai_client.py → AI 接口预留
```

### 核心流程

```
启动浏览器 → 检查登录态
  ├─ 已登录 → 直接进消息页
  └─ 未登录 → 等待扫码 → 登录
      ↓
轮询消息列表（10s 间隔）
      ↓
检测到新消息 → 提取候选人 + 消息内容
      ↓
关键词匹配 → 发送对应话术
      ↓
记录到本地 JSON → 防重复 → 继续轮询
```

### 关键技术点

**1. 浏览器自动化（Playwright）**

使用 Playwright 控制真实的 Chromium 浏览器，模拟人工操作。支持无头模式（后台运行）和有头模式（可见窗口）。

**2. 反检测**

- 注入脚本隐藏 `navigator.webdriver` 属性
- 随机化操作延迟（200ms-2000ms）
- 模拟中文语言环境
- 每小时回复数限制，防止触发平台风控

**3. Session 持久化**

Playwright 的 `launch_persistent_context` 将浏览器的 cookie、localStorage 保存到本地目录。登录一次后，下次启动自动恢复登录态。

**4. 消息去重**

每条消息通过 `候选人名字 + 消息内容` 生成 MD5 哈希，已回复的 ID 存入 `data/processed_messages.json`，重启后不会丢失。

**5. 打包方案**

PyInstaller 将 Python 代码 + 依赖打包成单个 `.exe`，无需安装 Python 环境。Chromium 浏览器内核通过 GitHub Actions 随包分发。

**6. AI 回复（预留）**

`reply.mode` 设为 `ai` 后，可接入 OpenAI / Claude 接口生成智能回复。配置 `api_key` 即可启用。

### 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `browser.headless` | 无头模式 | `false`（首次扫码需可见） |
| `monitor.poll_interval` | 轮询间隔 | `10` 秒 |
| `reply.mode` | 回复模式 | `template` |
| `reply.rate_limit_per_hour` | 每小时上限 | `50` 条 |
| `reply.min_delay / max_delay` | 操作延迟范围 | `1.0~3.0` 秒 |

### 目录结构

```
BossAutoReply-Windows/
├── BossAutoReply.exe      # 主程序
├── config.yaml             # 配置文件（可编辑）
├── ms-playwright/          # Chromium 浏览器内核
└── data/                   # 运行时数据（自动生成）
    ├── browser_state/      # 登录 session
    ├── bot.log             # 运行日志
    └── processed_messages.json  # 已回复记录
```
