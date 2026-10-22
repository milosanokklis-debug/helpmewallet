"""Render the (already redacted) per-run report.json into one self-contained HTML file."""
import base64
import html
import json
import sys
from pathlib import Path

E = html.escape
EMBED_MAX = 1_500_000  # shortcut: larger screenshots are not inlined, only named; raise if reports stay small
SKIP = {"step", "pass", "at", "duration_s", "authenticated_html"}

CSS = """
:root{--paper:#f6f5f1;--card:#fff;--ink:#1c1b19;--muted:#6b675f;--rule:#dcd8cf;--pass:#1f7a4d;--pass-bg:#e4f2ea;--fail:#b3261e;--fail-bg:#fbe7e5;
--sans:system-ui,-apple-system,"Segoe UI",sans-serif;--mono:ui-monospace,"Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box}html,body{overflow-x:clip}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans)}
main{max-width:860px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px;overflow-wrap:anywhere}h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:36px 0 12px}
.mono{font-family:var(--mono);font-size:13px}.muted{color:var(--muted)}
.head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
.badge{font-weight:700;letter-spacing:.04em;padding:6px 14px;border-radius:4px;border:1px solid}
.ok{color:var(--pass);background:var(--pass-bg);border-color:var(--pass)}.bad{color:var(--fail);background:var(--fail-bg);border-color:var(--fail)}
.banner{margin-top:20px;padding:12px 16px;border-left:4px solid var(--fail);background:var(--fail-bg);color:var(--fail)}
.banner b{display:block}.banner span{color:var(--ink);overflow-wrap:anywhere}
ol{list-style:none;margin:0;padding:0}
.step{background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--pass);border-radius:4px;padding:12px 16px;margin-bottom:10px}
.step.fail{border-left-color:var(--fail)}
.row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline}
.name{font-weight:600}.st{font-weight:700;font-size:12px;letter-spacing:.05em}
.st.ok,.st.bad{background:none;border:0}
dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;margin:8px 0 0;font-size:13px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
dl dl{margin:0}
.reason{margin-top:8px;color:var(--fail);overflow-wrap:anywhere}
figure{margin:12px 0 0}figcaption{font-size:12px;color:var(--muted);margin-top:4px;overflow-wrap:anywhere}
img{max-width:100%;height:auto;border:1px solid var(--rule);border-radius:2px;display:block}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--rule)}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--rule)}th{font-size:12px;color:var(--muted)}
ul{padding-left:18px;margin:0}li{overflow-wrap:anywhere}
a{color:#1a4fa0}a:focus-visible{outline:3px solid #1a4fa0;outline-offset:2px}
@media(max-width:700px){dl{grid-template-columns:1fr}dt{margin-top:4px}}
"""


def _val(v):
    if isinstance(v, dict):
        return "<dl>" + "".join(f"<dt>{E(str(k))}</dt><dd>{_val(x)}</dd>" for k, x in v.items()) + "</dl>"
    if isinstance(v, (list, tuple)):
        return E(", ".join(map(str, v))) if v else '<span class="muted">none</span>'
    if isinstance(v, bool):
        return "yes" if v else "no"
    return E(str(v))


def _resolve(p, base):
    """Report paths are relative to the project root; fall back to the run folder."""
    for c in (Path(p), base / p, base / Path(p).name):
        if c.is_file():
            return c
    return None


def _src(path, base):
    f = _resolve(path, base)
    if f and f.stat().st_size <= EMBED_MAX:
        return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
    return None


def _link(path, base):
    f = _resolve(path, base)
    return E(f.name) if f else None


def _evidence(auth, base):
    out = []
    for label, a in auth.items():
        if not isinstance(a, dict):
            continue
        meta = {k: v for k, v in a.items() if k not in ("path", "screenshot")}
        src = _src(a["screenshot"], base) if a.get("screenshot") else None
        href = _link(a["path"], base) if a.get("path") else None
        cap = f"<b>{E(str(label))}</b> " + (f'<a href="{href}">authenticated HTML</a>' if href else "")
        img = f'<img loading="lazy" src="{src}" alt="Screenshot: {E(str(label))}">' if src else ""
        out.append(f"<figure>{img}<figcaption>{cap}{_val(meta) if meta else ''}</figcaption></figure>")
    return "".join(out)


def _step(s, base):
    ok = bool(s.get("pass"))
    extra = {k: v for k, v in s.items() if k not in SKIP and v not in (None, "")}
    dur = f'{s["duration_s"]}s' if s.get("duration_s") is not None else ""
    reason = f'<div class="reason"><b>Reason:</b> {_val(s["reason"])}</div>' if s.get("reason") and not ok else ""
    mark = "✓ PASS" if ok else "✗ FAIL"
    return (f'<li class="step{"" if ok else " fail"}"><div class="row"><span class="name">{E(str(s.get("step", "?")))}</span>'
            f'<span class="st {"ok" if ok else "bad"}">{mark}</span></div>'
            f'<div class="muted mono">{E(str(s.get("at", "")))} &middot; {E(dur)}</div>'
            + reason + (_val(extra) if extra else "") + _evidence(s.get("authenticated_html") or {}, base) + "</li>")


def render_report(report, base_dir=None):
    """report: dict or path to report.json. base_dir: where screenshots are looked up (default: report's folder)."""
    if not isinstance(report, dict):
        p = Path(report)
        base_dir = base_dir or p.parent
        report = json.loads(p.read_text(encoding="utf-8"))
    base = Path(base_dir or ".")
    passed = report.get("status") == "passed"
    steps = report.get("steps") or []
    total = round(sum(s.get("duration_s") or 0 for s in steps), 2)
    fail = report.get("failure")
    banner = ""
    if fail:
        fstep = fail.get("step", "?") if isinstance(fail, dict) else "?"
        reason = fail.get("reason") if isinstance(fail, dict) else fail
        banner = (f'<div class="banner" role="alert"><b>Failed at step: {E(str(fstep))}</b>'
                  f'<span>{_val(reason) if reason else "No reason recorded"}</span></div>')
    routes = report.get("routes") or []
    rt = ('<div class="wrap"><table><tr><th>Path</th><th>Form</th></tr>' + "".join(
        f'<tr><td class="mono">{E(str(r.get("path", "")))}</td><td>{E(str(r.get("form", "")))}</td></tr>' for r in routes) + "</table></div>"
          if routes else '<p class="muted">No routes discovered.</p>')
    items = []
    for a in report.get("artifacts") or []:
        l = _link(a, base)
        items.append(f'<li class="mono"><a href="{l}">{l}</a></li>' if l else f'<li class="mono">{E(str(a))}</li>')
    al = "<h2>Artifacts</h2><ul>" + "".join(items) + "</ul>" if items else ""
    host = str(report.get("host") or report.get("url") or "Run report")
    badge = "✓ PASSED" if passed else "✗ " + E(str(report.get("status") or "failed").upper())
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Auth run: {E(host)} - {"PASSED" if passed else "FAILED"}</title><style>{CSS}</style></head><body><main>'
            f'<div class="head"><div><h1>{E(host)}</h1>'
            f'<div class="muted mono">{E(str(report.get("url", "")))}<br>{E(str(report.get("started_at", "")))} &rarr; {E(str(report.get("finished_at", "")))} &middot; {total}s in steps</div></div>'
            f'<div class="badge {"ok" if passed else "bad"}">{badge}</div></div>'
            f'{banner}<h2>Step timeline</h2><ol>{"".join(_step(s, base) for s in steps)}</ol>'
            f'<h2>Discovered routes</h2>{rt}{al}</main></body></html>')


def write_report_html(report_json):
    p = Path(report_json)
    out = p.with_name("report.html")
    out.write_text(render_report(p), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write_report_html(sys.argv[1]))
