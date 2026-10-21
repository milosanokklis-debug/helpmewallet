"""Credential generation (written only to gitignored .env.test) and log redaction."""
import re
import secrets as _s
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env.test"
MASK = "[REDACTED]"
_known = set()
# key=value / header-style secrets, including cookies
_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization|cookie|set-cookie)\b(\s*[:=]\s*)([^\r\n]*)"
)


def register_secret(value):
    if value:
        _known.add(str(value))


def redact(text):
    """Mask registered secret values and any password/token/cookie key=value pairs."""
    text = str(text)
    for v in sorted(_known, key=len, reverse=True):
        text = text.replace(v, MASK)
    return _PATTERN.sub(lambda m: m.group(1) + m.group(2) + MASK, text)


def safe_print(*args):
    print(redact(" ".join(map(str, args))))


def generate_creds(domain="authagent.test"):
    return {"TEST_EMAIL": f"agent-{_s.token_hex(4)}@{domain}", "TEST_PASSWORD": _s.token_urlsafe(18)}


def write_env_seed(creds=None, path=ENV_PATH):
    """Write creds to .env.test only; registers them for redaction. Refuses any other filename."""
    path = Path(path)
    if path.name != ".env.test":
        raise ValueError("credentials may only be written to .env.test")
    creds = creds or generate_creds()
    path.write_text("".join(f"{k}={v}\n" for k, v in creds.items()), encoding="utf-8")
    for v in creds.values():
        register_secret(v)
    return path
