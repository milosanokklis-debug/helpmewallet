"""Login / success-check / logout / re-login and the full e2e chain. Output carries no secrets."""
import json
import re
from urllib.parse import urlsplit

from . import secrets as sec
from .allowlist import check_url
from .fill import FIELDS_JS, detect_captcha, map_field, signup

LOGOUT = re.compile(r"log[\s-]?out|sign[\s-]?out", re.I)
LOGINBTN = re.compile(r"log[\s-]?in|sign[\s-]?in|continue|submit", re.I)
ME_PROBES = ("/api/auth/me", "/api/me", "/me")  # shortcut: common session-probe paths, not exhaustive
LOGOUT_PROBES = ("/api/auth/logout", "/logout", "/signout")
ME_JS = """async (p) => { try { const r = await fetch(p, {credentials: 'include'}); if (!r.ok) return null;
  const j = await r.json(); return j && typeof j === 'object' ? j : null; } catch (e) { return null; } }"""
POST_JS = """async (p) => { try { return (await fetch(p, {method: 'POST', credentials: 'include'})).status; } catch (e) { return 0; } }"""


def _logout_control(page):
    for role in ("button", "link"):
        loc = page.get_by_role(role, name=LOGOUT)
        if loc.count():
            return loc.first
    return None


def _me(page):
    for path in ME_PROBES:
        j = page.evaluate(ME_JS, path)
        if j and (j.get("user") or j.get("email") or j.get("username")):
            return True
    return False


def session_signals(page, ctx, base_cookies, login_path):
    """Independent evidence of an authenticated session. Names/booleans only, never values."""
    return {"logout_control": _logout_control(page) is not None,
            "left_login_page": urlsplit(page.url).path.rstrip("/") != login_path.rstrip("/"),
            "session_set": bool({c["name"] for c in ctx.cookies()} - base_cookies),
            "me_user": _me(page)}


def is_authenticated(sig):
    return sum(sig.values()) >= 2


def fill_login(page, creds):
    """Fill the login form with the stored creds verbatim (no value generation). Returns (roles, clicked)."""
    d = page.evaluate(FIELDS_JS)
    roles, first_id = [], True
    for f in d["fields"]:
        role = map_field(f)
        loc = page.locator(f'[data-aa="{f["idx"]}"]')
        if f["type"] == "password":
            loc.fill(creds["TEST_PASSWORD"])
            roles.append("password")
        elif f["type"] != "checkbox" and role in ("email", "username", "other", "name", "first_name") and first_id:
            key = "TEST_EMAIL" if role == "email" or not creds.get("TEST_USERNAME") else "TEST_USERNAME"
            loc.fill(creds[key])
            first_id = False
            roles.append("identifier:" + ("email" if key == "TEST_EMAIL" else "username"))
    btn = next((b for b in d["buttons"] if LOGINBTN.search(b["text"])), d["buttons"][0] if d["buttons"] else None)
    if not btn:
        return roles, False
    page.locator(f'[data-aa="b{btn["idx"]}"]').click()
    return roles, True


def _settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass  # shortcut: SPAs with live sockets may never idle
    page.wait_for_timeout(600)


def login_once(page, ctx, login_url, creds):
    """Navigate to the login page, submit stored creds, evaluate success signals."""
    base = {c["name"] for c in ctx.cookies()}
    page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
    _settle(page)
    cap = detect_captcha(page)
    if cap:
        return {"ok": False, "reason": f"captcha_detected ({cap}); stopped"}
    roles, clicked = fill_login(page, creds)
    if not clicked:
        return {"ok": False, "reason": "no_submit_button", "roles": roles}
    _settle(page)
    cap = detect_captcha(page)
    if cap:
        return {"ok": False, "reason": f"captcha_detected ({cap}); stopped"}
    sig = session_signals(page, ctx, base, urlsplit(login_url).path)
    return {"ok": is_authenticated(sig), "signals": sig, "roles": roles, "final_path": urlsplit(page.url).path}


def logout(page):
    """Click the logout control (fallback: POST to common logout paths). Confirms the session ended."""
    ctrl = _logout_control(page)
    via = "ui"
    if ctrl:
        ctrl.click()
    else:
        via = "post"
        for path in LOGOUT_PROBES:
            if 200 <= page.evaluate(POST_JS, path) < 300:
                break
        page.reload()
    _settle(page)
    return {"ok": not _me(page) and _logout_control(page) is None, "via": via}


def e2e(url, headless=True):
    """discovery -> signup -> login -> success check -> logout -> re-login. Returns step results (no secrets)."""
    from playwright.sync_api import sync_playwright

    from .crawl import crawl, guard_context

    check_url(url)
    steps = []

    def step(name, ok, **kw):
        steps.append({"step": name, "pass": bool(ok), **kw})
        return bool(ok)

    sm = crawl(url, depth=2, max_pages=25, headless=headless)
    forms = {urlsplit(u).path: f["classification"]["kind"] for u, p in sm["pages"].items() for f in p.get("forms", [])}
    login_url = next((u for u, p in sm["pages"].items() for f in p.get("forms", []) if f["classification"]["kind"] == "login"), None)
    if not step("discovery", login_url and "signup" in forms.values(), forms=forms, pages=len(sm["pages"])):
        return steps
    res = signup(url, headless=headless, sitemap=sm)
    if not step("signup", res.get("outcome") == "submitted", outcome=res.get("outcome"), target=res.get("target_path"),
                post_statuses=res.get("post_statuses"), errors=res.get("errors")):
        return steps
    creds = sec.load_env_seed()  # registers values so redact() masks them
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=headless)
        ctx = b.new_context()  # fresh session: proves the stored creds work independent of the signup session
        guard_context(ctx, url, {"blocked": 0})
        page = ctx.new_page()
        r = login_once(page, ctx, login_url, creds)
        if step("login", r["ok"], **{k: v for k, v in r.items() if k != "ok"}):
            lo = logout(page)
            if step("logout", lo["ok"], via=lo["via"]):
                r2 = login_once(page, ctx, login_url, creds)
                step("re_login", r2["ok"], **{k: v for k, v in r2.items() if k != "ok"})
        b.close()
    return steps


def report(steps):
    for s in steps:
        sec.safe_print(("PASS " if s["pass"] else "FAIL ") + json.dumps(s))
    return all(s["pass"] for s in steps)
