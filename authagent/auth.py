"""Login / success-check / logout / re-login and the full e2e chain. Output carries no secrets."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import secrets as sec
from .allowlist import check_url
from .fill import CAPTCHA_FIELD, FIELDS_JS, detect_captcha, map_field, signup

LOGOUT = re.compile(r"log[\s-]?out|sign[\s-]?out", re.I)
LOGINBTN = re.compile(r"log[\s-]?in|sign[\s-]?in|continue|submit", re.I)
NOT_LOGIN_BTN = re.compile(r"google|github|facebook|apple|twitter|microsoft|forgot|reset|register|sign[\s-]?up|create", re.I)
ME_PROBES = ("/api/auth/me", "/api/me", "/me")  # shortcut: common session-probe paths, not exhaustive
LOGOUT_PROBES = ("/api/auth/logout", "/logout", "/signout")
FILL_TIMEOUT = 5000  # ms; a short timeout keeps failures fast (error text is redacted anyway)
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "runs"
ME_JS = """async (p) => { try { const r = await fetch(p, {credentials: 'include'}); if (!r.ok) return null;
  const j = await r.json(); return j && typeof j === 'object' ? j : null; } catch (e) { return null; } }"""
POST_JS = """async (p) => { try { return (await fetch(p, {method: 'POST', credentials: 'include'})).status; } catch (e) { return 0; } }"""


def failure_reason(e):
    """Type name plus the redacted first line only. Never a traceback (Playwright errors embed filled values)."""
    return f"{type(e).__name__}: {sec.redact(str(e).splitlines()[0] if str(e) else '')[:120]}"


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


def _cookie_hashes(ctx):
    """name -> short hash of value. Values are never printed or stored."""
    return {c["name"]: hashlib.sha256(c["value"].encode()).hexdigest()[:12] for c in ctx.cookies()}


def session_signals(page, ctx, base_cookies, login_path):
    """Evidence of an authenticated session. Names/booleans only, never values."""
    return {"logout_control": _logout_control(page) is not None,
            "me_user": _me(page),
            "left_login_page": urlsplit(page.url).path.rstrip("/") != login_path.rstrip("/"),
            "browser_state_set": bool(set(_cookie_hashes(ctx)) - base_cookies)}


def is_authenticated(sig):
    """Needs a STRONG, server-confirmed signal (logout control or /me user) plus one corroborating signal."""
    return bool(sig["logout_control"] or sig["me_user"]) and sum(sig.values()) >= 2


def fill_login(page, creds, on_submit=None):
    """Fill the login form with the stored creds verbatim. Returns (roles, status): clicked | no_submit | captcha."""
    d = page.evaluate(FIELDS_JS)
    roles, first_id = [], True
    for f in d["fields"]:
        if CAPTCHA_FIELD.search(" ".join(str(f.get(k) or "") for k in ("name", "id", "aria_label", "label", "placeholder"))):
            continue  # never touch a captcha-like field
        role = map_field(f)
        loc = page.locator(f'[data-aa="{f["idx"]}"]')
        if f["type"] == "password":
            loc.fill(creds["TEST_PASSWORD"], timeout=FILL_TIMEOUT)
            roles.append("password")
        elif f["type"] != "checkbox" and role in ("email", "username", "other", "name", "first_name") and first_id:
            key = "TEST_EMAIL" if role == "email" or not creds.get("TEST_USERNAME") else "TEST_USERNAME"
            loc.fill(creds[key], timeout=FILL_TIMEOUT)
            first_id = False
            roles.append("identifier:" + ("email" if key == "TEST_EMAIL" else "username"))
    cands = [b for b in d["buttons"] if not NOT_LOGIN_BTN.search(b["text"])]
    btn = next((b for b in cands if LOGINBTN.search(b["text"])), next((b for b in cands if b["type"] == "submit"), None))
    if not btn:
        return roles, "no_submit"
    if detect_captcha(page):  # re-check immediately before the submit click
        return roles, "captcha"
    if on_submit:
        on_submit()
    page.locator(f'[data-aa="b{btn["idx"]}"]').click(timeout=FILL_TIMEOUT)
    return roles, "clicked"


def _settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass  # shortcut: SPAs with live sockets may never idle
    page.wait_for_timeout(600)


ACCOUNT_JS = r"""() => { const a = [...document.querySelectorAll('a[href]')].find(a => a.origin === location.origin &&
  /profile|account|settings|\/me\b/i.test(a.pathname + ' ' + a.innerText)); return a ? a.href : null; }"""


def capture_html(page, label, creds):
    """Save the redacted authenticated page HTML as a run artifact; return a small proof dict (never the HTML)."""
    html = page.content()
    red = sec.redact_html(html)
    host = re.sub(r"[^a-z0-9.-]", "_", urlsplit(page.url).netloc.lower())
    EVIDENCE_DIR.mkdir(exist_ok=True)
    path = EVIDENCE_DIR / f"e2e-{host}-{time.strftime('%Y%m%d-%H%M%S')}-{label}.html"
    path.write_text(red, encoding="utf-8")
    user = creds.get("TEST_USERNAME") or creds.get("TEST_EMAIL") or ""
    return {"path": f"runs/{path.name}", "title": sec.redact(page.title())[:80], "bytes": len(red),
            "authed_marker": {"logout_control": _logout_control(page) is not None, "username_visible": bool(user) and user in html},
            "no_leak": creds["TEST_PASSWORD"] not in red}


def capture_authenticated(page, label, creds):
    """Landing page, plus the account/profile page if one is linked. Same authenticated browser context."""
    out = {"landing": capture_html(page, label, creds)}
    try:
        acct = page.evaluate(ACCOUNT_JS)
        if acct and acct.rstrip("/") != page.url.rstrip("/"):
            check_url(acct)
            landing = page.url
            page.goto(acct, wait_until="domcontentloaded", timeout=15000)
            _settle(page)
            out["account"] = capture_html(page, label + "-account", creds)
            page.goto(landing, wait_until="domcontentloaded", timeout=15000)  # back to where logout is expected
            _settle(page)
    except Exception as e:
        out["account_error"] = failure_reason(e)
    return out


def login_once(page, ctx, login_url, creds, label="login"):
    """Navigate to the login page, submit stored creds, evaluate success signals. Never raises on page errors."""
    check_url(login_url)  # defence in depth: do not rely only on the caller's route guard
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
        _settle(page)
        cap = detect_captcha(page)
        if cap:
            return {"ok": False, "reason": f"captcha_detected ({cap}); stopped"}
        base = {}
        roles, status = fill_login(page, creds, on_submit=lambda: base.update(_cookie_hashes(ctx)))
        if status == "captcha":
            return {"ok": False, "reason": "captcha_detected; stopped", "roles": roles}
        if status != "clicked":
            return {"ok": False, "reason": status, "roles": roles}
        _settle(page)
        if detect_captcha(page):
            return {"ok": False, "reason": "captcha_detected after submit; stopped", "roles": roles}
        sig = session_signals(page, ctx, set(base), urlsplit(login_url).path)
        res = {"ok": is_authenticated(sig), "signals": sig, "roles": roles, "final_path": urlsplit(page.url).path}
        if res["ok"]:
            res["authenticated_html"] = capture_authenticated(page, label, creds)
        return res
    except Exception as e:  # Playwright text can embed filled values: report redacted first line only
        return {"ok": False, "reason": failure_reason(e)}


def logout(page, ctx, pre_cookies):
    """Click the logout control (fallback: POST to common paths). Needs positive evidence the session ended."""
    ctrl = _logout_control(page)
    via = "ui"
    try:
        if ctrl:
            ctrl.click(timeout=FILL_TIMEOUT)
        else:
            via = "post"
            if not any(200 <= page.evaluate(POST_JS, p) < 300 for p in LOGOUT_PROBES):
                return {"ok": False, "reason": "no_logout_path", "via": via}
            page.reload()
        _settle(page)
    except Exception as e:
        return {"ok": False, "reason": failure_reason(e), "via": via}
    now = _cookie_hashes(ctx)
    state_rotated = (not pre_cookies) or any(now.get(n) != h for n, h in pre_cookies.items())
    signals_gone = not _me(page) and _logout_control(page) is None
    return {"ok": signals_gone and state_rotated, "via": via, "signals_gone": signals_gone,
            "state_rotated": state_rotated}


def save_evidence(url, steps):
    """Persist the redacted step list to runs/e2e-<host>.json (runs/ is gitignored)."""
    EVIDENCE_DIR.mkdir(exist_ok=True)
    name = "e2e-" + re.sub(r"[^a-z0-9.-]", "_", urlsplit(url).netloc.lower()) + ".json"
    (EVIDENCE_DIR / name).write_text(sec.redact(json.dumps(steps, indent=1)), encoding="utf-8")


def e2e(url, headless=True):
    """discovery -> signup -> login -> success check -> logout -> re-login. Never raises; no secrets in results."""
    steps = []
    try:
        _e2e(url, headless, steps)
    except Exception as e:
        steps.append({"step": "error", "pass": False, "reason": failure_reason(e)})
    try:
        save_evidence(url, steps)
    except Exception:
        pass  # shortcut: evidence file is best-effort
    return steps


def _e2e(url, headless, steps):
    from playwright.sync_api import sync_playwright

    from .crawl import crawl, guard_context

    check_url(url)

    def step(name, ok, **kw):
        steps.append({"step": name, "pass": bool(ok), **kw})
        return bool(ok)

    sm = crawl(url, depth=2, max_pages=25, headless=headless)
    forms = {urlsplit(u).path: f["classification"]["kind"] for u, p in sm["pages"].items() for f in p.get("forms", [])}
    login_url = next((u for u, p in sm["pages"].items() for f in p.get("forms", []) if f["classification"]["kind"] == "login"), None)
    if not step("discovery", login_url and "signup" in forms.values(), forms=forms, pages=len(sm["pages"])):
        return
    if sec.ENV_PATH.exists():  # re-runnable: reuse the stored account instead of failing with 409 on re-signup
        step("signup", True, skipped="existing .env.test creds reused (delete it to sign up a fresh account)")
    else:
        res = signup(url, headless=headless, sitemap=sm)
        if not step("signup", res.get("outcome") == "submitted", outcome=res.get("outcome"), target=res.get("target_path"),
                    post_statuses=res.get("post_statuses"), errors=res.get("errors")):
            return
    creds = sec.load_env_seed()  # registers values so redact() masks them
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=headless)
        try:
            ctx = b.new_context()  # fresh session: proves the stored creds work independent of the signup session
            guard_context(ctx, url, {"blocked": 0})
            page = ctx.new_page()
            r = login_once(page, ctx, login_url, creds)
            pre = _cookie_hashes(ctx)
            if step("login", r["ok"], **{k: v for k, v in r.items() if k != "ok"}):
                lo = logout(page, ctx, pre)
                if step("logout", lo["ok"], **{k: v for k, v in lo.items() if k != "ok"}):
                    r2 = login_once(page, ctx, login_url, creds, "relogin")
                    r2["fresh_session"] = r2["ok"] and _cookie_hashes(ctx) != pre
                    step("re_login", r2["ok"], **{k: v for k, v in r2.items() if k != "ok"})
        finally:
            b.close()


def report(steps):
    for s in steps:
        sec.safe_print(("PASS " if s["pass"] else "FAIL ") + json.dumps(s))
        for k, v in (s.get("authenticated_html") or {}).items():
            if isinstance(v, dict):
                sec.safe_print(f"  saved {v['path']}: authed marker={v['authed_marker']} no_leak={v['no_leak']}")
    return all(s["pass"] for s in steps)
