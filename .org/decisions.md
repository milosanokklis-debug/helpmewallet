# Architecture decisions

## 2026-10-21 Stack & layout
Python 3.12 + Playwright (chromium) + pytest for the auth-testing agent (repo convention, SPA rendering). Package `authagent/` installed as a module; CLI entry `python -m authagent run --url <url>`. Deps pinned in `requirements.txt` (stdlib + playwright, pyyaml, requests). Everything lives under the project root. The email-auth test site stays Node/Express to mirror the real target.

## 2026-10-21 Safety is the core, built first
The allowlist (`config/allowlist.yaml`, defaults localhost/127.0.0.1/*.test) is the single most important property: the agent REFUSES any host not on the allowlist, enforced in one chokepoint and covered by a unit test. CAPTCHA/bot-detection is never solved — on detection the run STOPS and reports the reason. Generated credentials live in a gitignored `.env.test`/seed and never appear in logs, stdout, or reports. `.gitignore` is committed in the very first ticket before any secret can be generated.

## 2026-10-21 Everything discovered at runtime
No hardcoded routes, selectors, or page structures. Discovery renders pages with Playwright (never trusts HTTP status, since the SPA returns 200 for every path) and classifies signup vs login vs other from visible text, ARIA roles/labels, input types & autocomplete, URL hints, and form shape (2 password fields => signup). Site map cached per host but always re-validated.

## 2026-10-21 Email verification
Primary provider = Mailpit in Docker (`docker-compose.yml`), polled via its REST API for the newest message to the generated address; extract verification link or OTP. Provider interface is pluggable (IMAP catch-all addable later, plus-addressing per run). Docker is DOWN on this machine now, so the email e2e must SKIP with a clear message when Mailpit is unreachable, never hang.

## 2026-10-21 Build order
Incremental: scaffold+safety -> discovery -> signup/form-fill -> login+success+logout+re-login -> email verification -> CLI+JSON report -> HTML report. Test site (Express+SMTP) built in parallel with the agent core since independent. Each agent stage is run against the live target localhost:8889 before moving on.

## 2026-10-21 UPDATE: Docker now UP
Coordinator confirmed Docker Desktop is running (`docker ps`, `docker compose version` work). The email-verification e2e must now ACTUALLY RUN, not skip: bring up Mailpit, start the email-auth test site, and run the full discovery->join/verify->signin->success flow extracting the link/OTP from Mailpit's REST API. The skip-cleanly fallback stays for when Docker is genuinely down, but must not trigger in this build. (DEV-005, DEV-008 ACs updated.)
