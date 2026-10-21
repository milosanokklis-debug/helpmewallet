import pytest

from authagent.auth import fill_login, is_authenticated, login_once
from authagent.fill import detect_captcha, new_creds, run_signup

CAPTCHA_FORM = """<form onsubmit="return false"><input name=email type=email><input type=password name=pw>
<div class="g-recaptcha" data-sitekey="x"></div><button>Sign in</button></form>"""
PLAIN_LOGIN = """<form onsubmit="return false"><label>Username<input name=username></label><input type=password name=pw>
<button>Log in</button></form>"""


@pytest.fixture(scope="module")
def ctxpage():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context()
        yield ctx, ctx.new_page()
        b.close()


def test_captcha_detected_and_untouched(ctxpage):
    _, page = ctxpage
    page.set_content(CAPTCHA_FORM + "<script>window.touched=0;document.querySelector('.g-recaptcha').onclick=()=>window.touched++</script>")
    assert detect_captcha(page)
    res = run_signup(page, new_creds())
    assert res["outcome"] == "captcha_detected"
    assert page.evaluate("window.touched") == 0
    assert page.locator("input[name=email]").input_value() == ""  # stopped before filling anything


def test_captcha_text_variant(ctxpage):
    _, page = ctxpage
    page.set_content("<p>Please verify you are human</p><form><input type=password></form>")
    assert detect_captcha(page)


def test_no_captcha_on_plain_form(ctxpage):
    _, page = ctxpage
    page.set_content(PLAIN_LOGIN)
    assert detect_captcha(page) is None


def test_login_fill_uses_stored_creds_verbatim(ctxpage):
    _, page = ctxpage
    page.set_content(PLAIN_LOGIN)
    c = {"TEST_EMAIL": "a@b.test", "TEST_PASSWORD": "Pw-1234567", "TEST_USERNAME": "agent_ab12"}
    roles, clicked = fill_login(page, c)
    assert clicked and roles == ["identifier:username", "password"]
    assert page.locator("input[name=username]").input_value() == "agent_ab12"
    assert page.locator("input[name=pw]").input_value() == "Pw-1234567"


def test_login_stops_on_captcha(ctxpage):
    ctx, page = ctxpage
    ctx.route("http://localhost:9/login", lambda r: r.fulfill(body=CAPTCHA_FORM, content_type="text/html"))
    r = login_once(page, ctx, "http://localhost:9/login", {"TEST_EMAIL": "a@b.test", "TEST_PASSWORD": "x", "TEST_USERNAME": "u"})
    assert not r["ok"] and r["reason"].startswith("captcha_detected")
    assert page.locator("input[name=email]").input_value() == ""


def test_success_needs_two_signals():
    assert not is_authenticated({"logout_control": False, "left_login_page": True, "browser_state_set": False, "me_user": False})
    assert is_authenticated({"logout_control": True, "left_login_page": False, "browser_state_set": False, "me_user": True})
