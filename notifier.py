"""Telegram 机器人通知：用 Bot API 发送详细执行结果，可附带失败截图。"""
from __future__ import annotations

import io
import json
import mimetypes
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.telegram.org/bot{token}/"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id).strip()
        self.base = API.format(token=token) if token else ""
        self.ready = bool(token and self.chat_id and not self.chat_id.startswith("__"))

    def _url(self, method: str) -> str:
        return f"{self.base}{method}"

    def _post(self, method: str, data: dict) -> dict:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(self._url(method), data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "unknown telegram error"))
        return payload

    def send_text(self, text: str) -> bool:
        if not self.ready:
            return False
        try:
            self._post("sendMessage", {"chat_id": self.chat_id, "text": text})
            return True
        except Exception as err:  # noqa: BLE001
            print(f"[telegram] 发送文本失败: {err}")
            return False

    def send_photo(self, image_path: Path, caption: str = "") -> bool:
        """发送单张实体照片（Best for 截图）。"""
        if not self.ready or not image_path.exists():
            return False
        try:
            boundary = "----trae" + str(int(time.time() * 1000))
            content_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
            fields = [("chat_id", self.chat_id)]
            if caption:
                fields.append(("caption", caption))
            body = build_multipart(fields, image_path.name, b"input", content_type, image_path.read_bytes(), boundary)
            req = urllib.request.Request(self._url("sendPhoto"), data=body, method="POST",
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                json.loads(resp.read().decode())
            return True
        except Exception as err:  # noqa: BLE001
            print(f"[telegram] 发送照片失败 {image_path.name}: {err}")
            return False

    def send_detailed_report(self, report: str, shot_paths: list[Path]) -> None:
        """发送详细文本报告；如有失败截图则附带发送。"""
        self.send_text(report)
        if shot_paths:
            # 只附带最多 5 张失败截图，避免消息超限
            for shot in shot_paths[:5]:
                self.send_photo(shot, caption="")


def build_multipart(fields: list[tuple], fname: str, ffield: bytes, fct: str, fdata: bytes, boundary: str) -> bytes:
    buf = io.BytesIO()
    CRLF = b"\r\n"
    for name, value in fields:
        buf.write(b"--" + boundary.encode() + CRLF)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode() + CRLF + CRLF)
        buf.write(str(value).encode() + CRLF)
    buf.write(b"--" + boundary.encode() + CRLF)
    buf.write(f'Content-Disposition: form-data; name="{ffield.decode()}"; filename="{fname}"'.encode() + CRLF)
    buf.write(f"Content-Type: {fct}".encode() + CRLF + CRLF)
    buf.write(fdata + CRLF)
    buf.write(b"--" + boundary.encode() + b"--" + CRLF)
    return buf.getvalue()