import pytest

from authagent.classify import classify_form
from authagent.crawl import EXTRACT_JS, guard_context

SIGNUP = """<form><h2>Create your account</h2><label>Email <input type=email name=email autocomplete=email></label>
<label>Password <input type=password name=pw autocomplete=new-password></label>
<label>Confirm password <input type=password name=pw2></label><button>Join</button></form>"""
LOGIN = """<form><h2>Welcome back</h2><label>Email <input type=email name=email></label>
<label>Password <input type=password name=pw autocomplete=current-password></label>
<button>Sign in</button><a href=#>Forgot password?</a></form>"""
OTHER = """<form role=search aria-label="Site search"><input type=search name=q aria-label=Search><button>Go</button></form>"""
NOFORM_SIGNUP = """<div><h1>Register</h1><input name=u><input type=password name=a><input type=password name=b><button>Go</button></div>"""


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b.new_page()
        b.close()


def kind(page, html, url=""):
    page.set_content(html)
    forms = page.evaluate(EXTRACT_JS)["forms"]
    assert len(forms) == 1
    return classify_form(forms[0], url)["kind"]


def test_signup(page):
    assert kind(page, SIGNUP) == "signup"


def test_login(page):
    assert kind(page, LOGIN) == "login"


def test_other(page):
    assert kind(page, OTHER) == "other"


def test_pseudo_form_two_passwords_is_signup(page):
    assert kind(page, NOFORM_SIGNUP) == "signup"


def test_url_hints_break_ambiguity():
    f = {"fields": [{"type": "password"}], "buttons": ["Continue"], "text": ""}
    assert classify_form(f, "http://x.test/login")["kind"] == "login"
    assert classify_form({"fields": [{"type": "password"}, {"type": "password"}], "buttons": [], "text": ""}, "http://x.test/")["kind"] == "signup"


def test_guard_blocks_non_allowlisted_requests(page):
    ctx = page.context.browser.new_context()
    stats = {"blocked": 0}
    guard_context(ctx, "http://localhost:1/", stats)
    p = ctx.new_page()
    with pytest.raises(Exception):
        p.goto("http://example.com/", timeout=5000)
    assert stats["blocked"] >= 1
    ctx.close()
