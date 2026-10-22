# Tech debt

Collected from `shortcut:` comments (/ponytail-debt).

## DEV-001 (approved r2) deferred minors
- redact(): unquoted Cookie/Authorization values stop at , ; } so a SECOND cookie pair (e.g. `Cookie: sid=abc; x=y`) leaves `x=y` unmasked unless registered. Generated creds ARE registered so unaffected. Fix: make Cookie/Authorization swallow to end of line + add a two-cookie test.
- A user-added `*.co.uk` wildcard is accepted (deliberate owner action; doc-level only).
- 0600 file mode not enforced on Windows (file came out 0o666); acceptable for a local dev tool. write_env_seed does not verify target is gitignored (shortcut: relies on .gitignore + stage1 secret scan).

## Cross-cutting (from DEV-001 review) — MUST honor in browser tickets
- check_url() is a convention, not an enforced boundary. DEV-002/003/004 MUST route ALL navigation + every redirect/subresource through check_url (e.g. Playwright context.route handler), and call load_env_seed() to get creds.
- UI-002: /verify still shows the OTP form after a successful verification (success status + data-verified=true already shown). Tighten later; not blocking.

## DEV-002 (approved) deferred minors
- Allowlist routing does not cover WebSockets or service-worker fetches. Fix: service_workers='block' + route_web_socket in guard_context.
- Classifier test coverage thin (~6 of 47 tests are new classifier cases).
- Cache re-validation has no age check.
- Live 8889 crawl (/register=signup, /login=login) was waived while 8889 was down — RE-CONFIRM now that 8889 is back up (fold into DEV-004 e2e).

## DEV-006 (approved) deferred minors
- If an email step is SKIPPED and a later step really fails, exit code is 3 (skipped_email) instead of 1 (fail). Unlikely because the email step stops the chain, but note it.
- Old runs/e2e-localhost_8889.json from before the fix still fails json.load (gitignored; a new --e2e run regenerates it).

## UI-001 (built) follow-ups (pre-review)
- Optionally call write_report_html(path) at end of run.py so every run emits report.html (DEV-008 can also call it).
- 8889 report.html ~3MB because 4 screenshots inlined; lower EMBED_MAX if too heavy.
- Failed-run layout only exercised by a synthetic unit test, not a real failed report.
