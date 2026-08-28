"""Playwright 无头发送逻辑：逐个好友发送随机模板，带反检测与失败截图。"""
from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_MARKERS = ("/login",)

# 候选选择器（TikTok DOM 常变，多备几手）
MESSAGE_BTN_DATA = (
    'button[data-e2e*="message" i]',
    'button[data-e2e*="dm" i]',
    '[data-e2e="user-bottom-bar"] button[role="button"]',
)
EDITOR_SELECTORS = (
    '[data-e2e="chat-input"] [contenteditable="true"]',
    '[contenteditable="true"]',
    '.public-DraftEditor-content[contenteditable="true"]',
    'textarea[data-e2e="chat-input"]',
)
SEND_SELECTORS = (
    '[data-e2e*="send" i]',
    'button[type="submit"]',
    'div[data-e2e="chat-input-area"] button',
)


class LoginExpiredError(Exception):
    """会话失效：页面跳转登录页。"""


def _now_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _sleep(ms: float):
    time.sleep(ms / 1000.0)


def _is_login(page) -> bool:
    return any(m in page.url for m in LOGIN_MARKERS)


def build_text(template: str, username: str) -> str:
    now = time.localtime()
    return (template
            .replace("{username}", username)
            .replace("{date}", time.strftime("%Y-%m-%d", now))
            .replace("{time}", time.strftime("%H:%M", now)))


def _first_visible(page, selectors, timeout=5000):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:  # noqa: BLE001
            continue
    return None


def _find_message_button(page):
    try:
        by_text = page.get_by_role("button", name=re.compile("message", re.I)).first
        by_text.wait_for(state="visible", timeout=4000)
        return by_text
    except Exception:  # noqa: BLE001
        pass
    return _first_visible(page, MESSAGE_BTN_DATA, 4000)


def _type_humanlike(page, text: str):
    """拟人输入：逐字打，但按键间隔非等速，句读后/偶发停顿更像真人。"""
    for i, ch in enumerate(text):
        # 基础延迟 + 随机波动（不等间隔）
        delay = 28 + random.random() * 48
        # 句读/空格后常停顿；或约 4% 概率随机“思考”停顿
        if ch in " ，。,.!?;：、\u3000" or random.random() < 0.04:
            delay += 120 + random.random() * 380
        # 首字符略慢，模拟起手
        if i == 0:
            delay += 300
        page.keyboard.type(" " if ch == "\n" else ch, delay=delay)


def _fill_editor(page, text: str) -> bool:
    editor = _first_visible(page, EDITOR_SELECTORS, 4000)
    if not editor:
        return False
    try:
        editor.click()
        _sleep(300)
    except Exception:  # noqa: BLE001
        pass
    _type_humanlike(page, text)
    _sleep(350 + random.random() * 300)
    return True


def _editor_empty(page) -> bool | None:
    """发送后检查输入框是否清空。返回 None 表示无法判定。"""
    ed = _first_visible(page, EDITOR_SELECTORS, 1500)
    if not ed:
        return None
    try:
        return (ed.inner_text() or "").strip() == ""
    except Exception:  # noqa: BLE001
        return None


def _message_in_flow(page, text: str) -> bool:
    """尽力在消息流中确认该条消息真的发出去了。"""
    fragment = text.strip()[:30]
    if not fragment:
        return False
    try:
        page.get_by_text(fragment, exact=False).first.wait_for(state="visible", timeout=3500)
        return True
    except Exception:  # noqa: BLE001
        return False


def _verify_send(page, text: str) -> tuple[bool, str]:
    """发送后校验：输入框已清空 + 消息出现在消息流，避免静默丢消息却误判成功。"""
    empty = _editor_empty(page)
    if empty is False:
        _sleep(900)
        empty = _editor_empty(page)
    if empty is False:
        return False, "发送后输入框未清空，消息未真正发出"
    if not _message_in_flow(page, text):
        return False, "输入框已清空但消息流中未见该消息，疑似被静默丢弃"
    return True, "ok"


def _submit(page) -> bool:
    send_btn = _first_visible(page, SEND_SELECTORS, 3000)
    if send_btn:
        try:
            send_btn.click()
            _sleep(600)
            return True
        except Exception:  # noqa: BLE001
            pass
    try:
        page.keyboard.press("Enter")
        _sleep(800)
        return True
    except Exception:  # noqa: BLE001
        return False


def _shot(page, dirpath: Path, tag: str) -> str:
    dirpath.mkdir(parents=True, exist_ok=True)
    name = f"error_{tag}_{_now_tag()}.png"
    try:
        page.screenshot(path=str(dirpath / name))
        return str(dirpath / name)
    except Exception:  # noqa: BLE001
        return ""


def _send_via_profile(page, user: str, text: str, shots_dir: Path, save_ok_shot: bool) -> dict:
    page.goto(f"https://www.tiktok.com/@{user}?lang=en", wait_until="domcontentloaded", timeout=60000)
    _sleep(3000)
    if _is_login(page):
        raise LoginExpiredError()

    btn = _find_message_button(page)
    if not btn:
        path = _shot(page, shots_dir, f"{user}_no_msg_btn")
        return {"ok": False, "reason": "未找到 Message 按钮（对方可能未开启私信）", "shot": path}
    btn.click()
    _sleep(2500)

    if not _fill_editor(page, text):
        path = _shot(page, shots_dir, f"{user}_no_editor")
        return {"ok": False, "reason": "未找到消息输入框", "shot": path}

    sent = _submit(page)
    if not sent:
        path = _shot(page, shots_dir, f"{user}_send_fail")
        return {"ok": False, "reason": "未能触发发送", "shot": path}

    # 发送校验：输入框清空 + 消息出现在消息流
    verified, detail = _verify_send(page, text)
    if not verified:
        path = _shot(page, shots_dir, f"{user}_verify_fail")
        return {"ok": False, "reason": detail, "shot": path}

    shot = ""
    if save_ok_shot:
        shots_dir.mkdir(parents=True, exist_ok=True)
        shot = str(shots_dir / f"ok_{user}_{_now_tag()}.png")
        try:
            page.screenshot(path=shot)
        except Exception:  # noqa: BLE001
            shot = ""
    return {"ok": True, "shot": shot}


class StreakSender:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ROOT = Path(__file__).resolve().parent
        self.shots_dir = Path(self.ROOT, cfg["run"].get("shotsDir", "shots"))

    def _launch_args(self):
        return ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]

    def run(self, cookies: list):
        results = []
        with sync_playwright() as p:
            browser_cls = p.chromium if self.cfg["run"].get("browser", "chromium") == "chromium" else p.firefox
            browser = browser_cls.launch(headless=self.cfg["run"]["headless"], args=self._launch_args())
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
                locale=self.cfg["run"].get("locale", "en-US"),
            )
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            try:
                # 登录态检查
                page.goto("https://www.tiktok.com/?lang=en", wait_until="domcontentloaded", timeout=60000)
                _sleep(2500)
                if _is_login(page):
                    raise LoginExpiredError()

                recipients = self.cfg.get("recipients", [])
                mini = self.cfg["run"].get("minDelayMs", 6000)
                maxi = self.cfg["run"].get("maxDelayMs", 18000)
                max_sends = int(self.cfg["run"].get("maxDailySends", 50)) or 50
                abort_after = int(self.cfg["run"].get("abortAfterFails", 3))
                cooldown = self.cfg["run"].get("cooldownAfterFailMs", 20000)

                # 安全护栏 1：每日发送上限，超出部分跳过并记录
                truncated = 0
                if len(recipients) > max_sends:
                    print(f"[safety] 收件人 {len(recipients)} 人超过 maxDailySends={max_sends}，本次仅处理前 {max_sends} 人")
                    truncated = len(recipients) - max_sends
                targets = recipients[:max_sends]

                # 安全护栏 2：冷启动随机延迟，避免定时任务整点集中触发
                _sleep(self.cfg["run"].get("startDelayMs", 8000) * random.uniform(0.5, 1.5))

                consecutive_fails = 0
                aborted = False
                for idx, user in enumerate(targets):
                    if aborted:
                        results.append({"user": user, "ok": False, "reason": "因连续失败已安全中止，跳过", "shot": ""})
                        continue
                    text = build_text(self._pick_template(), user)
                    print(f"\n[发送] @{user} -> {text[:40]!r}…")
                    if self.cfg["run"].get("dryRun"):
                        print(f"[dry-run] 跳过真实发送（模板={text!r}）")
                        results.append({"user": user, "ok": True, "dry": True, "shot": ""})
                        continue
                    try:
                        if self.cfg.get("sendStrategy") == "messages":
                            res = self._send_via_messages(page, user, text)
                        else:
                            res = _send_via_profile(page, user, text, self.shots_dir, self.cfg["run"].get("saveShotPerSend", False))
                        state = "成功" if res["ok"] else "失败 - " + res.get("reason", "")
                        print(f"[结果] @{user}: {state}")
                        results.append({"user": user, **res})
                        consecutive_fails = consecutive_fails + 1 if not res["ok"] else 0
                    except LoginExpiredError:
                        raise
                    except Exception as err:  # noqa: BLE001
                        shot = _shot(page, self.shots_dir, f"{user}_exception")
                        print(f"[结果] @{user}: 异常 - {err}")
                        results.append({"user": user, "ok": False, "reason": str(err), "shot": shot})
                        consecutive_fails += 1

                    # 安全护栏 3：连续失败熔断——疑似被风控/页面结构异常时立即收手，不硬闯
                    if consecutive_fails >= abort_after:
                        print(f"[safety] 连续失败 {consecutive_fails} 次达到熔断阈值，中止本次任务以保护账号（余下收件人跳过）")
                        aborted = True
                        continue

                    # 发送间隔：随机化 + 若刚失败额外冷却，放慢节奏
                    if idx < len(targets) - 1:
                        wait = random.uniform(mini, maxi)
                        if not results[-1]["ok"]:
                            wait += cooldown
                        _sleep(wait)

                if truncated:
                    results.insert(0, {"user": f"(已跳过 {truncated} 人：超过每日上限 {max_sends})", "ok": True, "dry": True, "shot": "", "notice": True})
            finally:
                browser.close()
        return results

    def _pick_template(self) -> str:
        templates = self.cfg.get("templates") or ["Streak! 🔥"]
        return random.choice(templates)

    def _send_via_messages(self, page, user: str, text: str) -> dict:
        """方案 messages：直接进消息列表，从会话找到该用户再发。"""
        page.goto("https://www.tiktok.com/messages?lang=en", wait_until="domcontentloaded", timeout=60000)
        _sleep(3500)
        if _is_login(page):
            raise LoginExpiredError()
        # 在会话列表中按用户名文本定位（会话项通常含可读名称）
        item = page.get_by_text(re.compile(re.escape(user), re.I)).first
        try:
            item.wait_for(state="visible", timeout=6000)
            item.click()
        except Exception:  # noqa: BLE001
            path = _shot(page, self.shots_dir, f"{user}_no_convo")
            return {"ok": False, "reason": "消息列表中未找到该用户的会话", "shot": path}
        _sleep(2000)
        if not _fill_editor(page, text):
            path = _shot(page, self.shots_dir, f"{user}_no_editor")
            return {"ok": False, "reason": "未找到消息输入框", "shot": path}
        if not _submit(page):
            path = _shot(page, self.shots_dir, f"{user}_send_fail")
            return {"ok": False, "reason": "未能触发发送", "shot": path}
        verified, detail = _verify_send(page, text)
        if not verified:
            path = _shot(page, self.shots_dir, f"{user}_verify_fail")
            return {"ok": False, "reason": detail, "shot": path}
        return {"ok": True, "shot": ""}