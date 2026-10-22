import smtplib
import time
from email.message import EmailMessage

import pytest

from authagent.mail import MailpitProvider, extract_link, extract_otp, html_to_text

HTML = """<p>Your verification code is <b>482913</b></p><p>Or <a href="http://localhost:8890/verify?token=abc123def">click here to verify</a>.</p>
<a href="https://evil.example.com/verify?token=zzz">phish</a><a href="http://localhost:8890/unsubscribe?u=1">unsubscribe</a>"""
TEXT = "Your verification code is 482913\n\nOr open this link: http://localhost:8890/verify?token=abc123def\n"


def test_link_from_html_and_text():
    assert extract_link("", HTML) == "http://localhost:8890/verify?token=abc123def"
    assert extract_link(TEXT, "") == "http://localhost:8890/verify?token=abc123def"


def test_link_never_returns_non_allowlisted_host():
    assert extract_link("", '<a href="https://evil.example.com/verify?token=zzz">x</a>') is None
    assert extract_link("go to https://evil.example.com/confirm now", "") is None


def test_link_prefers_verification_keywords():
    t = "Welcome http://localhost:3000/home then confirm: http://localhost:3000/confirm?k=1"
    assert extract_link(t, "") == "http://localhost:3000/confirm?k=1"


@pytest.mark.parametrize("text,html,code", [
    (TEXT, "", "482913"), ("", HTML, "482913"),
    ("Use OTP: 7741 to continue", "", "7741"),
    ("Hi! Sent 2026-10-21. Your one-time passcode is 123456.", "", "123456"),
    ("Order 99 shipped. Ref 654321 attached", "", "654321"),
])
def test_otp(text, html, code):
    assert extract_otp(text, html) == code


def test_no_otp():
    assert extract_otp("Hello, no codes here", "<p>hi</p>") is None


def test_html_to_text():
    assert "482913" in html_to_text(HTML) and "<" not in html_to_text(HTML)


def test_unreachable_provider_is_fast_and_clean():
    p = MailpitProvider("http://localhost:1")  # nothing listens
    t = time.monotonic()
    assert not p.reachable() and p.latest_message("x@authagent.test", timeout=1.5, interval=0.3) is None
    assert time.monotonic() - t < 15


def test_real_mailpit_roundtrip():
    """Integration: send via SMTP :1025, fetch via the REST API :8025 (not mocked)."""
    p = MailpitProvider()
    if not p.reachable():
        pytest.skip("Mailpit unreachable at localhost:8025 (run `docker compose up -d`)")
    to = f"it-{time.time_ns()}@authagent.test"
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "site@authagent.test", to, "Confirm"
    m.set_content(TEXT)
    m.add_alternative(HTML, subtype="html")
    with smtplib.SMTP("localhost", 1025, timeout=5) as s:
        s.send_message(m)
    got = p.latest_message(to, timeout=10)
    assert got and extract_otp(got["text"], got["html"]) == "482913"
    assert extract_link(got["text"], got["html"]) == "http://localhost:8890/verify?token=abc123def"


# ---- complete_verification (DEV-005 r1) ----
from authagent import auth as A
from authagent import secrets as S
from authagent.crawl import guard_context
from authagent.fill import new_creds
from authagent.mail import EmailProvider, complete_verification


class FakeProvider(EmailProvider):
    """Proves the interface is pluggable and lets tests control the mailbox."""

    def __init__(self, msg=None, up=True):
        self.msg, self.up = msg, up

    def reachable(self):
        return self.up

    def latest_message(self, to_address, timeout=30, interval=1.0):
        return self.msg


VERIFY_PAGE = "<h1>Check your email</h1><p>Enter the code we emailed you.</p>"
OTP_PAGE = VERIFY_PAGE + """<form onsubmit="return false"><input name=code autocomplete=one-time-code>
<button type=button id=v>Verify</button></form><script>v.onclick=()=>{ if (document.querySelector('[name=code]').value === '482913')
document.body.innerHTML='<p>Email verified</p>' }</script>"""


@pytest.fixture()
def pg():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context()
        guard_context(ctx, "http://localhost:8123/", {"blocked": 0})
        page = ctx.new_page()
        requested = []
        page.on("request", lambda r: requested.append(r.url))
        page.requested = requested
        yield ctx, page
        b.close()


def _serve(ctx, pages):
    def make(body):
        return lambda route: route.fulfill(body=body, content_type="text/html")

    for path, body in pages.items():
        ctx.route(f"http://localhost:8123{path}", make(body))


def test_otp_branch(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": OTP_PAGE})
    page.goto("http://localhost:8123/verify")
    r = complete_verification(page, FakeProvider({"subject": "s", "text": TEXT, "html": ""}), new_creds(), timeout=1)
    assert r == {"ok": True, "required": True, "method": "otp"}


def test_link_branch(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": VERIFY_PAGE, "/go*": "<p>Email verified</p>"})
    page.goto("http://localhost:8123/verify")
    msg = {"subject": "s", "text": "Open http://localhost:8123/go?token=abcdef123456 to confirm", "html": ""}
    r = complete_verification(page, FakeProvider(msg), new_creds(), timeout=1)
    assert r == {"ok": True, "required": True, "method": "link"}
    assert S.redact("x abcdef123456 y") == "x [REDACTED] y"  # link token registered right after extraction


def test_off_allowlist_link_only_never_navigates(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": VERIFY_PAGE})
    page.goto("http://localhost:8123/verify")
    msg = {"subject": "s", "text": "", "html": '<a href="https://evil.example.com/verify?token=zzzzzz1">verify</a>'}
    r = complete_verification(page, FakeProvider(msg), new_creds(), timeout=1)
    assert not r["ok"] and r["reason"] == "no_link_or_code_in_email"
    assert not any("evil.example.com" in u for u in page.requested)


def test_provider_unreachable_is_a_skip(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": VERIFY_PAGE})
    page.goto("http://localhost:8123/verify")
    r = complete_verification(page, FakeProvider(up=False), new_creds())
    assert r["skipped"] and not r["ok"] and "unreachable" in r["reason"]


def test_captcha_stops_verification(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": VERIFY_PAGE + '<div class="g-recaptcha"></div>'})
    page.goto("http://localhost:8123/verify")
    r = complete_verification(page, FakeProvider({"subject": "s", "text": TEXT, "html": ""}), new_creds(), timeout=1)
    assert not r["ok"] and r["reason"].startswith("captcha_detected")


def test_no_email_and_not_required(pg):
    ctx, page = pg
    _serve(ctx, {"/verify": VERIFY_PAGE, "/done": "<p>Welcome</p>"})
    page.goto("http://localhost:8123/verify")
    assert complete_verification(page, FakeProvider(None), new_creds(), timeout=1)["reason"] == "no_email_received"
    page.goto("http://localhost:8123/done")
    assert complete_verification(page, FakeProvider(None), new_creds()) == {"ok": True, "required": False}


def test_email_step_reports_skip_not_failure(monkeypatch):
    """Mailpit down -> email_verify is a non-failing SKIP and the chain stops with a clear message."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import authagent.mail as M

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(VERIFY_PAGE.encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(M, "MailpitProvider", lambda: FakeProvider(up=False))
    steps = []
    base = f"http://localhost:{srv.server_port}/"
    cont = A._email_step(base, {"final_path": "/verify"}, new_creds(), True,
                         lambda name, ok, **kw: steps.append({"step": name, "pass": bool(ok), **kw}) or bool(ok))
    srv.shutdown()
    assert cont is False and steps[0]["pass"] is True and "Mailpit unreachable" in steps[0]["skipped"]


def test_live_site_otp_and_link_with_real_mailpit():
    """Live: sign up on the 8890 email-auth site, verify via real Mailpit with BOTH methods. Skips if either is down."""
    import requests
    p = MailpitProvider()
    if not p.reachable():
        pytest.skip("Mailpit unreachable - skipping email verification (docker compose up -d)")
    try:
        requests.get("http://localhost:8890/join", timeout=2)
    except requests.RequestException:
        pytest.skip("testsite-email not running on :8890 (cd testsite-email && SMTP_PORT=1025 npm start)")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for prefer in ("otp", "link"):
            c = new_creds()
            ctx = b.new_context()
            guard_context(ctx, "http://localhost:8890/", {"blocked": 0})
            page = ctx.new_page()
            page.goto("http://localhost:8890/join")
            page.fill("#email", c["TEST_EMAIL"]); page.fill("#password", c["TEST_PASSWORD"]); page.click("button")
            page.wait_for_load_state()
            r = complete_verification(page, p, c, prefer=prefer)
            assert r["ok"] and r["method"] == prefer
            ctx.close()
        b.close()
