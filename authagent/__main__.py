import argparse

p = argparse.ArgumentParser(prog="authagent", description="Authorized auth-flow testing agent (allowlist-gated).")
p.add_argument("--check-url", metavar="URL", help="verify URL passes the allowlist")
a = p.parse_args()
if a.check_url:
    from .allowlist import HostRefused, check_url
    try:
        print("allowed:", check_url(a.check_url))
    except HostRefused as e:
        raise SystemExit(str(e))
