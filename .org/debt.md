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

## UI-001 (approved) deferred minors
- test_no_secret_values uses only generic regexes; it never checks the real .env.test values or a planted secret, so it is weak. Strengthen to assert the actual generated creds are absent.
- Screenshots embedded as base64 (HTML ~3MB); their pixels can't be grepped for leaks.
- Artifact links use only the file basename, so report.html must stay beside the artifacts.
- DEV-008 (approved): the Mailpit-down skip path was confirmed from code, not exercised live (Mailpit was up during review).

## Final design audit follow-ups (acceptable to ship as-is; none blocking)
HTML report (authagent/report_html.py):
- Worth doing: collapse passing steps (<details>, failing open) + add a "N of M steps passed" count under the badge.
- Worth doing: report.html is ~3MB from base64-embedded screenshots; embed only failed-step + last-pass shots, or link the PNGs beside the report.
- Polish: neutral border for passing steps (reserve green for badge/✓); larger .st; show HH:MM:SS + duration (full ISO only in header); humanize dl key names + render signals as inline chips; collapse Discovered routes/Artifacts; @media print rules.
Test-site pages (testsite-email/views/*): no changes required (semantic, accessible, clear states). Optional: reorder verify.html hint above status; extract shared /style.css if edited again; button:focus-visible instead of :focus.
Audit caveat: the failure banner / failed-step styling / "No routes discovered." empty state are verified in code only, never rendered with a real failed report.
