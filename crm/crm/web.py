"""Minimal web endpoints: unsubscribe page and Calendly webhook receiver.

Standard library only (wsgiref), so it runs anywhere. Put it behind HTTPS
(e.g. Caddy or a hosting platform) before pointing real links at it.
"""
from __future__ import annotations

import html
import json
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from . import booking, compliance, db
from .settings import Settings


def make_app(settings: Settings):
    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET")
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ["wsgi.input"].read(length) if length else b""
        conn = db.connect(settings.db_path)
        try:
            if path == "/u":
                email = (qs.get("e") or [""])[0]
                token = (qs.get("t") or [""])[0]
                if not compliance.verify_unsubscribe(settings.unsubscribe_secret, email, token):
                    return _resp(start_response, "400 Bad Request", "That unsubscribe link isn't valid.")
                if method == "POST":  # RFC 8058 one-click, or the button below
                    compliance.suppress(conn, email, "unsubscribe", actor="link")
                    conn.commit()
                    return _resp(start_response, "200 OK",
                                 "You're unsubscribed. None of our brands will email you again.")
                safe = html.escape(email)
                form = (f"<p>Stop all emails to {safe} from our group?</p>"
                        f"<form method='post'><button>Unsubscribe</button></form>")
                return _resp(start_response, "200 OK", form, html_body=True)
            if path == "/webhooks/calendly" and method == "POST":
                sig = environ.get("HTTP_CALENDLY_WEBHOOK_SIGNATURE", "")
                if not booking.verify_signature(settings.calendly_signing_key, sig, body):
                    return _resp(start_response, "401 Unauthorized", "bad signature")
                result = booking.handle_webhook(conn, settings, json.loads(body), settings.outbox_dir)
                return _resp(start_response, "200 OK", json.dumps(result), ctype="application/json")
            return _resp(start_response, "404 Not Found", "not found")
        finally:
            conn.close()
    return app


def _resp(start_response, status, text, html_body=False, ctype=None):
    if html_body:
        payload = f"<!doctype html><meta charset=utf-8><title>Email preferences</title><body>{text}</body>".encode()
        ctype = "text/html; charset=utf-8"
    else:
        payload = text.encode()
        ctype = ctype or "text/plain; charset=utf-8"
    start_response(status, [("Content-Type", ctype), ("Content-Length", str(len(payload)))])
    return [payload]


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 8080) -> None:
    with make_server(host, port, make_app(settings)) as srv:
        print(f"listening on http://{host}:{port}")
        srv.serve_forever()
