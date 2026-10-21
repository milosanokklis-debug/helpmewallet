"""Allowlist-gated, same-origin Playwright crawler producing a classified site map."""
import json
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from .allowlist import HostRefused, check_url
from .classify import classify_form
from .secrets import redact, safe_print

CACHE_DIR = Path(__file__).resolve().parent.parent / "runs"

# Runs in the rendered page. Never reads field values.
EXTRACT_JS = """() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const txt = e => (e.innerText || e.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
  const labelOf = i => {
    let l = i.labels && i.labels[0] ? i.labels[0].innerText : '';
    if (!l && i.getAttribute('aria-labelledby')) {
      const r = document.getElementById(i.getAttribute('aria-labelledby')); l = r ? r.innerText : '';
    }
    return l.trim().slice(0, 80);
  };
  const field = i => ({type: (i.getAttribute('type') || (i.tagName === 'TEXTAREA' ? 'textarea' : 'text')).toLowerCase(),
    name: i.name || null, id: i.id || null, autocomplete: i.getAttribute('autocomplete'),
    aria_label: i.getAttribute('aria-label'), label: labelOf(i), placeholder: i.getAttribute('placeholder')});
  const fieldsIn = root => [...root.querySelectorAll('input,select,textarea')]
    .filter(i => !['hidden','submit','button'].includes(i.type) && vis(i)).map(field);
  const btns = root => [...root.querySelectorAll('button,[role=button],input[type=submit]')].filter(vis).map(txt).filter(Boolean);
  const heads = root => [...root.querySelectorAll('h1,h2,h3,legend,label,a')].map(txt).join(' ').slice(0, 400);
  const forms = [...document.forms].filter(vis).map(f => ({
    action: f.getAttribute('action'), aria_label: f.getAttribute('aria-label'), fields: fieldsIn(f), buttons: btns(f),
    text: heads(f)}));
  if (!forms.length) {  // SPA pages often skip <form>; treat visible inputs as one pseudo-form
    const fields = fieldsIn(document.body);
    if (fields.length) forms.push({action: null, aria_label: null, fields, buttons: btns(document.body),
      text: heads(document.body), pseudo: true});
  }
  return {title: document.title, heading: (document.querySelector('h1,h2') || {}).innerText || '',
    text_len: document.body.innerText.length,
    links: [...document.querySelectorAll('a[href]')].map(a => a.href),
    buttons: btns(document.body), forms};
}"""


def _norm(url):
    p = urlsplit(url)
    # shortcut: query/fragment dropped so tokens never reach the map; query-only routes are not distinguished
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", ""))


def _origin(url):
    p = urlsplit(url)
    return (p.scheme, p.netloc.lower())


def guard_context(context, start_url, stats):
    """Every request (navigation, redirect, subresource) must pass check_url; cross-origin navigations are blocked."""
    origin = _origin(start_url)

    def handler(route):
        req = route.request
        u = req.url
        if urlsplit(u).scheme in ("data", "blob", "about"):
            return route.continue_()
        try:
            check_url(u)
            if req.is_navigation_request() and _origin(u) != origin:
                raise HostRefused("cross-origin navigation")
        except HostRefused:
            stats["blocked"] += 1
            return route.abort()
        return route.continue_()

    context.route("**/*", handler)


def extract_page(page):
    data = page.evaluate(EXTRACT_JS)
    for f in data["forms"]:
        f["classification"] = classify_form(f, page.url)
    return data


def crawl(start_url, depth=2, max_pages=25, headless=True):
    from playwright.sync_api import sync_playwright

    check_url(start_url)
    origin = _origin(start_url)
    stats = {"blocked": 0}
    pages = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context()
        guard_context(ctx, start_url, stats)
        page = ctx.new_page()
        queue, seen = deque([(_norm(start_url), 0)]), {_norm(start_url)}
        while queue and len(pages) < max_pages:
            url, d = queue.popleft()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass  # shortcut: busy SPAs (HMR sockets) may never idle; proceed with what rendered
                data = extract_page(page)
            except Exception as e:
                pages[url] = {"error": redact(str(e).splitlines()[0][:120])}
                continue
            data["http_status"] = resp.status if resp else None  # informational only, never trusted
            data["final_path"] = urlsplit(_norm(page.url)).path
            links = sorted({_norm(urljoin(page.url, h)) for h in data["links"] if _origin(urljoin(page.url, h)) == origin})
            data["links"] = links
            pages[url] = data
            if d < depth:
                for l in links:
                    if l not in seen:
                        seen.add(l)
                        queue.append((l, d + 1))
        browser.close()
    return {"host": urlsplit(start_url).netloc, "pages": pages, "blocked_requests": stats["blocked"]}


def save_and_diff(sitemap):
    """Cache per host; return what changed versus the previous cached run (re-validation)."""
    CACHE_DIR.mkdir(exist_ok=True)
    f = CACHE_DIR / ("sitemap-" + sitemap["host"].replace(":", "_") + ".json")
    diff = {"previous": False}
    if f.exists():
        old = json.loads(f.read_text(encoding="utf-8")).get("pages", {})
        new = sitemap["pages"]

        def kinds(pg):
            return sorted(x["classification"]["kind"] for p in pg.values() for x in p.get("forms", []))

        diff = {"previous": True, "added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
                "forms_changed": kinds(old) != kinds(new)}
    if any("error" in p for p in sitemap["pages"].values()):
        diff["cache_kept"] = "run had errors; previous cache not overwritten"
    else:
        f.write_text(json.dumps(sitemap, indent=1), encoding="utf-8")
    return diff


def report(sitemap, diff):
    safe_print(f"host={sitemap['host']} pages={len(sitemap['pages'])} blocked_requests={sitemap['blocked_requests']}")
    for url, p in sitemap["pages"].items():
        path = urlsplit(url).path
        if "error" in p:
            safe_print(f"  {path}: ERROR {p['error']}")
            continue
        safe_print(f"  {path} (final {p['final_path']}) title={p['title']!r} links={len(p['links'])} buttons={len(p['buttons'])}")
        for f in p["forms"]:
            c = f["classification"]
            names = [f"{x['type']}({x['name'] or x['id']})" for x in f["fields"]]
            safe_print(f"    form -> {c['kind'].upper()} (signup={c['signup_score']} login={c['login_score']}) fields={names}")
    safe_print("revalidation:", json.dumps(diff))
