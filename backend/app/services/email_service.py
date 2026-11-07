"""Email service (P1.1) — SMTP with a test-mode sink.

Two transports:
  - SMTP:  real delivery via a configured SMTP host. Reads SMTP_HOST /
           SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM / SMTP_TLS.
  - Test:  writes every message to `runtime_data/outbox/` as .eml so QA
           and CI can assert on content without an MTA.

`send_password_reset`, `send_alert`, `send_welcome` etc. are thin wrappers
over `send_email` so product code never touches the transport directly.
"""

from __future__ import annotations

import logging
import smtplib
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str | None = None
    from_addr: str | None = None


class EmailTransport:
    """Transport interface — SMTP and Test implementations below."""

    def send(self, msg: EmailMessage) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


class TestTransport(EmailTransport):
    """Write to runtime_data/outbox/*.eml — QA-assertable sink."""

    def __init__(self, outbox_dir: str = "runtime_data/outbox") -> None:
        self.outbox_dir = Path(outbox_dir)

    def send(self, msg: EmailMessage) -> dict[str, Any]:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        fname = self.outbox_dir / f"{stamp}-{abs(hash(msg.subject)) % 100000}.eml"
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg.subject
        mime["From"] = msg.from_addr or "noreply@visionflywheel.local"
        mime["To"] = msg.to
        if msg.text_body:
            mime.attach(MIMEText(msg.text_body, "plain", "utf-8"))
        mime.attach(MIMEText(msg.html_body, "html", "utf-8"))
        fname.write_text(mime.as_string(), encoding="utf-8")
        logger.info("test email written: %s", fname)
        return {"status": "sent", "transport": "test", "file": str(fname)}


class SMTPTransport(EmailTransport):
    """Real delivery via the configured SMTP host."""

    def __init__(self, host: str, port: int, username: str | None, password: str | None,
                 from_addr: str, use_tls: bool, use_ssl: bool) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def send(self, msg: EmailMessage) -> dict[str, Any]:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg.subject
        mime["From"] = msg.from_addr or self.from_addr
        mime["To"] = msg.to
        if msg.text_body:
            mime.attach(MIMEText(msg.text_body, "plain", "utf-8"))
        mime.attach(MIMEText(msg.html_body, "html", "utf-8"))

        if self.use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            if self.use_tls:
                server.starttls()
        try:
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(mime["From"], [msg.to], mime.as_string())
        finally:
            server.quit()
        logger.info("smtp email sent: to=%s subject=%r", msg.to, msg.subject)
        return {"status": "sent", "transport": "smtp"}


def _build_transport() -> EmailTransport:
    """Pick SMTP when SMTP_HOST is configured; otherwise fall back to Test."""
    settings = get_settings()
    smtp_host = getattr(settings, "smtp_host", None) or ""
    if smtp_host:
        return SMTPTransport(
            host=smtp_host,
            port=int(getattr(settings, "smtp_port", 587) or 587),
            username=getattr(settings, "smtp_user", None),
            password=getattr(settings, "smtp_password", None),
            from_addr=getattr(settings, "smtp_from", "noreply@visionflywheel.local"),
            use_tls=bool(getattr(settings, "smtp_tls", True)),
            use_ssl=bool(getattr(settings, "smtp_ssl", False)),
        )
    return TestTransport()


def send_email(msg: EmailMessage) -> dict[str, Any]:
    """Single entry point — all product code calls this."""
    try:
        return _build_transport().send(msg)
    except Exception as exc:
        logger.exception("email send failed: to=%s subject=%r", msg.to, msg.subject)
        return {"status": "error", "transport": "unknown", "error": str(exc)}


# ---------- high-level templates ----------
_BASE_STYLE = (
    "font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;"
    "max-width:560px;margin:0 auto;padding:24px;color:#1f2937;"
)


def send_password_reset(to_email: str, reset_token: str, *, username: str, expires_minutes: int = 30) -> dict[str, Any]:
    reset_url = f"/reset-password?token={reset_token}"
    html = (
        f"<div style='{_BASE_STYLE}'>"
        f"<h2 style='margin-top:0'>重置你的 VisionFlywheel 密码</h2>"
        f"<p>你好 <strong>{username}</strong>，</p>"
        f"<p>我们收到你的密码重置请求。点击下面的按钮继续：</p>"
        f"<p style='margin:24px 0'>"
        f"<a href='{reset_url}' style='background:#4f46e5;color:#fff;padding:12px 24px;"
        f"border-radius:8px;text-decoration:none;display:inline-block'>重置密码</a>"
        f"</p>"
        f"<p style='color:#6b7280;font-size:13px'>"
        f"或者复制此链接到浏览器：<br>{reset_url}</p>"
        f"<p style='color:#6b7280;font-size:13px'>"
        f"链接有效期 {expires_minutes} 分钟。如果不是你发起的，请忽略本邮件。</p>"
        f"</div>"
    )
    text = (
        f"你好 {username}，\n\n"
        f"点击以下链接重置密码（{expires_minutes} 分钟内有效）：\n{reset_url}\n\n"
        f"如果不是你发起的，请忽略。\n"
    )
    return send_email(EmailMessage(to=to_email, subject="重置你的 VisionFlywheel 密码", html_body=html, text_body=text))


def send_welcome(to_email: str, *, username: str, role: str = "user") -> dict[str, Any]:
    html = (
        f"<div style='{_BASE_STYLE}'>"
        f"<h2 style='margin-top:0'>欢迎加入 VisionFlywheel</h2>"
        f"<p>账号 <strong>{username}</strong> 已创建（角色：{role}）。</p>"
        f"<p>登录后请尽快在「系统管理」页面修改初始密码。</p>"
        f"</div>"
    )
    return send_email(EmailMessage(to=to_email, subject="欢迎加入 VisionFlywheel", html_body=html, text_body=f"账号 {username} 已创建。"))


def send_alert(to_email: str, *, subject: str, body: str, severity: str = "warning") -> dict[str, Any]:
    color = {"info": "#1976d2", "warning": "#f57c00", "critical": "#c62828"}.get(severity, "#1976d2")
    html = (
        f"<div style='{_BASE_STYLE}'>"
        f"<div style='background:{color};color:#fff;padding:8px 12px;border-radius:6px;"
        f"display:inline-block;font-size:13px;margin-bottom:12px'>{severity.upper()}</div>"
        f"<h2 style='margin-top:0'>{subject}</h2>"
        f"<div style='white-space:pre-wrap'>{body}</div>"
        f"</div>"
    )
    return send_email(EmailMessage(to=to_email, subject=f"[VisionFlywheel] {subject}", html_body=html, text_body=body))
