import pytest

from authagent.allowlist import HostRefused, check_url
from authagent import secrets as sec


@pytest.mark.parametrize("u", ["http://localhost:3000/x", "https://127.0.0.1/", "https://app.test/login", "http://LOCALHOST"])
def test_allowed(u):
    assert check_url(u)


@pytest.mark.parametrize("u", [
    "https://example.com", "http://test", "https://evil.com/?a=localhost", "http://localhost@evil.com/",
    "https://localhost.evil.com", "https://eviltest", "ftp://localhost", "localhost", "", "http://evil.com#.test",
])
def test_refused(u):
    with pytest.raises(HostRefused):
        check_url(u)


def test_missing_allowlist_fails_closed(tmp_path):
    from authagent.allowlist import load_allowlist
    with pytest.raises(HostRefused):
        load_allowlist(tmp_path / "nope.yaml")


def test_redaction():
    sec.register_secret("s3cr3tVALUE")
    out = sec.redact("login with s3cr3tVALUE; Cookie: sid=abc123; password=hunter2")
    assert "s3cr3tVALUE" not in out and "abc123" not in out and "hunter2" not in out


def test_env_seed_only_env_test(tmp_path):
    with pytest.raises(ValueError):
        sec.write_env_seed(path=tmp_path / "creds.txt")
    p = sec.write_env_seed(path=tmp_path / ".env.test")
    pw = dict(l.split("=", 1) for l in p.read_text().splitlines())["TEST_PASSWORD"]
    assert pw not in sec.redact(f"pw is {pw}")
