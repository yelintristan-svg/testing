"""Outbound mail transports.

DryRunMailer is the default and the only one used in this prototype: it
writes each message as an .eml file in the outbox so it can be opened in any
mail client and inspected. SmtpMailer exists so the wiring is clear, but it
refuses to run unless CRM_ALLOW_LIVE_SEND=true is set deliberately.
"""
from __future__ import annotations

import smtplib
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path


def build(sender_name: str, sender: str, to: str, subject: str, body: str, unsubscribe_url: str,
          reply_to: str | None = None, message_id_domain: str = "example.com") -> EmailMessage:
    # Long lines allowed so the List-Unsubscribe URL is never RFC 2047 encoded.
    msg = EmailMessage(policy=policy.SMTP.clone(max_line_length=998))
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=message_id_domain)
    if reply_to:
        msg["Reply-To"] = reply_to
    # RFC 8058 one-click unsubscribe. Gmail and Yahoo require it for bulk senders.
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)
    return msg


class DryRunMailer:
    live = False

    def __init__(self, outbox: Path):
        self.outbox = Path(outbox)
        self.outbox.mkdir(parents=True, exist_ok=True)

    def send(self, msg: EmailMessage, message_id: str) -> str:
        path = self.outbox / f"{message_id}.eml"
        path.write_bytes(bytes(msg))
        return str(path)


class SmtpMailer:
    live = True

    def __init__(self, host: str, port: int, user: str, password: str, allow_live_send: bool):
        if not allow_live_send:
            raise RuntimeError("Live sending is disabled. Set CRM_ALLOW_LIVE_SEND=true only when you mean it.")
        self.host, self.port, self.user, self.password = host, port, user, password

    def send(self, msg: EmailMessage, message_id: str) -> str:
        with smtplib.SMTP(self.host, self.port) as s:
            s.starttls()
            s.login(self.user, self.password)
            s.send_message(msg)
        return msg["Message-ID"]


def from_settings(settings):
    if settings.mailer == "dryrun":
        return DryRunMailer(settings.outbox_dir)
    if settings.mailer == "smtp":
        import os
        return SmtpMailer(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)),
                          os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"], settings.allow_live_send)
    raise ValueError(f"unknown mailer {settings.mailer}")
