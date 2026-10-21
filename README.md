# authagent
Authorized-testing tool. Every site access goes through `authagent.allowlist.check_url`, which refuses hosts not in `config/allowlist.yaml`.

Setup: `pip install -r requirements.txt` then `playwright install chromium`.
Run: `python -m authagent --help`. Tests: `pytest`.
Generated creds go only to the gitignored `.env.test` (see `.env.test.example`).
