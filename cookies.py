"""Cookie 加载与过滤：优先 TIKTOK_COOKIES 环境变量（GitHub Secrets），退化到 cookies.json。"""
from __future__ import annotations

import json
import os
from pathlib import Path

TIKTOK_DOMAINS = ("tiktok.com", ".tiktok.com", "www.tiktok.com")

ROOT = Path(__file__).resolve().parent


def _normalize(raw) -> list:
    """把各种 cookie 输入规整为 list[dict]，至少包含 name/value/domain。"""
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Cookie 头形式 name=value; name2=value2
            return _from_header(raw)
    else:
        data = raw

    if isinstance(data, dict):
        # Playwright storage_state: {"cookies": [...]}
        if isinstance(data.get("cookies"), list):
            return data["cookies"]
        return []
    if isinstance(data, list):
        return data
    return []


def _from_header(header: str) -> list:
    out = []
    for pair in header.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        out.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".tiktok.com",
            "path": "/",
            "secure": True,
        })
    return out


def is_tiktok_cookie(c: dict) -> bool:
    domain = str(c.get("domain", "")).lower()
    return any(domain == d or domain.endswith("." + d.lstrip(".")) or domain.endswith(d) for d in TIKTOK_DOMAINS)


_SAME_SITE = {
    "none": "None",
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
}


def _to_playwright(c: dict) -> dict | None:
    """把 Cookie-Editor / DevTools 导出的 cookie 规整成 Playwright add_cookies 可接受的格式。"""
    name = c.get("name")
    if not name:
        return None
    out = {"name": str(name), "value": str(c.get("value", "")), "url": None}
    if c.get("domain"):
        out["domain"] = c["domain"]
    if c.get("path"):
        out["path"] = c["path"]
    if c.get("httpOnly"):
        out["httpOnly"] = True
    if c.get("secure"):
        out["secure"] = True
    expires = c.get("expires") or c.get("expirationDate")
    if expires:
        out["expires"] = float(expires)
    ss = c.get("sameSite")
    if isinstance(ss, str):
        mapped = _SAME_SITE.get(ss.strip().lower())
        if mapped:
            out["sameSite"] = mapped
    out.pop("url", None)
    return out


def sanitize_for_playwright(cookies: list) -> list:
    """把所有 cookie 清洗为 Playwright 兼容格式，丢弃无效项。"""
    cleaned = []
    for c in cookies:
        item = _to_playwright(c)
        if item:
            cleaned.append(item)
    return cleaned


def load_cookies(env: dict | None = None) -> tuple[list, str]:
    """返回 (cookies, source)。source: env / file / none"""
    env = env if env is not None else os.environ

    if env.get("TIKTOK_COOKIES"):
        try:
            cookies = sanitize_for_playwright([c for c in _normalize(env["TIKTOK_COOKIES"]) if is_tiktok_cookie(c)])
            if cookies:
                print(f"[cookies] 从环境变量 TIKTOK_COOKIES 载入 {len(cookies)} 条 cookie")
                return cookies, "env"
        except Exception as err:  # noqa: BLE001
            print(f"[cookies] 解析 TIKTOK_COOKIES 失败: {err}")

    file = Path(ROOT, "cookies.json")
    if file.exists():
        try:
            cookies = sanitize_for_playwright([c for c in _normalize(file.read_text(encoding="utf-8")) if is_tiktok_cookie(c)])
            if cookies:
                print(f"[cookies] 从本地文件 cookies.json 载入 {len(cookies)} 条 cookie")
                return cookies, "file"
        except Exception as err:  # noqa: BLE001
            print(f"[cookies] 读取 cookies.json 失败: {err}")

    return [], "none"