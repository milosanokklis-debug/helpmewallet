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
