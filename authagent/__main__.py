import argparse

p = argparse.ArgumentParser(prog="authagent", description="Authorized auth-flow testing agent (allowlist-gated).")
p.add_argument("--check-url", metavar="URL", help="verify URL passes the allowlist")
p.add_argument("--crawl", metavar="URL", help="crawl a site (allowlist-gated) and classify forms")
p.add_argument("--depth", type=int, default=2)
p.add_argument("--max-pages", type=int, default=25)
p.add_argument("--signup", metavar="URL", help="discover and fill the signup form; creds go to .env.test only")
p.add_argument("--e2e", metavar="URL", help="discover, signup, login, logout, re-login (allowlist-gated)")
a = p.parse_args()
if a.e2e:
    from .allowlist import HostRefused
    from .auth import e2e, report
    try:
        raise SystemExit(0 if report(e2e(a.e2e)) else 1)
    except HostRefused as e:
        raise SystemExit(str(e))
if a.signup:
    import json
    from .allowlist import HostRefused
    from .fill import signup
    from .secrets import safe_print
    try:
        safe_print("signup result:", json.dumps(signup(a.signup)))
    except HostRefused as e:
        raise SystemExit(str(e))
if a.crawl:
    from .allowlist import HostRefused
    from .crawl import crawl, report, save_and_diff
    try:
        sm = crawl(a.crawl, a.depth, a.max_pages)
    except HostRefused as e:
        raise SystemExit(str(e))
    report(sm, save_and_diff(sm))
if a.check_url:
    from .allowlist import HostRefused, check_url
    try:
        print("allowed:", check_url(a.check_url))
    except HostRefused as e:
        raise SystemExit(str(e))
