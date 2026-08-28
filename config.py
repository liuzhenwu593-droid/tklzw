"""配置加载：resolve_config 从 config.json 读取，缺失时回退到 config.example.json。"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULTS = {
    "run": {
        "headless": True,
        "dryRun": False,
        "browser": "chromium",
        "locale": "en-US",
        "minDelayMs": 6000,
        "maxDelayMs": 18000,
        "startDelayMs": 8000,
        "maxDailySends": 50,
        "abortAfterFails": 3,
        "cooldownAfterFailMs": 20000,
        "shotsDir": "shots",
        "saveShotPerSend": False,
    },
    "sendStrategy": "profile",
    "templates": ["Today's streak! 🔥"],
    "recipients": [],
    "telegram": {"enabled": True},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def resolve_config(cli_config: str = "config.json") -> dict:
    config_path = Path(ROOT, cli_config)
    if not config_path.exists():
        config_path = Path(ROOT, "config.example.json")
        print(f"[config] 未找到 config.json，已回退到示例配置 config.example.json")

    with open(config_path, "r", encoding="utf-8") as fh:
        user_cfg = json.load(fh)

    cfg = _deep_merge(DEFAULTS, user_cfg)

    # 命令行 --dry-run 覆盖
    if "--dry-run" in os.sys.argv or cfg["run"].get("dryRun"):
        cfg["run"]["dryRun"] = True

    return cfg


def get_env_config() -> dict:
    return {
        "tiktok_cookies": os.environ.get("TIKTOK_COOKIES", ""),
        "tg_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "tg_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    }