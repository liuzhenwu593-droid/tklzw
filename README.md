# TikTok 续火花（Streak Keeper）· Python 版

基于 **GitHub Actions 定时 + Python/Playwright 无头浏览器** 的 TikTok 会话火花维持工具，并支持 **Telegram 机器人推送详细执行结果**。
每天自动向好友列表逐个发送固定消息模板，保持对话火花不断。完全免费、无需常开电脑。

> 单一 TikTok 账号，向**多个好友**发送**固定消息模板**（支持 `{username}`/`{date}`/`{time}` 占位符），跑完通过 Telegram 机器人推送每位好友的成功/失败明细。

## 特性

- 定时自动运行：GitHub Actions `schedule`（每日）+ 手动触发
- 多收件人列表 + 消息模板（随机取一条）
- Telegram 机器人提醒：发送详情报告，失败时附带截图
- 登录 Cookie 存于 GitHub Secrets（`TIKTOK_COOKIES`），不入仓库
- 反检测：关闭自动化标记、串行 + 随机延迟
- 失败自动截图，可上传 Actions Artifact 排查
- `--dry-run` 试跑模式

## 账号安全护栏（尽力保护你的号）

这些是用**温和、合规**的方式降低封号/限流风险，已在 `config.example.json` 中默认开启：

| 选项 | 默认 | 作用 |
|------|------|------|
| `minDelayMs` / `maxDelayMs` | 6s / 18s | 每两条消息之间随机间隔，避免突发连发 |
| `startDelayMs` | 8s | 冷启动随机延迟（实际乘 0.5~1.5），避免整点集中触发 |
| `maxDailySends` | 50 | 单日发送上限，超出部分自动跳过并在报告中提示 |
| `abortAfterFails` | 3 | 连续失败熔断：疑似被风控/页面异常时立即收手，余下收件人跳过，保护账号 |
| `cooldownAfterFailMs` | 20s | 某好友失败后，下一条再额外冷却，放慢节奏 |
| 随机错峰 | 是 | 定时任务触发时随机 sleep，错开整点 |
| 会话失效即停 | 是 | 检测到跳转登录页立即中止并 exit 2，绝不硬闯 |
| 拟人输入 | 是 | 逐字非等速键入，句读后/偶发“思考”停顿，而非瞬间填满 |
| 发送校验 | 是 | 发送后检查输入框已清空且消息出现在消息流，避免静默丢消息却误判成功 |

**明确不做（也不建议）的实现**：验证码自动打码、代理池/IP 轮换、伪造浏览器指纹（canvas/WebGL/TLS）、伪造鼠标轨迹等"主动欺骗反作弊"手段。这些会把项目推向规避平台安全措施的方向，对单账号低频率的续火花场景不仅无益，反而更危险。你的账号安全，靠的是**低频率 + 随机节奏 + 异常即停**，而不是对抗式伪装。

## 目录结构

```
tiktok-streak/
├── .github/workflows/streak.yml   # GitHub Actions 定时工作流（含 TG 推送）
├── main.py                        # 主入口（编排 + Telegram 报告）
├── config.py                      # 配置加载（含默认值与 --dry-run）
├── cookies.py                     # Cookie 加载与 tiktok 域名过滤
├── sender.py                      # Playwright 发送逻辑 + 反检测
├── notifier.py                    # Telegram 机器人推送（文本 + 截图）
├── config.example.json            # 配置示例（复制为 config.json 使用）
├── requirements.txt
├── README.md
└── LICENSE                        # MIT
```

## 快速开始

### 1. 推送仓库

将本项目推送到你的 GitHub（建议私有仓库）。

### 2. 准备配置文件

复制 `config.example.json` 为 `config.json` 并编辑：

```jsonc
{
  "run": {
    "headless": true,          // CI 保持 true
    "dryRun": false,           // true=试跑不发送
    "minDelayMs": 4000,        // 消息间最小延迟(ms)
    "maxDelayMs": 12000,       // 消息间最大延迟(ms)
    "saveShotPerSend": false
  },
  "sendStrategy": "profile",   // profile=主页Message按钮 / messages=直接进消息列表
  "templates": [
    "今天也要一起继续火花哦 {username} 🔥",
    "来续火花啦，{date} {time} 打卡 📸"
  ],
  "recipients": ["friend_username_1", "friend_username_2"],
  "telegram": { "enabled": true }
}
```

- `recipients`：接收消息的好友用户名（不含 `@`）
- `templates`：消息模板，随机取一条；支持 `{username}` `{date}` `{time}`
- `config.json` 已被 `.gitignore` 忽略，不会提交

### 3. 配置 GitHub Secrets

在 `Settings → Secrets and variables → Actions` 添加：

| Secret | 说明 |
|--------|------|
| `TIKTOK_COOKIES` | 已登录 TikTok 的 Cookie（JSON 数组字符串），必填 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token，选填（不填则不推送） |
| `TELEGRAM_CHAT_ID` | 接收消息的 Chat/Dialog ID，选填 |

**获取 Cookie**：浏览器打开已登录 tiktok.com 页面，在 DevTools → Console 执行：

```js
copy(JSON.stringify(document.cookie.split('; ').map(c => {
  const [name, ...rest] = c.split('=');
  return { name, value: rest.join('=') };
})));
```

将输出的 JSON 字符串作为 `TIKTOK_COOKIES` 的值。（或用 Cookie-Editor 扩展直接导出。）

### 4. 获取 Telegram Bot

1. 与 [@BotFather](https://t.me/BotFather) 对话，`/newbot` 创建机器人，得到 `TELEGRAM_BOT_TOKEN`。
2. 把自己的账号或群组指定为接收目标，获取对应的数字 ID（如用 @userinfobot 私聊获取），填入 `TELEGRAM_CHAT_ID`。
3. 把两者加入仓库 Secrets。

### 5. 测试并启用

仓库 Actions 页 → "TikTok 续火花" → **Run workflow** 手动触发一次，确认发送成功后 Telegram 能收到报告，再等待每日定时即可。

## 自定义定时

编辑 `.github/workflows/streak.yml` 中的 cron（**UTC 时区**，北京 18:00 = UTC 10:00）：

```yaml
on:
  schedule:
    - cron: "0 10 * * *"
```

## 本地试运行

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
python main.py --dry-run     # 试跑，不发送
```

本地也会优先读环境变量，否则读根目录 `cookies.json`。

## Telegram 报告示例

```
🔥 TikTok 续火花执行报告
时间: 2026-08-28 10:00:05 (UTC)
收件人: 2 | 成功: 2 | 失败: 0

✅ @friend_username_1
✅ @friend_username_2

—— GitHub Actions · TikTok Streak Keeper
```

如有失败，会列出失败项原因，并附带对应的 `error_*.png` 截图。

## 常见问题

- **报错 exit 2（会话过期）**：Cookie 失效，重新导出并更新 `TIKTOK_COOKIES`。
- **某个好友失败**：可能对方关闭私信/无 Message 按钮，脚本已截图并随 Telegram 报告/Artifact 供排查。
- **公共仓库定时被暂停**：超过 60 天无活动会暂停 schedule，手动触发一次即可恢复。

## 免责声明

本项目仅供个人学习与技术研究，请遵守 TikTok 服务条款与当地法律。自动发送存在被平台检测、限流甚至封号的风险，使用者须自行承担后果。Telegram 推送与定时任务均需自行负责相应平台账号的合规使用。