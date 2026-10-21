"""The single allowlist gate. Call check_url() before touching any site."""
from pathlib import Path
from urllib.parse import urlsplit

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "allowlist.yaml"


class HostRefused(Exception):
    """Raised when a URL's host is not on the allowlist (or cannot be verified)."""


def load_allowlist(path=DEFAULT_PATH):
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        entries = list(data.get("defaults") or []) + list(data.get("user_hosts") or [])
    except Exception as e:  # fail closed
        raise HostRefused(f"cannot load allowlist {path}: {e}") from None
    return [str(e).strip().lower().rstrip(".") for e in entries if str(e).strip()]


def _matches(host, pattern):
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and len(host) > len(pattern) - 1
    return host == pattern


def check_url(url, allowlist=None):
    """Return the normalized host if allowed; raise HostRefused otherwise."""
    try:
        parts = urlsplit(str(url).strip())
        host = parts.hostname  # strips userinfo/port, lowercases
    except ValueError:
        raise HostRefused(f"unparseable URL: {url!r}") from None
    if parts.scheme not in ("http", "https") or not host:
        raise HostRefused(f"refused: not an http(s) URL with a host: {url!r}")
    host = host.rstrip(".")
    patterns = load_allowlist() if allowlist is None else [p.lower() for p in allowlist]
    if not any(_matches(host, p) for p in patterns):
        raise HostRefused(f"refused: host {host!r} is not on the allowlist")
    return host
