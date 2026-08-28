#!/usr/bin/env python3
"""TikTok 续火花主入口。

用法：
  python main.py                 # 正常执行（默认读取 config.json）
  python main.py --dry-run       # 试跑，不真实发送
  python main.py --config my.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from config import ROOT, get_env_config, resolve_config
from cookies import load_cookies
from notifier import TelegramNotifier
from sender import LoginExpiredError, StreakSender


def build_report(results, utc_now, errors=None) -> str:
    real = [r for r in results if not r.get("notice")]
    ok_count = sum(1 for r in real if r["ok"])
    fail = [r for r in real if not r["ok"]]
    notices = [r["user"] for r in results if r.get("notice")]

    lines = [
        "🔥 TikTok 续火花执行报告",
        f"时间: {utc_now} (UTC)",
        f"收件人: {len(real)} | 成功: {ok_count} | 失败: {len(fail)}",
        "",
    ]
    for r in real:
        if r["ok"]:
            lines.append(f"✅ @{r['user']}" + ("（试跑）" if r.get("dry") else ""))
        else:
            lines.append(f"❌ @{r['user']}: {r.get('reason', '未知错误')}")
    for n in notices:
        lines.append(f"ℹ️ {n}")
    if fail:
        lines.append("")
        lines.append("⚠️ 有失败项：若为连续失败/疑似风控，任务已安全中止以保护账号。")
    if errors:
        lines.append("")
        lines.append("⚠️ 全局异常: " + errors)
    lines += ["", "—— GitHub Actions · TikTok Streak Keeper"]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--config" in argv:
        idx = argv.index("--config")
        cfg_file = argv[idx + 1] if idx + 1 < len(argv) else "config.json"
    else:
        cfg_file = "config.json"

    cfg = resolve_config(cfg_file)
    env = get_env_config()

    print("[start] TikTok Streak Keeper (Python) 启动")
    if cfg["run"].get("dryRun"):
        print("[dry-run] 试跑模式：不会真实发送消息")
    print(f"[config] 收件人: {len(cfg.get('recipients', []))} 人, 模板: {len(cfg.get('templates', []))} 条")

    cookies, source = load_cookies(env)
    if not cookies:
        print("[fatal] 未找到有效的 TikTok cookie（尝试过 TIKTOK_COOKIES 环境变量和 cookies.json）")
        print("[fatal] 请导出 cookie 并配置 TIKTOK_COOKIES，详见 README。")
        return 1
    print(f"[cookies] 来源: {source}, 有效条数: {len(cookies)}")

    notifier = TelegramNotifier(env["tg_bot_token"], env["tg_chat_id"])
    if not notifier.ready:
        print("[telegram] 未配置 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID，跳过机器人提醒")

    sender = StreakSender(cfg)
    utc_now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    global_err = None
    exit_code = 0
    results = []
    try:
        results = sender.run(cookies)
    except LoginExpiredError as err:
        global_err = str(err)
        print(f"\n[fatal] {err}")
        exit_code = 2
    except Exception as err:  # noqa: BLE001
        global_err = f"{err}"
        print(f"\n[fatal] 未捕获异常: {err}")
        exit_code = 1

    report = build_report(results, utc_now, global_err)

    # 汇总截图（失败/全局送 Telegram 附注）
    shot_paths = [Path(r["shot"]) for r in results if r.get("shot") and Path(r["shot"]).exists()]
    if global_err:
        # 收集 shots 目录里所有错误截图
        shots_dir = Path(ROOT, cfg["run"].get("shotsDir", "shots"))
        shot_paths += sorted(shots_dir.glob("error_*.png"))[:5]

    # 无论成功失败都推送报告
    if notifier.ready:
        notifier.send_detailed_report(report, shot_paths)
        print(f"[telegram] 已推送提醒（{len(results)} 用户，{len(shot_paths)} 张截图）")
    else:
        print("[telegram] 未推送（未配置）")

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n[summary] 成功: {ok_count}, 失败: {len(results) - ok_count}, 总计: {len(results)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())