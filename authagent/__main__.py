import argparse

p = argparse.ArgumentParser(prog="authagent", description="Authorized auth-flow testing agent (allowlist-gated).")
p.add_argument("--check-url", metavar="URL", help="verify URL passes the allowlist")
p.add_argument("--crawl", metavar="URL", help="crawl a site (allowlist-gated) and classify forms")
p.add_argument("--depth", type=int, default=2)
p.add_argument("--max-pages", type=int, default=25)
a = p.parse_args()
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
