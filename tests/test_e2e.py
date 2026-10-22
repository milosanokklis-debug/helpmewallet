"""Live end-to-end runs through the real CLI. Seed + reports go to tmp dirs: the real .env.test is never touched."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, port_open

pytestmark = pytest.mark.e2e
STEPS = ["allowlist", "discovery", "signup", "email_verify", "login", "logout", "re_login"]


def run_cli(url, tmp_path):
    env = dict(os.environ, AUTHAGENT_ENV_FILE=str(tmp_path / ".env.test"), AUTHAGENT_RUNS_DIR=str(tmp_path / "runs"))
    r = subprocess.run([sys.executable, "-m", "authagent", "run", "--url", url], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=170)
    report = json.load(open(next((tmp_path / "runs").glob("run-*/report.json")), encoding="utf-8"))
    seed = (tmp_path / ".env.test").read_text(encoding="utf-8") if (tmp_path / ".env.test").exists() else ""
    secrets = [l.split("=", 1)[1] for l in seed.splitlines() if "=" in l and not l.startswith("TEST_SITE")]
    return r, report, secrets


def assert_clean(r, report, secrets, tmp_path):
    blob = r.stdout + r.stderr + json.dumps(report)
    blob += "".join(p.read_text(encoding="utf-8", errors="ignore") for p in (tmp_path / "runs").rglob("*.html"))
    assert secrets and not any(s in blob for s in secrets), "a credential leaked into stdout, report or saved HTML"


def test_8889_full_flow(tmp_path):
    if not port_open(8889):
        pytest.skip("target http://localhost:8889 is not running - skipping the 8889 e2e")
    r, rep, secrets = run_cli("http://localhost:8889", tmp_path)
    assert r.returncode == 0, r.stdout[-500:]
    assert [s["step"] for s in rep["steps"]] == STEPS and all(s["pass"] for s in rep["steps"])
    assert {x["path"]: x["form"] for x in rep["routes"]} == {"/login": "login", "/register": "signup"}
    assert rep["status"] == "passed" and rep["artifacts"]
    assert_clean(r, rep, secrets, tmp_path)


def test_email_auth_site_join_verify_signin(site_email, tmp_path):
    """Starts at /join (the site root 404s): /join -> poll Mailpit -> /verify -> /signin -> authenticated."""
    r, rep, secrets = run_cli(site_email + "/join", tmp_path)
    assert r.returncode == 0, r.stdout[-500:]
    by = {s["step"]: s for s in rep["steps"]}
    assert all(s["pass"] for s in rep["steps"]) and rep["status"] == "passed"
    assert by["email_verify"]["required"] is True and by["email_verify"]["method"] in ("otp", "link")
    assert {x["path"]: x["form"] for x in rep["routes"]} == {"/join": "signup", "/signin": "login"}
    assert_clean(r, rep, secrets, tmp_path)
